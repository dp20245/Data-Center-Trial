"""
dc_edgar.py  —  SS3 corporate disclosure via SEC EDGAR full-text search.

Free JSON API, no key. Requires a descriptive User-Agent (SEC_USER_AGENT env,
e.g. "Name email@x.com") and a ≤10 req/s cap.

Like the Sheet 7 SEC connector: for each full-text hit it fetches the actual
filing text and extracts an EVIDENCE WINDOW around matched keywords — a data-center
term near a geo term near an action/deal term — and records which terms matched,
the deal_type, and a confidence based on that proximity. Evidence is auditable.
"""
import os
import re
import time
import json
import gzip
import urllib.request
import urllib.error

import dc_config as dc
import dc_ingest  # reuse tag_layers + GEO_KEYWORDS


def _ua():
    return os.environ.get("SEC_USER_AGENT", "Data-Center-Trial dpuri2024@gmail.com")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": _ua(),
                                               "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8", "ignore"))


def _filing_url(adsh, cik, fname):
    acc = adsh.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{fname}"


# --- filing body fetch + evidence extraction -------------------------------
_DOC_CACHE = {}


def fetch_doc_text(url, cap=800_000):
    """Fetch a filing document, strip HTML, return plain text (capped, cached).
    Requests identity encoding so a capped read isn't a truncated gzip stream."""
    if not url:
        return ""
    if url in _DOC_CACHE:
        return _DOC_CACHE[url]
    text = ""
    for attempt in range(3):
        try:
            time.sleep(0.15)  # ≤10 req/s
            req = urllib.request.Request(
                url, headers={"User-Agent": _ua(), "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read(cap)
            html = raw.decode("utf-8", "ignore")
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"&#?\w+;", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            break
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
        except Exception:
            break
    _DOC_CACHE[url] = text
    return text


def _first_positions(text, terms):
    """[(pos, term)] for each term's first occurrence (term kept as written)."""
    out = []
    for t in terms:
        i = text.find(t)
        if i >= 0:
            out.append((i, t.strip()))
    return out


def _geo_positions(text):
    """[(pos, keyword, country)] for India/GCC geo keywords found."""
    out = []
    for country, kws in dc_ingest.GEO_KEYWORDS.items():
        for kw in kws:
            i = text.find(kw)
            if i >= 0:
                out.append((i, kw, country))
    return out


def extract_evidence(text):
    """Find the tightest DC↔geo↔action window; return evidence snippet, matched
    terms, deal_type, counterparty_region, confidence, layer (Sheet 7 §10 rule)."""
    blank = {"evidence": "", "matched_terms": "", "deal_type": "",
             "counterparty_region": "", "confidence": "low", "layer": "General"}
    if not text:
        return blank
    t = text.lower()
    W = dc.EDGAR_EVIDENCE_WINDOW
    dcs = _first_positions(t, dc.DC_TERMS)
    geos = _geo_positions(t)
    acts = _first_positions(t, dc.ACTION_TERMS)

    anchor, conf, cregion = None, "low", ""
    for di, _ in dcs:                       # prefer a DC term with geo+action nearby
        near_geo = [(g, c) for (g, _kw, c) in geos if abs(g - di) <= W]
        near_act = any(abs(a - di) <= W for a, _ in acts)
        if near_geo and near_act:
            anchor, conf, cregion = di, "high", near_geo[0][1]
            break
        if near_geo and conf != "high":
            anchor, conf, cregion = di, "med", near_geo[0][1]
    if anchor is None:                      # fall back to first geo / first DC
        if geos:
            anchor, cregion = geos[0][0], geos[0][2]
            conf = "med" if dcs else "low"
        elif dcs:
            anchor = dcs[0][0]
        else:
            anchor = 0

    start = max(0, anchor - 150)
    snippet = text[start:start + 300].strip()
    win = t[max(0, anchor - W):anchor + W]
    matched = sorted(
        {term.strip() for term in dc.DC_TERMS + dc.ACTION_TERMS if term in win}
        | {kw for (_p, kw, _c) in geos if kw in win})
    deal = next((dt for term, dt in dc.DEAL_TYPE_TERMS if term in win), "")
    layer = "; ".join(dc_ingest.tag_layers(win)) or "General"
    return {"evidence": snippet, "matched_terms": ", ".join(matched[:8]),
            "deal_type": deal, "counterparty_region": cregion,
            "confidence": conf, "layer": layer}


def fetch_filings(limit=None):
    """One phrase query per market, deduped by accession, recency-sorted, then the
    N most-recent get their filing body fetched + evidence extracted."""
    from urllib.parse import quote
    limit = limit or dc.EDGAR_MAX_DOCS
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
                cik = (s.get("ciks") or [""])[0]
                fname = h.get("_id", "").split(":")[-1]
                by_acc[adsh] = {
                    "accession": adsh,
                    "filed_date": s.get("file_date", ""),
                    "filer": (s.get("display_names") or [""])[0],
                    "cik": cik,
                    "form": s.get("form", ""),
                    "url": _filing_url(adsh, cik or "0", fname) if cik else "",
                }
        except urllib.error.HTTPError as e:
            print(f"  [edgar error] {e.code} on {term!r}")
        except Exception as exc:
            print(f"  [edgar error] {exc} on {term!r}")

    rows = sorted(by_acc.values(), key=lambda r: r["filed_date"], reverse=True)[:limit]
    for r in rows:
        ev = extract_evidence(fetch_doc_text(r["url"]))
        # fall back to filer-name layer tag if the body gave nothing
        if ev["layer"] == "General":
            ev["layer"] = "; ".join(dc_ingest.tag_layers(r["filer"].lower())) or "General"
        r.update(ev)
    return rows, {"EDGAR FTS": len(rows)}


if __name__ == "__main__":
    rows, health = fetch_filings(limit=8)
    print("health:", health)
    for r in rows:
        print(f"\n  {r['filed_date']} {r['form']} {r['filer'][:46]} "
              f"[{r['confidence']}|{r['deal_type'] or '-'}|{r['layer']}|{r['counterparty_region'] or '-'}]")
        print(f"    matched: {r['matched_terms']}")
        print(f"    evidence: {r['evidence'][:160]}")
