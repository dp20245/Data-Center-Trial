"""
dc_osint.py  —  SS4 job-posting signals (Greenhouse/Lever public JSON + Adzuna).

All return OSINT sub-schema rows. Greenhouse/Lever need real ATS tokens in
dc_config (empty by default -> skipped). Adzuna needs ADZUNA_APP_ID/KEY env
(absent -> skipped). Reddit lives in dc_ingest.fetch_reddit.
"""
import os
import json
import time
import hashlib
import urllib.request
import urllib.error

import dc_config as dc
import dc_ingest

UA = "Mozilla/5.0 dc-osint"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


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


def fetch_all():
    jobs = fetch_greenhouse() + fetch_lever() + fetch_adzuna()
    facilities = fetch_peeringdb()
    return jobs + facilities, {"OSINT jobs": len(jobs), "PeeringDB facilities": len(facilities)}
