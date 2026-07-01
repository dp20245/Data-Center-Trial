"""
check_dc_sources.py  —  validate every source in the registry in one command.

    python check_dc_sources.py

Prints ✅/❌ per feed (HTTP status + whether the body looks like RSS/Atom/JSON),
so a freshly pasted source — including Codex-supplied ones — is verified before
it ships. Read-only; no credentials needed. A source that fails here should be
fixed or quarantined in dc_config.py before relying on it.
"""
import ssl
import sys
import time
import urllib.request
import urllib.error

import dc_config as dc

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 dc-source-check"
_INSECURE = ssl.create_default_context()
_INSECURE.check_hostname = False
_INSECURE.verify_mode = ssl.CERT_NONE


def _check(name, url, want="xml"):
    """want: 'xml' for RSS/Atom feeds, 'json' for APIs. Returns True if live+valid."""
    time.sleep(0.5)  # be polite (Reddit 429s on rapid same-host hits)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            r = urllib.request.urlopen(req, timeout=25)
        except urllib.error.URLError as e:
            if "CERTIFICATE" not in str(e):
                raise
            r = urllib.request.urlopen(req, timeout=25, context=_INSECURE)  # some gov feeds have bad chains
        with r:
            code = r.status
            body = r.read(2000).decode("utf-8", "ignore").lstrip().lower()
        if want == "xml":
            ok = ("<rss" in body) or ("<feed" in body) or body.startswith("<?xml")
        elif want == "html":
            ok = ("<table" in body) or ("<tr" in body) or ("<html" in body) or ("<!doctype" in body)
        else:
            ok = body.startswith("{") or body.startswith("[")
        mark = "✅" if ok else "⚠️"
        print(f"  {mark} [{code}] {name}: {'valid ' + want if ok else 'NOT ' + want + ' (HTML/error?)'}")
        return ok
    except urllib.error.HTTPError as e:
        if e.code == 429:  # alive but rate-limited (Reddit) — not dead
            print(f"  ⚠️ [429] {name}: rate-limited (reachable; throttle at runtime)")
            return True
        print(f"  ❌ [{e.code}] {name}: {url}")
    except Exception as e:
        print(f"  ❌ [err] {name}: {e}")
    return False


def main():
    live = total = 0

    def run(title, feeds, want="xml"):
        nonlocal live, total
        print(f"\n{title}")
        for name, url in feeds.items():
            total += 1
            live += _check(name, url, want)

    run("SS1 — News feeds", dc.DC_NEWS_FEEDS)
    run("SS1 — Geo discovery (Google News)", dc.DC_GNEWS_GEO)
    run("SS2 — Policy feeds", dc.DC_POLICY_FEEDS)
    run("SS2 — Policy geo (Google News)", dc.POLICY_GNEWS_GEO)
    run("SS4 — Reddit OSINT", dc.REDDIT_FEEDS)

    # Endpoint-shape probes (these need params/keys, so just probe the host is up):
    print("\nSS3/SS4 — APIs (probe only)")
    total += 1
    live += _check("SEC EDGAR FTS",
                   f"{dc.EDGAR_FTS_URL}?q=%22data+center%22&forms=8-K", want="json")
    for geo, url in dc.PEERINGDB_FAC_URLS.items():
        total += 1
        live += _check(f"PeeringDB fac {geo}", url, want="json")
    total += 1
    live += _check("PeeringDB ix", dc.PEERINGDB_IX_URL, want="json")
    total += 1
    live += _check("CPPP tenders", dc.CPPP_TENDER_URL.format(page=1), want="html")
    total += 1                                    # Overpass needs POST (GET 406s)
    try:
        q = '[out:json][timeout:25];area["ISO3166-1"="IN"]->.a;(nwr["telecom"="data_center"](area.a););out count;'
        req = urllib.request.Request(dc.OVERPASS_URL, data=urllib.parse.urlencode({"data": q}).encode(),
                                     headers={"User-Agent": "tag-dc-bot/1.0 (research)"})
        with urllib.request.urlopen(req, timeout=45) as r:
            ok = r.status == 200 and b"elements" in r.read(2000)
        print(f"  {'✅' if ok else '❌'} OSM Overpass")
        live += bool(ok)
    except Exception as e:
        print(f"  ❌ OSM Overpass ({e})")
    for token in dc.GREENHOUSE_TOKENS:
        total += 1
        live += _check(f"Greenhouse/{token}",
                       f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", want="json")
    for token in dc.LEVER_TOKENS:
        total += 1
        live += _check(f"Lever/{token}",
                       f"https://api.lever.co/v0/postings/{token}?mode=json", want="json")

    print(f"\n{live}/{total} sources live. "
          f"{'All good.' if live == total else 'Fix or quarantine the ❌/⚠️ ones in dc_config.py.'}")
    sys.exit(0 if live == total else 1)


if __name__ == "__main__":
    main()
