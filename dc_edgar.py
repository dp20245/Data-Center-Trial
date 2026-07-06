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
    """[(pos, keyword, country)] for India/GCC geo keywords found. `text` must be lowered."""
    out = []
    for country, kws in dc_ingest.GEO_KEYWORDS.items():
        for kw in kws:                      # GEO_KEYWORDS are lowercase
            i = text.find(kw)
            if i >= 0:
                out.append((i, kw, country))
    return out


def extract_sections(text):
    """Split a filing into labeled spans ordered by evidence priority (Risk Factors &
    Growth first, then Business, then a whole-doc Other fallback). Each span = header→next
    header. Returns [(priority_rank, label, span_text)]. Sheet 7 §5-style section scoping —
    keeps the extractor out of XBRL tag-soup and country-list boilerplate."""
    t = text.lower()
    marks = []                              # (char_pos, priority_rank, label)
    for rank, (label, pat) in enumerate(dc.EDGAR_SECTION_PRIORITY):
        for m in re.finditer(pat, t):
            marks.append((m.start(), rank, label))
    if not marks:
        return [(99, "Other", text)]
    marks.sort()
    spans = []
    for i, (pos, rank, label) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        spans.append((rank, label, text[pos:end]))
    spans.append((99, "Other", text))       # lowest-priority full-doc fallback
    spans.sort(key=lambda s: s[0])
    return spans


def _word_window(text, anchor_char, words=None):
    """~`words` words each side of the anchor character position (word-accurate context)."""
    words = words or dc.EDGAR_EVIDENCE_WORDS
    left = text[:anchor_char].split()
    right = text[anchor_char:].split()
    return " ".join(left[-words:] + right[:words])


def extract_evidence(text):
    """Scan sections in priority order; in the highest-priority section that has a DC term
    with a geo+action nearby, anchor there and return a 500-word context window plus the
    matched terms / deal_type / region / confidence / layer / section. A DC term is REQUIRED
    (geo-only rows are dropped — that was the country-list false-positive source)."""
    blank = {"evidence": "", "window_text": "", "section": "", "matched_terms": "",
             "deal_type": "", "counterparty_region": "", "confidence": "low", "layer": "General"}
    if not text:
        return blank
    W = dc.EDGAR_EVIDENCE_WINDOW

    _CONF = {"high": 2, "med": 1, "low": 0}
    best = None                             # highest (conf, section-priority) candidate
    for rank, label, span in extract_sections(text):
        t = span.lower()
        dcs = _first_positions(t, dc.DC_TERMS)
        if not dcs:                         # require a DC term IN this section
            continue
        geos = _geo_positions(t)
        acts = _first_positions(t, dc.ACTION_TERMS)
        anchor, conf, cregion = None, "low", ""
        for di, _ in dcs:                   # prefer a DC term with geo+action nearby
            near_geo = [(g, c) for (g, _kw, c) in geos if abs(g - di) <= W]
            near_act = any(abs(a - di) <= W for a, _ in acts)
            if near_geo and near_act:
                anchor, conf, cregion = di, "high", near_geo[0][1]
                break
            if near_geo and conf != "high":
                anchor, conf, cregion = di, "med", near_geo[0][1]
        if anchor is None:                  # DC term but no geo nearby: keep as weak candidate
            anchor, conf = dcs[0][0], "low"
        # Pick by confidence first, then by section priority (Risk/Growth win ties) — so a
        # strong geo-anchored Business hit isn't lost to a weak Risk mention, while risk/growth
        # are still preferred whenever the evidence is equally strong.
        key = (_CONF[conf], -rank)
        cand = (key, rank, label, span, t, anchor, conf, cregion, geos)
        if best is None or key > best[0]:
            best = cand
        if conf == "high" and rank < 2:     # nothing will beat a high-confidence Risk/Growth hit
            break
    if best is None:
        return blank

    _key, _rank, label, span, t, anchor, conf, cregion, geos = best
    snippet = span[max(0, anchor - 250):anchor + 350].strip()
    window = _word_window(span, anchor)
    win = t[max(0, anchor - W):anchor + W]
    matched = sorted(
        {term.strip() for term in dc.DC_TERMS + dc.ACTION_TERMS if term in win}
        | {kw for (_p, kw, _c) in geos if kw in win})
    deal = next((dt for term, dt in dc.DEAL_TYPE_TERMS if term in win), "")
    layer = "; ".join(dc_ingest.tag_layers(win)) or "General"
    return {"evidence": snippet, "window_text": window, "section": label,
            "matched_terms": ", ".join(matched[:8]), "deal_type": deal,
            "counterparty_region": cregion, "confidence": conf, "layer": layer}


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
    _attach_verdicts(rows)
    for r in rows:
        r.pop("window_text", None)          # context was for the judge, not the sheet
    return rows, {"EDGAR FTS": len(rows)}


# --- AI relevance judge (OpenRouter / Nemotron), permanent per-accession cache ------------
EDGAR_CACHE_PATH = os.path.join(os.path.dirname(__file__), "edgar_cache.json")


def _load_cache():
    if os.path.exists(EDGAR_CACHE_PATH):
        try:
            with open(EDGAR_CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(c):
    with open(EDGAR_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, separators=(",", ":"))


def _attach_verdicts(rows):
    """Judge each filing's evidence window once (filings are immutable → permanent cache).
    Write-all gate: every row keeps a `relevance` verdict + `section`; the judge, when it
    ran, overrides the brittle keyword guesses. Non-fatal — no key/failure leaves keyword
    fields intact and relevance='(no AI verdict)'."""
    import dc_ai
    cache = _load_cache()
    todo = [{"accession": r["accession"], "filer": r["filer"], "form": r["form"],
             "section": r.get("section", ""), "matched_terms": r.get("matched_terms", ""),
             "window_text": r.get("window_text", "")}
            for r in rows if r["accession"] not in cache and r.get("window_text")]
    verdicts = dc_ai.judge_filings(todo)
    if verdicts:
        cache.update(verdicts)
        _save_cache(cache)
    for r in rows:
        v = cache.get(r["accession"])
        if v:
            yn = "yes" if v.get("relevant") else "no"
            r["relevance"] = f"{yn} — {v.get('why', '')}".strip(" —")
            r["confidence"] = v.get("confidence") or r.get("confidence", "low")
            r["deal_type"] = v.get("deal_type") or r.get("deal_type", "")
            if v.get("region"):
                r["counterparty_region"] = v["region"]
            if v.get("layer"):
                r["layer"] = v["layer"]
        else:
            r.setdefault("relevance", "(no AI verdict)")


if __name__ == "__main__":
    rows, health = fetch_filings(limit=8)
    print("health:", health)
    for r in rows:
        print(f"\n  {r['filed_date']} {r['form']} {r['filer'][:46]} "
              f"[{r['confidence']}|{r['deal_type'] or '-'}|{r['layer']}|{r['counterparty_region'] or '-'}] "
              f"§{r.get('section') or '-'}")
        print(f"    matched:   {r['matched_terms']}")
        print(f"    verdict:   {r.get('relevance', '')}")
        print(f"    evidence:  {r['evidence'][:160]}")
