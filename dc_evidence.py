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
                   "headline", "url", "geo", "layer", "confidence", "event_id"]


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
        put(eid, {"evidence_id": eid, "company": id2co.get(eid, ""),
                  "date": (r.get("date") or "")[:10],
                  "publisher": r.get("source") or _domain(r.get("url", "")),
                  "source_type": "secondary", "headline": (r.get("title") or "")[:180],
                  "url": r.get("url", ""), "geo": r.get("geo", ""), "layer": r.get("layer", ""),
                  "confidence": "med", "event_id": r.get("event_id", "")})
    for r in tabs.get("ss3", []):
        eid = r.get("accession")
        put(eid, {"evidence_id": eid, "company": id2co.get(eid, "") or r.get("filer", ""),
                  "date": (r.get("filed_date") or "")[:10], "publisher": "SEC EDGAR",
                  "source_type": "primary",
                  "headline": f"{r.get('filer', '')} {r.get('form', '')} — {r.get('deal_type', '')}".strip(" —"),
                  "url": r.get("url", ""), "geo": r.get("counterparty_region", ""),
                  "layer": r.get("layer", ""), "confidence": r.get("confidence", "med"),
                  "event_id": ""})
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
                  "confidence": r.get("confidence", "low"), "event_id": ""})
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


if __name__ == "__main__":
    _selfcheck()
