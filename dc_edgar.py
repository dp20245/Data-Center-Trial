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


def fetch_doc_text(url, cap=16_000_000):
    """Fetch a filing document, strip HTML, return plain text (capped, cached).
    Requests identity encoding so a capped read isn't a truncated gzip stream.
    Cap is 16 MB: inline-XBRL 20-Fs are multi-MB (Sify's is 6.9 MB) and their readable
    narrative sits AFTER a large XBRL fact/context block — a tight cap truncates the whole
    Item 3-5 body and leaves only tag-soup. 16 MB covers current filers with headroom."""
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


def _word_window(text, anchor_char, side):
    """~`side` words each side of the anchor character position (word-accurate context)."""
    left = text[:anchor_char].split()
    right = text[anchor_char:].split()
    return " ".join(left[-side:] + right[:side])


def _words_between(text, a, b):
    """Word count of text[a:b] (a<=b)."""
    return len(text[a:b].split())


def extract_20f_items(text):
    """Return the Item 3–5 block of a 20-F (Item 3 Key Info/Risk Factors → Item 4 Business/
    Property → Item 5 Operating Review & Prospects; ends at Item 6). That block is where a
    20-F actually discloses geography, capex and risk — everything else is boilerplate/XBRL.
    Picks the LONGEST Item3→Item6 span so the table-of-contents (tiny gap) and 'see Item 3.D'
    cross-references (short tails) don't win. Returns None if headers aren't found.
    ponytail: header-regex heuristic; swap for a real 20-F item parser only if a filer breaks it."""
    t = text.lower()
    i3 = [m.start() for m in re.finditer(r"item\s*3[\.\s]", t)]
    i4 = [m.start() for m in re.finditer(r"item\s*4[\.\s]", t)]
    i6 = [m.start() for m in re.finditer(r"item\s*6[\.\s]", t)]
    if not i3 or not i6:
        return None
    # Body Item-3 headers are followed by a long section (3.A–3.D) before Item 4; table-of-
    # contents entries have Item 4 right after them. Drop the TOC-style Item-3 positions, then
    # take the longest Item3→next-Item6 span among what's left (ignores late 'see Item 3' refs).
    body = [s for s in i3 if not any(0 < (a - s) < 600 for a in i4)] or i3
    best = None
    for s in body:
        ends = [e for e in i6 if e > s]
        if ends and (best is None or (ends[0] - s) > (best[1] - best[0])):
            best = (s, ends[0])
    return text[best[0]:best[1]] if best else None


def _search_region(text, form):
    """(label, region_text): the slice where BOTH keyword flagging and the AI window live.
    20-F → Item 3-5 only; every other form → whole doc."""
    if form.upper().startswith("20-F"):
        block = extract_20f_items(text)
        if block:
            return "Item 3-5", block
    return "Full " + (form or "doc"), text


def _pick_anchor(region):
    """Best DC anchor in `region` via section-priority scan: (anchor_char, conf, cregion, geos,
    dc_positions) or (None, ...). Prefers a DC term with geo+action nearby; ties broken by
    section priority (Risk/Growth win)."""
    W = dc.EDGAR_EVIDENCE_WINDOW
    _CONF = {"high": 2, "med": 1, "low": 0}
    best = None
    all_dc = []
    for rank, _label, span, off in _sections_with_offsets(region):
        t = span.lower()
        dcs = _first_positions(t, dc.DC_TERMS)
        if not dcs:
            continue
        all_dc += [off + p for p, _ in dcs]
        geos = _geo_positions(t)
        acts = _first_positions(t, dc.ACTION_TERMS)
        anchor, conf, cregion = None, "low", ""
        for di, _ in dcs:
            near_geo = [(g, c) for (g, _kw, c) in geos if abs(g - di) <= W]
            near_act = any(abs(a - di) <= W for a, _ in acts)
            if near_geo and near_act:
                anchor, conf, cregion = di, "high", near_geo[0][1]
                break
            if near_geo and conf != "high":
                anchor, conf, cregion = di, "med", near_geo[0][1]
        if anchor is None:
            anchor, conf = dcs[0][0], "low"
        key = (_CONF[conf], -rank)
        if best is None or key > best[0]:
            best = (key, off + anchor, conf, cregion, off, geos)
        if conf == "high" and rank < 2:
            break
    if best is None:
        return None, "low", "", [], sorted(set(all_dc))
    _k, anchor, conf, cregion, _off, geos = best
    return anchor, conf, cregion, geos, sorted(set(all_dc))


def _sections_with_offsets(text):
    """Like extract_sections but also yields each span's char offset into `text`."""
    t = text.lower()
    marks = []
    for rank, (label, pat) in enumerate(dc.EDGAR_SECTION_PRIORITY):
        for m in re.finditer(pat, t):
            marks.append((m.start(), rank, label))
    if not marks:
        yield (99, "Other", text, 0)
        return
    marks.sort()
    spans = []
    for i, (pos, rank, label) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        spans.append((rank, label, text[pos:end], pos))
    spans.append((99, "Other", text, 0))
    spans.sort(key=lambda s: s[0])
    yield from spans


def extract_evidence(text, form=""):
    """Form-aware evidence extraction. Confine keyword flagging + the AI window to the search
    region (20-F → Item 3-5, else whole doc). If the region fits the AI budget, send it whole
    (no keyword gate — the judge decides); otherwise send a 4000-word window centered to cover
    the DC keyword hits within the region."""
    blank = {"evidence": "", "window_text": "", "section": "", "matched_terms": "",
             "deal_type": "", "counterparty_region": "", "confidence": "low", "layer": "General"}
    if not text:
        return blank
    W = dc.EDGAR_EVIDENCE_WINDOW
    budget = dc.EDGAR_AI_WHOLE_WORDS
    side = budget // 2

    label, region = _search_region(text, form)
    anchor, conf, cregion, geos, dc_hits = _pick_anchor(region)
    region_words = len(region.split())

    if region_words <= budget:
        # Small region: hand the whole thing to the judge, keyword hit or not.
        window, section = region, label
        if anchor is None:
            anchor = 0
    else:
        # Big region (e.g. Sify Item 3-5): require a DC hit, then window to cover the cluster.
        if not dc_hits:
            return blank
        span_words = _words_between(region, dc_hits[0], dc_hits[-1])
        center = ((dc_hits[0] + dc_hits[-1]) // 2) if span_words <= budget else (anchor or dc_hits[0])
        window = _word_window(region, center, side)
        section = label + " (windowed)"

    # Keyword fields from the window (or the anchor's neighbourhood within it).
    wl = window.lower()
    matched = sorted(
        {term.strip() for term in dc.DC_TERMS + dc.ACTION_TERMS if term.strip() in wl}
        | {kw for (_p, kw, _c) in geos if kw in wl})
    deal = next((dt for term, dt in dc.DEAL_TYPE_TERMS if term in wl), "")
    layer = "; ".join(dc_ingest.tag_layers(wl)) or "General"
    snippet = region[max(0, anchor - 250):anchor + 350].strip()
    return {"evidence": snippet, "window_text": window, "section": section,
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
        ev = extract_evidence(fetch_doc_text(r["url"]), r["form"])
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
            quote = _verify_quote(v.get("evidence_quote", ""), r.get("window_text", ""))
            if quote:                       # extractive quote wins the evidence cell
                r["evidence"] = quote
        else:
            r.setdefault("relevance", "(no AI verdict)")


def _verify_quote(quote, source):
    """Return `quote` only if it is a verbatim substring of `source` (whitespace-insensitive,
    case-insensitive) — the anti-hallucination guard. Otherwise '' → keep the mechanical snippet."""
    if not quote or not source:
        return ""
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    return quote.strip() if norm(quote) in norm(source) else ""


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
