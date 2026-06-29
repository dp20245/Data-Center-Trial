"""
dc_ingest.py  —  SS1 ingestion. feedparser only (no ML).

Pulls every feed in the registry, normalises each entry, assigns a stable ID,
tags value-chain LAYER(s) and GEO, and keeps only India/GCC-relevant items
(the SS1 scope filter). Global trade feeds carry lots of US/EU stories; we drop
those unless an India/GCC actor/site is named, per PRD non-goals.
"""
import re
import html
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import feedparser

import dc_config as dc

# Some feeds (and Reddit/Oman) reject feedparser's default UA — present a browser one.
feedparser.USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 dc-bot"

_TRACK = ("utm_", "fbclid", "gclid", "igshid", "ref")

# Geo detection — India + GCC only. First key whose keyword hits wins as primary;
# all hits are recorded so a multi-market story keeps both tags.
GEO_KEYWORDS = {
    "India": ["india", "indian", "mumbai", "navi mumbai", "hyderabad", "chennai",
              "bengaluru", "bangalore", "pune", "noida", "delhi", "kolkata"],
    "UAE": ["uae", "united arab emirates", "dubai", "abu dhabi", "sharjah"],
    "Saudi Arabia": ["saudi", "riyadh", "jeddah", "neom", "dammam"],
    "Qatar": ["qatar", "doha"],
    "Bahrain": ["bahrain", "manama"],
    "Kuwait": ["kuwait"],
    "Oman": ["oman", "muscat"],
}


def clean_link(link):
    try:
        p = urlparse(link)
        q = [(k, v) for (k, v) in parse_qsl(p.query)
             if not any(k.lower().startswith(t) for t in _TRACK)]
        return urlunparse(p._replace(query=urlencode(q), fragment=""))
    except Exception:
        return link


def article_id(link):
    return hashlib.sha1(clean_link(link).encode("utf-8")).hexdigest()[:12]


def _strip(t):
    return html.unescape(re.sub(r"<[^>]+>", "", t or "")).strip()


def _published(e):
    for key in ("published_parsed", "updated_parsed"):
        t = e.get(key)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def _matches(text, keywords):
    return [kw for kw in keywords
            if re.search(r"\b" + re.escape(kw) + r"\b", text)]


def tag_layers(text):
    """All layers with >=1 keyword hit, ordered by hit count (primary first)."""
    scored = []
    for layer, kws in dc.LAYERS.items():
        n = len(_matches(text, [k.lower() for k in kws]))
        if n:
            scored.append((n, layer))
    scored.sort(reverse=True)
    return [layer for _, layer in scored]


def tag_geo(text):
    """All India/GCC markets named, primary (most hits) first."""
    scored = []
    for geo, kws in GEO_KEYWORDS.items():
        n = len(_matches(text, kws))
        if n:
            scored.append((n, geo))
    scored.sort(reverse=True)
    return [geo for _, geo in scored]


def _gnews_publisher(entry, title):
    src = entry.get("source")
    pub = src.get("title", "") if isinstance(src, dict) else ""
    if pub and title.endswith(f" - {pub}"):
        title = title[: -(len(pub) + 3)]
    return pub, title


def fetch():
    """Return (rows, health). Each feed gets an optional geo hint: the geo-scoped
    Google News feeds are already country-bound, so an item with no detected geo
    inherits the feed's country instead of being dropped."""
    feeds = [(name, url, None) for name, url in dc.DC_NEWS_FEEDS.items()]
    for name, url in dc.DC_GNEWS_GEO.items():
        hint = name.replace("GNews ", "").strip()  # "GNews India" -> "India"
        hint = {"Saudi": "Saudi Arabia"}.get(hint, hint)
        feeds.append((name, url, hint))

    rows, health = [], {}
    for name, url, geo_hint in feeds:
        is_gnews = "news.google.com" in url
        try:
            parsed = feedparser.parse(url)
            entries = parsed.entries or []
            health[name] = len(entries)
            for e in entries:
                title = _strip(e.get("title", ""))
                summary = _strip(e.get("summary", e.get("description", "")))
                link = e.get("link", "")
                if not title or not link:
                    continue
                source = name
                if is_gnews:
                    pub, title = _gnews_publisher(e, title)
                    source = pub or name
                text = f"{title} {summary}".lower()
                geos = tag_geo(text)
                if not geos and geo_hint:
                    geos = [geo_hint]
                if not geos:
                    continue  # out of India/GCC scope -> drop
                layers = tag_layers(text)
                rows.append({
                    "id": article_id(link),
                    "date": _published(e),
                    "source": source,
                    "layer": "; ".join(layers) if layers else "General",
                    "geo": "; ".join(geos),
                    "title": title,
                    "url": clean_link(link),
                    "summary": summary[:500],
                    "type": "gnews-geo" if is_gnews else "feed",
                    "primary_layer": layers[0] if layers else "General",
                    "text": f"{title}. {summary}"[:1000],
                })
        except Exception as exc:
            health[name] = 0
            print(f"  [feed error] {name}: {exc}")
    return rows, health


def dedup(rows, seen_ids):
    """Drop already-seen IDs and within-batch dupes (same story via two feeds)."""
    out, batch, headlines = [], set(), set()
    for r in rows:
        if r["id"] in seen_ids or r["id"] in batch:
            continue
        norm = re.sub(r"[^a-z0-9]", "", r["title"].lower())[:80]
        if norm in headlines:
            continue
        batch.add(r["id"]); headlines.add(norm)
        out.append(r)
    return out
