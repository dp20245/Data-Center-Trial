"""
dc_osint.py  —  SS4 job-posting signals (Greenhouse/Lever public JSON + Adzuna).

All return OSINT sub-schema rows. Greenhouse/Lever need real ATS tokens in
dc_config (empty by default -> skipped). Adzuna needs ADZUNA_APP_ID/KEY env
(absent -> skipped). Reddit lives in dc_ingest.fetch_reddit.
"""
import os
import re
import json
import time
import hashlib
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

import dc_config as dc
import dc_ingest

UA = "Mozilla/5.0 dc-osint"

TENDER_CACHE_PATH = os.path.join(os.path.dirname(__file__), "tender_cache.json")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _get_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 tag-dc"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


def _get_retry(url, tries=4):
    """GET JSON with backoff on 429/5xx (PeeringDB rate-limits rapid calls)."""
    delay = 2
    for attempt in range(tries):
        try:
            return _get(url)
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt < tries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 16)
                continue
            raise


def _oid(*parts):
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def _row(uid, date, signal, actor, geo, layer, magnitude, conf, url, excerpt):
    return {"id": uid, "observed_date": date[:10], "signal_type": signal,
            "actor": actor, "geo": geo, "layer": layer, "magnitude": magnitude,
            "confidence": conf, "url": url, "excerpt": excerpt[:300]}


def fetch_greenhouse():
    rows = []
    for token in dc.GREENHOUSE_TOKENS:
        try:
            time.sleep(0.3)
            data = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
            jobs = data.get("jobs", [])
            for j in jobs:
                loc = (j.get("location") or {}).get("name", "")
                geos = dc_ingest.tag_geo(loc.lower())
                if not geos:
                    continue  # only India/GCC roles
                title = j.get("title", "")
                rows.append(_row(
                    _oid("gh", token, str(j.get("id"))), j.get("updated_at", ""),
                    "job-posting", token, "; ".join(geos),
                    "; ".join(dc_ingest.tag_layers(title.lower())) or "General",
                    "1 role", "med", j.get("absolute_url", ""), f"{title} — {loc}"))
        except Exception as exc:
            print(f"  [greenhouse {token}] {exc}")
    return rows


def fetch_lever():
    rows = []
    for token in dc.LEVER_TOKENS:
        try:
            time.sleep(0.3)
            data = _get(f"https://api.lever.co/v0/postings/{token}?mode=json")
            for j in data:
                loc = ((j.get("categories") or {}).get("location") or "")
                geos = dc_ingest.tag_geo(loc.lower())
                if not geos:
                    continue
                title = j.get("text", "")
                rows.append(_row(
                    _oid("lv", token, j.get("id", "")), "",
                    "job-posting", token, "; ".join(geos),
                    "; ".join(dc_ingest.tag_layers(title.lower())) or "General",
                    "1 role", "med", j.get("hostedUrl", ""), f"{title} — {loc}"))
        except Exception as exc:
            print(f"  [lever {token}] {exc}")
    return rows


def fetch_adzuna(per_country=20):
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []
    rows = []
    for country, query in dc.ADZUNA_QUERIES.items():
        from urllib.parse import quote
        url = (f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
               f"?app_id={app_id}&app_key={app_key}&results_per_page={per_country}"
               f"&what={quote(query)}&content-type=application/json")
        try:
            time.sleep(0.3)
            data = _get(url)
            for j in data.get("results", []):
                loc = (j.get("location") or {}).get("display_name", "")
                title = j.get("title", "")
                geos = dc_ingest.tag_geo(f"{loc} {title}".lower()) or [country.upper()]
                rows.append(_row(
                    _oid("az", str(j.get("id"))), j.get("created", ""),
                    "job-posting", j.get("company", {}).get("display_name", "Adzuna"),
                    "; ".join(geos),
                    "; ".join(dc_ingest.tag_layers(title.lower())) or "General",
                    "1 role", "low", j.get("redirect_url", ""), f"{title} — {loc}"))
        except Exception as exc:
            print(f"  [adzuna {country}] {exc}")
    return rows


def fetch_peeringdb():
    """SS4 facility + IX presence (Network/Colo). Free JSON, no key. Confirms
    presence (signal_type=facility-presence), not a new development."""
    rows = []
    for geo, url in dc.PEERINGDB_FAC_URLS.items():
        try:
            time.sleep(1.5)
            for f in _get_retry(url).get("data", []):
                name = f.get("name", "")
                rows.append(_row(
                    _oid("pdb-fac", str(f.get("id"))), f.get("updated", ""),
                    "facility-presence", f.get("org_name") or name, geo,
                    "; ".join(dc_ingest.tag_layers(name.lower())) or "Colo",
                    f"{f.get('net_count', 0)} nets", "high",
                    f"https://www.peeringdb.com/fac/{f.get('id')}",
                    f"{name} — {f.get('city', '')}, {f.get('country', '')}"))
        except Exception as exc:
            print(f"  [peeringdb fac {geo}] {exc}")
    try:
        time.sleep(1.5)
        for ix in _get_retry(dc.PEERINGDB_IX_URL).get("data", []):
            name = ix.get("name", "")
            rows.append(_row(
                _oid("pdb-ix", str(ix.get("id"))), ix.get("updated", ""),
                "facility-presence", ix.get("org_name") or name, ix.get("country", ""),
                "Network", f"{ix.get('net_count', 0)} nets", "high",
                f"https://www.peeringdb.com/ix/{ix.get('id')}",
                f"IX: {name} — {ix.get('city', '')}, {ix.get('country', '')}"))
    except Exception as exc:
        print(f"  [peeringdb ix] {exc}")
    return rows


# --------------------------------------------------------------------------
# CPPP India tenders (SS4 signal_type=tender) — keyword pre-gate, then AI triage.
# --------------------------------------------------------------------------
def _load_tender_cache():
    try:
        with open(TENDER_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_tender_cache(c):
    with open(TENDER_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, separators=(",", ":"))


def _cppp_rows(html):
    """Parse the auth-free 'latest active tenders' table: [1]=pub, [4]=title, [5]=org, href=view."""
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        if len(tds) < 6:
            continue

        def clean(x):
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip()

        title = clean(tds[4])
        if not title:
            continue
        m = re.search(r'href="([^"]+)"', tr)
        out.append({"pub": clean(tds[1]), "title": title, "org": clean(tds[5]),
                    "url": m.group(1) if m else ""})
    return out


def _cppp_date(s):
    try:
        return datetime.strptime(s.split()[0], "%d-%b-%Y").strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_cppp_tenders(pages=None):
    pages = pages or dc.CPPP_TENDER_PAGES
    raw = []
    for p in range(1, pages + 1):
        try:
            time.sleep(0.4)
            raw += _cppp_rows(_get_html(dc.CPPP_TENDER_URL.format(page=p)))
        except Exception as exc:
            print(f"  [cppp p{p}] {exc}")

    cands = []                                   # keyword pre-gate (free) -> candidates only
    for r in raw:
        t = r["title"].lower()
        if any(k in t for k in dc.TENDER_KEYWORDS):
            r["id"] = _oid("cppp", r["url"] or r["title"])
            cands.append(r)
    if not cands:
        return []

    cache = _load_tender_cache()                 # AI triage on uncached only, batched, non-fatal
    todo = [{"id": c["id"], "title": c["title"], "org": c["org"]}
            for c in cands if c["id"] not in cache]
    if todo:
        import dc_ai
        for tid, v in dc_ai.classify_tenders(todo).items():
            cache[tid] = v
        _save_tender_cache(cache)

    rows = []
    for c in cands:
        v = cache.get(c["id"])                    # None = AI unavailable -> keyword-only fallback keeps it
        if v is not None and not v.get("is_dc", False):
            continue                              # AI said not a DC tender -> drop
        layer = (v.get("layer") if v else "") or "; ".join(dc_ingest.tag_layers(c["title"].lower())) or "General"
        mag = f"{v['capacity_mw']} MW" if v and v.get("capacity_mw") else ""
        extra = ""
        if v:
            bits = [f"{k}={v[k]}" for k in ("state", "capacity_mw", "value_inr") if v.get(k)]
            extra = ("  [" + "; ".join(bits) + "]") if bits else ""
        rows.append(_row(c["id"], _cppp_date(c["pub"]), "tender", c["org"] or "Gov tender",
                         "India", layer, mag, "med", c["url"], c["title"] + extra))
    return rows


# --------------------------------------------------------------------------
# OSM Overpass facilities (SS4 facility-presence, med) — building-centric, noise-filtered.
# --------------------------------------------------------------------------
def _osm_keep(tags, gaz):
    # precision > recall (PeeringDB covers recall): a bare operator tag is too weak
    # (a college computer lab has one) — require a real DC marker.
    name = (tags.get("name") or "").lower()
    if not name:
        return False
    if tags.get("building") == "data_center":
        return True
    if any(g in name for g in gaz):
        return True
    return any(s in name for s in ("data center", "data centre", "datacenter", "datacentre"))


def fetch_overpass():
    rows = []
    gaz = [g.lower() for g in dc.WATCH_OPERATORS_INDIA + dc.WATCH_OPERATORS_GCC]
    for market, iso in dc.OVERPASS_ISO.items():
        q = (f'[out:json][timeout:25];area["ISO3166-1"="{iso}"]->.a;'
             f'(nwr["telecom"="data_center"](area.a);nwr["building"="data_center"](area.a););out center 200;')
        try:
            time.sleep(1.5)                       # Overpass rate-limits
            req = urllib.request.Request(dc.OVERPASS_URL,
                                         data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": "tag-dc-bot/1.0 (research)"})
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode("utf-8", "ignore"))
            for el in data.get("elements", []):
                tags = el.get("tags", {})
                if not _osm_keep(tags, gaz):
                    continue
                name = tags["name"]
                rows.append(_row(
                    _oid("osm", str(el.get("type")), str(el.get("id"))),
                    "", "facility-presence", tags.get("operator") or name, market,
                    "; ".join(dc_ingest.tag_layers(name.lower())) or "Colo", "", "med",
                    f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
                    f"OSM: {name} — {tags.get('addr:city', '')}, {market}"))
        except Exception as exc:
            print(f"  [overpass {market}] {exc}")
    return rows


def fetch_all():
    jobs = fetch_greenhouse() + fetch_lever() + fetch_adzuna()
    facilities = fetch_peeringdb() + fetch_overpass()
    tenders = fetch_cppp_tenders()
    return jobs + facilities + tenders, {"OSINT jobs": len(jobs),
            "facilities": len(facilities), "tenders": len(tenders)}


def _selfcheck():
    """Offline: CPPP parser + keyword intent + OSM noise filter + date parse."""
    fx = ('<tr><td>1.</td><td>01-Jul-2026 12:10 PM</td><td>06-Jul-2026</td><td>06-Jul-2026</td>'
          '<td><a href="http://t/1">Supply and installation of colocation data centre</a></td>'
          '<td>NIC</td><td>--</td></tr>')
    r = _cppp_rows(fx)
    assert r and r[0]["title"].lower().startswith("supply and installation of colocation"), r
    assert r[0]["org"] == "NIC" and r[0]["url"] == "http://t/1", r
    assert any(k in r[0]["title"].lower() for k in dc.TENDER_KEYWORDS)
    gaz = ["yotta", "ctrls"]
    assert _osm_keep({"name": "Yotta NM1", "telecom": "data_center"}, gaz)      # gazetteer
    assert _osm_keep({"name": "Foo", "building": "data_center"}, gaz)           # building tag
    assert _osm_keep({"name": "Acme Data Centre", "telecom": "data_center"}, gaz)  # name marker
    assert not _osm_keep({"name": "st marys press", "telecom": "data_center"}, gaz)  # noise
    assert not _osm_keep({"name": "Malda College", "operator": "x"}, gaz)       # bare operator dropped
    assert _cppp_date("01-Jul-2026 12:10 PM") == "2026-07-01"
    print("dc_osint self-check: OK")


if __name__ == "__main__":
    _selfcheck()
