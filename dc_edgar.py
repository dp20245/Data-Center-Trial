"""
dc_edgar.py  —  SS3 corporate disclosure via SEC EDGAR full-text search.

Free JSON API, no key. Requires a descriptive User-Agent (SEC_USER_AGENT env,
e.g. "Name email@x.com") and a ≤10 req/s cap. Returns filings rows in the PRD §3
sub-schema. deal_type/counterparty/excerpt need the filing body, so v1 leaves
them blank (ponytail: enrich by fetching doc text + classifying once SS3 proves out).
"""
import os
import time
import json
import urllib.request
import urllib.error

import dc_config as dc
import dc_ingest  # reuse tag_layers / tag_geo / article_id

# Geo of the filing's stated business location -> our scope (best-effort).
_BIZ_GEO = {"India": "India", "K7": "Saudi Arabia", "C0": "UAE", "K6": "Kuwait",
            "I0": "Qatar", "K3": "Bahrain", "K8": "Oman"}  # SEC state codes are coarse


def _ua():
    return os.environ.get("SEC_USER_AGENT", "Data-Center-Trial dpuri2024@gmail.com")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": _ua(),
                                               "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=30) as r:
        import gzip
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8", "ignore"))


def _filing_url(adsh, cik, fname):
    acc = adsh.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{fname}"


def fetch_filings(limit=40):
    """One phrase query per market, deduped by accession, recency-sorted."""
    from urllib.parse import quote
    by_acc = {}
    for term in dc.EDGAR_GEO_TERMS:
        url = f"{dc.EDGAR_FTS_URL}?q={quote(term)}&forms={dc.EDGAR_FORMS}"
        try:
            time.sleep(0.15)  # ≤10 req/s
            data = _get(url)
            for h in data.get("hits", {}).get("hits", []):
                s = h.get("_source", {})
                adsh = s.get("adsh", "")
                if not adsh or adsh in by_acc:
                    continue
                filer = (s.get("display_names") or [""])[0]
                cik = (s.get("ciks") or [""])[0]
                fname = h.get("_id", "").split(":")[-1]
                by_acc[adsh] = {
                    "accession": adsh,
                    "filed_date": s.get("file_date", ""),
                    "filer": filer,
                    "cik": cik,
                    "form": s.get("form", ""),
                    "counterparty": "",          # ponytail: needs doc body
                    "counterparty_region": "",
                    "deal_type": "",             # ponytail: classify from doc body
                    "layer": "; ".join(dc_ingest.tag_layers(filer.lower())) or "General",
                    "excerpt": "",
                    "url": _filing_url(adsh, cik or "0", fname) if cik else "",
                }
        except urllib.error.HTTPError as e:
            print(f"  [edgar error] {e.code} on {term!r}")
        except Exception as exc:
            print(f"  [edgar error] {exc} on {term!r}")
    rows = sorted(by_acc.values(), key=lambda r: r["filed_date"], reverse=True)[:limit]
    return rows, {"EDGAR FTS": len(rows)}


if __name__ == "__main__":
    rows, health = fetch_filings(limit=10)
    print("health:", health)
    for r in rows[:8]:
        print(f"  {r['filed_date']} {r['form']:5} {r['filer'][:50]}  [{r['layer']}]")
