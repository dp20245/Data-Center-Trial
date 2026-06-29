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


def _gnews_geo_hints():
    """Map each geo-scoped Google News feed name to its country."""
    hints = {}
    for name in dc.DC_GNEWS_GEO:
        c = name.replace("GNews ", "").strip()
        hints[name] = {"Saudi": "Saudi Arabia"}.get(c, c)
    return hints


def pull(feeds, geo_hints=None, type_of=None, geo_required=True):
    """Generic RSS pull shared by SS1/SS2/SS4.

    feeds        : {name: url}
    geo_hints    : {name: country}  — fallback geo for already-scoped feeds
    type_of      : fn(name) -> type flag for the `type` column (else feed/gnews-geo)
    geo_required : drop items with no India/GCC signal (True for in-scope tabs)
    """
    geo_hints = geo_hints or {}
    rows, health = [], {}
    for name, url in feeds.items():
        is_gnews = "news.google.com" in url
        hint = geo_hints.get(name)
        try:
            entries = feedparser.parse(url).entries or []
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
                geos = tag_geo(text) or ([hint] if hint else [])
                if geo_required and not geos:
                    continue
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
                    "type": type_of(name) if type_of else ("gnews-geo" if is_gnews else "feed"),
                    "primary_layer": layers[0] if layers else "General",
                    "text": f"{title}. {summary}"[:1000],
                })
        except Exception as exc:
            health[name] = 0
            print(f"  [feed error] {name}: {exc}")
    return rows, health


def fetch():
    """SS1 News: specialist trade press + per-market Google News."""
    feeds = {**dc.DC_NEWS_FEEDS, **dc.DC_GNEWS_GEO}
    return pull(feeds, geo_hints=_gnews_geo_hints())


# Policy source -> type flag for SS2.
_POLICY_TYPE = {
    "CSET Georgetown": "analysis",
    "PIB India": "legislation", "SEBI": "regulation",
    "Boursa Kuwait": "regulation", "Oman News Agency Economy": "legislation",
}


def fetch_policy():
    """SS2 Policy: think-tank analysis + India/GCC government/market feeds + geo proxy."""
    feeds = {**dc.DC_POLICY_FEEDS, **dc.POLICY_GNEWS_GEO}
    hints = {n: n.replace("GNews ", "").replace(" Policy", "").strip()
             for n in dc.POLICY_GNEWS_GEO}
    hints = {n: {"Saudi": "Saudi Arabia"}.get(v, v) for n, v in hints.items()}
    return pull(feeds, geo_hints=hints,
                type_of=lambda n: _POLICY_TYPE.get(n, "regulation"))


def fetch_reddit():
    """SS4 OSINT (Reddit): keep only India/GCC-relevant posts."""
    return pull(dc.REDDIT_FEEDS, type_of=lambda n: "reddit", geo_required=True)


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
