"""
dc_evidence.py  —  the Evidence Register: resolve every evidence hash (SS5
top_evidence_ids, AI/Dashboard citations) into a readable, clickable record so nothing
in the product shows a bare hash or "open" again.

Deterministic — built from SS1-SS4 rows we already have. `label()`/`hyperlink()` turn an
id into "Publisher — 5 Jun" and a =HYPERLINK cell.
"""
from datetime import datetime

import dc_config as dc

REGISTER_HEADER = ["evidence_id", "company", "date", "publisher", "source_type",
                   "headline", "url", "geo", "layer", "confidence", "event_id",
                   # Phase 4b (append-only):
                   "source_tier"]


_PLACEHOLDER_PUBS = {"publisher", "src", "source", ""}


def source_tier(publisher, url=""):
    """R2: publisher-name or URL-domain -> T1/T2/T3 via dc_config.SOURCE_TIERS.
    Unknown => T3 (SOURCE_TIER_DEFAULT). Deterministic, no network."""
    p = (publisher or "").strip().lower()
    for key, tier in dc.SOURCE_TIERS.items():
        k = key.lower()
        if p and (p == k or p == k.split(".")[0] or k.startswith(p + ".")):
            return tier
    d = _domain(url).lower()
    if d:
        for key, tier in dc.SOURCE_TIERS.items():
            k = key.lower()
            if d == k or d.endswith("." + k):
                return tier
    # Publisher display names ("Reuters", "Economic Times") -> match against domains loosely
    if p:
        squash = p.replace(" ", "")
        for key, tier in dc.SOURCE_TIERS.items():
            stem = key.split(".")[0]
            if len(stem) >= 5 and stem in squash:
                return tier
    return dc.SOURCE_TIER_DEFAULT


def _publisher_or_domain(publisher, url, fallback=""):
    """Never emit a placeholder publisher (the literal 'publisher' bug)."""
    p = (publisher or "").strip()
    if p.lower() in _PLACEHOLDER_PUBS:
        p = ""
    return p or _domain(url) or fallback


def _domain(url):
    try:
        return (url or "").split("/")[2].replace("www.", "")
    except Exception:
        return ""


def _short_date(d):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            dt = datetime.strptime((d or "")[:10], fmt)
            return f"{dt.day} {dt.strftime('%b')}"
        except Exception:
            continue
    return (d or "")[:10]


def build_register(tabs, ranked=None):
    """{evidence_id: record}. `ranked` (optional) tags each id with the operator that cites it."""
    id2co = {}
    for r in (ranked or []):
        for i in (r.get("top_evidence_ids") or "").split(","):
            i = i.strip()
            if i and i not in id2co:
                id2co[i] = r.get("company", "")

    reg = {}

    def put(eid, rec):
        if eid and eid not in reg:
            reg[eid] = rec

    for r in tabs.get("ss1", []) + tabs.get("ss2", []):
        eid = r.get("id")
        pub = _publisher_or_domain(r.get("source"), r.get("url", ""))
        put(eid, {"evidence_id": eid, "company": id2co.get(eid, ""),
                  "date": (r.get("date") or "")[:10],
                  "publisher": pub,
                  "source_type": "secondary", "headline": (r.get("title") or "")[:180],
                  "url": r.get("url", ""), "geo": r.get("geo", ""), "layer": r.get("layer", ""),
                  "confidence": "med", "event_id": r.get("event_id", ""),
                  "source_tier": source_tier(pub, r.get("url", ""))})
    for r in tabs.get("ss3", []):
        eid = r.get("accession")
        put(eid, {"evidence_id": eid, "company": id2co.get(eid, "") or r.get("filer", ""),
                  "date": (r.get("filed_date") or "")[:10], "publisher": "SEC EDGAR",
                  "source_type": "primary",
                  "headline": f"{r.get('filer', '')} {r.get('form', '')} — {r.get('deal_type', '')}".strip(" —"),
                  "url": r.get("url", ""), "geo": r.get("counterparty_region", ""),
                  "layer": r.get("layer", ""), "confidence": r.get("confidence", "med"),
                  "event_id": "", "source_tier": "T1"})   # SEC filings are primary/official
    for r in tabs.get("ss4", []):
        eid = r.get("id")
        st = r.get("signal_type", "")
        primary = st in ("tender", "facility-presence")
        put(eid, {"evidence_id": eid, "company": id2co.get(eid, "") or r.get("actor", ""),
                  "date": (r.get("observed_date") or "")[:10],
                  "publisher": st or _domain(r.get("url", "")),
                  "source_type": "primary" if primary else "secondary",
                  "headline": (r.get("excerpt") or r.get("actor") or "")[:180],
                  "url": r.get("url", ""), "geo": r.get("geo", ""), "layer": r.get("layer", ""),
                  "confidence": r.get("confidence", "low"), "event_id": "",
                  "source_tier": "T1" if primary else "T2"})   # tenders/facilities official; jobs/reddit T2
    return reg


def label(eid, register):
    rec = register.get(eid)
    if not rec:
        return (eid or "")[:10]
    pub = (rec.get("publisher") or "src")[:22]
    d = _short_date(rec.get("date", ""))
    return f"{pub} — {d}" if d else pub


def hyperlink(eid, register):
    rec = register.get(eid) or {}
    url = (rec.get("url") or "").replace('"', "")
    lab = label(eid, register).replace('"', "")
    return f'=HYPERLINK("{url}","{lab}")' if url else lab


def write_register(ss, register):
    import dc_sheets
    ws = dc_sheets.get_tab(ss, dc.EVIDENCE_TAB, REGISTER_HEADER)
    dc_sheets._retry(ws.clear)
    grid = [REGISTER_HEADER] + [[rec.get(k, "") for k in REGISTER_HEADER]
                                for rec in register.values()]
    dc_sheets._retry(ws.update, "A1", grid, value_input_option="RAW")
    return len(grid) - 1


def _selfcheck():
    tabs = {
        "ss1": [{"id": "n1", "date": "2026-07-01", "source": "ET", "title": "AirTrunk $5B India",
                 "url": "https://economictimes.indiatimes.com/x", "geo": "India", "layer": "Build",
                 "event_id": "e9"}],
        "ss3": [{"accession": "a1", "filed_date": "2026-06-03", "filer": "Yotta", "form": "6-K",
                 "deal_type": "expansion", "counterparty_region": "India", "url": "http://sec/a1",
                 "layer": "Colo", "confidence": "high"}],
        "ss4": [{"id": "t1", "observed_date": "2026-06-20", "signal_type": "tender",
                 "actor": "NIC", "excerpt": "Data centre tender", "url": "http://t/1", "geo": "India"}],
    }
    reg = build_register(tabs, ranked=[{"company": "AirTrunk", "top_evidence_ids": "n1"}])
    assert reg["n1"]["company"] == "AirTrunk" and reg["n1"]["source_type"] == "secondary"
    assert reg["a1"]["source_type"] == "primary" and reg["t1"]["source_type"] == "primary"
    assert label("n1", reg) == "ET — 1 Jul", label("n1", reg)
    assert hyperlink("n1", reg).startswith('=HYPERLINK("https://economictimes'), hyperlink("n1", reg)
    assert label("zzz", reg) == "zzz"          # unknown id degrades gracefully
    print("dc_evidence self-check: OK")


def _selfcheck_tiers():
    # R2 fixtures
    assert source_tier("", "https://www.sec.gov/Archives/x") == "T1"
    assert source_tier("Reuters", "") == "T1"
    assert source_tier("Data Center Dynamics", "https://www.datacenterdynamics.com/x") == "T2"
    assert source_tier("Economic Times", "https://economictimes.indiatimes.com/x") == "T2"
    assert source_tier("", "https://vocal.media/x") == "T3"
    assert source_tier("Whalesbook", "") == "T3"
    assert source_tier("Some Unknown Blog", "https://random-seo-site.biz/x") == "T3"
    # placeholder publisher fix
    assert _publisher_or_domain("publisher", "https://www.livemint.com/x") == "livemint.com"
    assert _publisher_or_domain("", "", "PIB India") == "PIB India"
    print("dc_evidence tier self-check: OK")


if __name__ == "__main__":
    _selfcheck()
    _selfcheck_tiers()
