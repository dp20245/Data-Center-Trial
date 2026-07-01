"""
dc_ai.py  —  grounded "AI Summary" tab via OpenRouter (free Nemotron). Never kills
the pipeline.

Flow per run:
  1. compile a SHEET-ONLY context (computed heatmaps + digests of every tab).
  2. hash it — if unchanged since last success, SKIP the call (protects the daily
     query budget; OpenRouter counts internal reasoning tokens too).
  3. cheap connection + budget test (GET /auth/key, no completion tokens). If it
     fails / no key / budget low -> write "Didn't Work", keep last good summary.
  4. call the model with a strict grounding prompt; on any failure -> "Didn't Work".
  5. write the tab with "Last AI check: <ts>"; cache hash+summary on success.

Reads OPENROUTER_API_KEY. Output is locked to the spreadsheet data only.
"""
import os
import json
import hashlib
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timezone

import dc_config as dc

CACHE_PATH = os.path.join(os.path.dirname(__file__), "ai_cache.json")

SYSTEM = (
    "detailed thinking off\n\n"  # Nemotron switch: no chain-of-thought, answer directly
    "Output ONLY the sections below — no preamble, no meta-commentary, no 'we need to' "
    "reasoning, no restating the task. Start directly with 'EXECUTIVE READ'.\n\n"
    "GROUNDING RULE: every company, number, deal, filing, and signal you mention MUST come from "
    "the spreadsheet DATA below — never invent or add ones that are not present. You MAY apply "
    "brief, widely-known background knowledge, but ONLY about entities that already appear in the "
    "DATA, and ONLY to explain why a data signal matters (e.g. what kind of company it is). Mark "
    "any such background with a leading '[context]' tag so it is distinguishable from sheet facts. "
    "If the DATA doesn't support a specific claim, write 'not in data'. When in doubt, stay on the DATA.\n\n"
    "You are a business-development analyst for The Asia Group (TAG). TAG's core business is "
    "helping companies ENTER AND GROW IN INDIA — market entry, government affairs, partnerships, "
    "site selection. Convert this Datacentre intelligence into TAG's best INDIA opportunities. "
    "Use ONLY the DATA provided below. Do NOT use outside knowledge or assumptions. Name the "
    "company every time and cite evidence ids or CIN.\n\n"
    "Lens — always reason toward an INDIA angle:\n"
    "- A company active in the GCC with NO India entity is a prime India MARKET-ENTRY target.\n"
    "- ownership=FTC/foreign-subsidiary means a foreign parent is ALREADY in India via a sub — "
    "the parent is the market-GROWTH / partnership target; say so.\n"
    "- An India operator with rising momentum or a fresh filing/partnership is an India "
    "PARTNERSHIP or GOVERNMENT-AFFAIRS target.\n"
    "- Indian policy items are India government-affairs hooks; GCC policy matters only if it "
    "pushes a player toward India.\n"
    "- Hiring spikes / facility presence / nearby government tenders in Indian states signal "
    "India expansion before the news — connect them.\n\n"
    "Produce EXACTLY these three sections:\n\n"
    "EXECUTIVE READ — 3–5 short lines: where India activity concentrates (states/layers), the "
    "top India policy hook, the value-chain layers/operators moving on India, and this run's top movers.\n\n"
    "RANKING — a pipe-delimited table, a header row then ONE row per company, highest-conviction "
    "first, EXACTLY these columns:\n"
    "Rank | Company | Tier | Score Δ | India status | TAG play\n"
    "(TAG play ∈ India market-entry / India government-affairs / India partnership / India "
    "site-selection.) No prose around the table.\n\n"
    "COMPANY DOSSIERS — one block per company in the DOSSIER DATA, using ONLY that company's "
    "supplied facts. Format each block EXACTLY as:\n"
    "━ <Legal name> (<CIN or 'no India entity'>) ━\n"
    "Entity: <ownership/listed/inc_year/state/industry — or 'no India entity'>\n"
    "Momentum: score <s> (Δ<d>) · <n> new signals ≤7d · tier <T>\n"
    "Signals: <signal mix + layers + geo/states>\n"
    "Why-now: <the sharpest cross-signal, one line>\n"
    "TAG play: <play> — <one-line rationale>\n"
    "Analysis: 2–4 sentences of grounded cross-signal reasoning (e.g. GCC-active + no India "
    "entity => entry; foreign parent + rising momentum => scale the sub; hiring in a new state "
    "=> site coming). Mark general background with [context].\n"
    "Evidence: <ids or CIN>\n"
)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(c):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, separators=(",", ":"))


def _ev_index(tabs):
    """id/accession -> a short evidence string, across every evidence tab (real text)."""
    idx = {}
    for r in tabs.get("ss1", []) + tabs.get("ss2", []):
        if r.get("id"):
            idx[r["id"]] = f"news/policy: {(r.get('title') or '')[:120]}"
    for r in tabs.get("ss3", []):
        if r.get("accession"):
            idx[r["accession"]] = (f"filing {r.get('form', '')} "
                                   f"[{r.get('deal_type', '')}/{r.get('counterparty_region', '')}]: "
                                   f"{(r.get('evidence') or r.get('matched_terms') or '')[:150]}")
    for r in tabs.get("ss4", []):
        if r.get("id"):
            idx[r["id"]] = f"{r.get('signal_type', '')}: {(r.get('excerpt') or r.get('actor') or '')[:120]}"
    return idx


def compile_context(tabs, c):
    # Brief global block for the EXECUTIVE READ + RANKING, then a deep per-company block.
    L = ["=== HEATMAPS ===",
         "Geo(market×layer): " + json.dumps(c["geo_hm"]),
         "Policy(market×type): " + json.dumps(c["policy_hm"]),
         "Commercial(layer×market): " + json.dumps(c["comm_hm"])]
    L += ["", "KEY SIGNALS:"] + c["emphasis"]

    movers = [p for p in c.get("movers", []) if p.get("score_delta") == "new"
              or (isinstance(p.get("score_delta"), (int, float)) and p["score_delta"] > 0)][:5]
    if movers:
        L += ["", "TOP MOVERS:"]
        for p in movers:
            d = p.get("score_delta")
            dtxt = "new" if d == "new" else f"+{d}"
            L.append(f"  {p.get('company')} | Δ{dtxt} | {p.get('new_ev', 0)} new signals | {p.get('why_now', '')}")

    L += ["", "POLICY SS2:"]
    for r in tabs.get("ss2", [])[:12]:
        L.append(f"  {r.get('geo')} | {r.get('type')} | {r.get('title', '')[:100]}")

    sig = Counter(r.get("signal_type") for r in tabs.get("ss4", []))
    L += ["", f"OSINT SS4 mix: {json.dumps(dict(sig))}"]

    # ---- deep per-company dossier data: 1 block per SS5 company (all 11) ----
    ents = {r.get("cin"): r for r in tabs.get("entities", []) if r.get("cin")}
    evidx = _ev_index(tabs)
    companies = c.get("movers", [])                # full enriched SS5 set
    L += ["", f"=== PER-COMPANY DOSSIER DATA ({len(companies)}) ==="]
    for p in companies:
        e = ents.get(p.get("cin"), {})
        name = e.get("legal_name") or p.get("company")
        d = p.get("score_delta")
        dtxt = "new" if d == "new" else (f"+{d}" if isinstance(d, (int, float)) and d > 0 else str(d))
        L.append(f"\n━ {name} ({p.get('cin') or 'no India entity'}) ━")
        if e:
            L.append(f"  entity: ownership={e.get('ownership', '?')} listed={e.get('listed', '?')} "
                     f"inc_year={e.get('inc_year', '?')} state={e.get('state', '?')} "
                     f"nic={e.get('nic_class', '?')} class={e.get('company_class', '?')} "
                     f"paidup={e.get('paidup_capital', '?')} roc={e.get('roc', '?')}")
        else:
            L.append("  entity: no resolved India entity (MCA) — market-entry candidate")
        L.append(f"  momentum: score={p.get('score')} Δ{dtxt} new≤7d={p.get('fresh_7d', 0)} "
                 f"tier={p.get('tier')} momentum={p.get('momentum')} last={p.get('last_signal')}")
        L.append(f"  profile: layers={p.get('layer')} geo={p.get('geo')} signals=[{p.get('signals', '')}] "
                 f"filings={p.get('partnership_strength', 0)} policy={p.get('policy_tailwind', 0)} "
                 f"status={p.get('india_status')} play={p.get('tag_play')}")
        ids = [i.strip() for i in (p.get("top_evidence_ids") or "").split(",") if i.strip()]
        ev = [f"    - [{i}] {evidx[i]}" for i in ids if i in evidx][:6]
        if ev:
            L += ["  evidence:"] + ev

    return "\n".join(L)


def test_connection(key):
    """Cheap key/budget check — no completion tokens. Returns (ok, note, remaining)."""
    try:
        req = urllib.request.Request(dc.OPENROUTER_BASE + "/auth/key",
                                     headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode("utf-8", "ignore")).get("data", {})
        rem = d.get("limit_remaining")
        if isinstance(rem, (int, float)) and rem <= 0:
            return False, "budget exhausted", rem
        return True, "ok", rem
    except Exception as e:
        return False, str(e), None


def _clean(text):
    """Nemotron can still leak chain-of-thought; keep from the first real section header."""
    import re
    m = re.search(r"(?im)^\s*#*\s*EXECUTIVE READ", text or "")
    return (text[m.start():] if m else (text or "")).strip()


def _chat(key, system, user, max_tokens, temperature=0.2):
    """Low-level OpenRouter chat call — reasoning OFF, returns raw content string."""
    body = json.dumps({
        "model": dc.DC_AI_MODEL, "temperature": temperature, "max_tokens": max_tokens,
        "reasoning": {"enabled": False},    # disable reasoning (not just hide it)
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(
        dc.OPENROUTER_BASE + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/dp20245/Data-Center-Trial",
                 "X-Title": "Datacentre BI"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode("utf-8", "ignore"))
    return d["choices"][0]["message"]["content"]


def call_model(key, user):
    return _clean(_chat(key, SYSTEM, user, dc.AI_MAX_TOKENS))


# --- tender triage: grounded classifier, keyword-pre-gated, non-fatal (dc_osint owns cache) ---
CLASSIFY_SYSTEM = (
    "detailed thinking off\n\n"
    "You are a strict classifier for INDIAN GOVERNMENT DATA-CENTRE PROCUREMENT. For each "
    "tender you get only a title and an organisation name. Use ONLY that text plus basic, "
    "widely-known contextual inference (e.g. 'colocation'/'UPS'/'cooling'/'server farm'/"
    "'hyperscale' relate to data centres). Do NOT use outside data; do NOT invent operators, "
    "numbers, locations, or values. If a field is not stated or clearly inferable FROM THE "
    "TEXT, return null for it.\n\n"
    "is_dc = true ONLY if the tender is genuinely for a data-centre facility, colocation, or "
    "its core infrastructure (power/cooling/UPS/server halls). Generic IT, plain networking "
    "gear, or an unrelated 'server'/'relay' mention => false.\n\n"
    "Output ONLY a JSON array, one object per input, no prose:\n"
    '[{"id":"<id>","is_dc":true,"state":"<Indian state or null>","capacity_mw":<number or null>,'
    '"value_inr":<number or null>,"layer":"<Compute|Cooling|Power|Network|Colo|Build or null>"}]'
)


def _json_array(text):
    """Extract the first JSON array from possibly-wrapped model output."""
    i, j = (text or "").find("["), (text or "").rfind("]")
    return json.loads(text[i:j + 1]) if 0 <= i < j else []


def classify_tenders(candidates):
    """candidates: [{'id','title','org'}] -> {id: {is_dc,state,capacity_mw,value_inr,layer}}.
    Returns {} on no-key / connection-fail / parse-fail (caller falls back to keyword-only)."""
    if not candidates:
        return {}
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {}
    ok, note, _ = test_connection(key)
    if not ok:
        print(f"  [tender-ai] skipped ({note})")
        return {}
    user = "Classify these tenders:\n" + "\n".join(
        json.dumps({"id": c["id"], "title": c["title"], "org": c.get("org", "")}, ensure_ascii=False)
        for c in candidates)
    try:
        arr = _json_array(_chat(key, CLASSIFY_SYSTEM, user, max_tokens=1500, temperature=0.0))
        return {str(o["id"]): o for o in arr if isinstance(o, dict) and o.get("id") is not None}
    except Exception as e:
        print(f"  [tender-ai] {e}")
        return {}


def _render(header, body):
    """Any line with '|' → split into columns (the RANKING table); every other line →
    one text cell (reads + dossier label lines). Pad rectangular. No special-casing."""
    rows = [[header], [""]]
    for ln in (body or "").split("\n"):
        rows.append([c.strip() for c in ln.split("|")] if "|" in ln else [ln])
    w = max(len(r) for r in rows)
    return [r + [""] * (w - len(r)) for r in rows]   # pad rectangular


def _wrap_reqs(ss, ws, ncols):
    sid = ws._properties["sheetId"]
    return [{"repeatCell": {
        "range": {"sheetId": sid, "startColumnIndex": 0, "endColumnIndex": ncols},
        "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
        "fields": "userEnteredFormat.wrapStrategy"}}]


def _write(ss, header, body):
    import dc_sheets
    ws = dc_sheets.get_tab(ss, dc.AI_SUMMARY_TAB, ["AI Summary"])
    grid = _render(header, body)
    dc_sheets._retry(ws.clear)
    dc_sheets._retry(ws.update, "A1", grid, value_input_option="RAW")
    try:
        dc_sheets._retry(ss.batch_update, {"requests": _wrap_reqs(ss, ws, len(grid[0]))})
    except Exception as e:
        print(f"  [ai] wrap formatting skipped: {e}")


def summarize(ss, tabs, computed):
    """Never raises — degrades to 'Didn't Work' on any failure."""
    try:
        cache = load_cache()
        ctx = compile_context(tabs, computed)
        h = hashlib.sha1(ctx.encode("utf-8")).hexdigest()
        last_good = cache.get("summary", "(no prior AI summary yet)")
        last_ts = cache.get("timestamp", "never")

        if cache.get("hash") == h and cache.get("status") == "ok":
            _write(ss, f"AI Summary — cached (data unchanged since {last_ts}) · model {cache.get('model')}",
                   last_good)
            print("  AI Summary -> cached (no change); no call made")
            return

        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            _write(ss, f"⚠️ AI Summary — Didn't Work (no OPENROUTER_API_KEY). Last successful: {last_ts}", last_good)
            print("  AI Summary -> no key; Didn't Work")
            return

        ok, note, rem = test_connection(key)
        if not ok:
            _write(ss, f"⚠️ AI Summary — Didn't Work ({note}). Last successful: {last_ts}. Attempted {_now()}", last_good)
            print(f"  AI Summary -> connection test failed: {note}")
            return

        try:
            summary = call_model(key, ctx)
        except Exception as e:
            _write(ss, f"⚠️ AI Summary — Didn't Work (call failed: {e}). Last successful: {last_ts}. Attempted {_now()}", last_good)
            print(f"  AI Summary -> call failed: {e}")
            return

        known = sorted({r.get("legal_name", "") for r in tabs.get("entities", [])}
                       | {p.get("company", "") for p in computed["prospects"]})
        summary += "\n\n— Grounding set (companies in sheet): " + ", ".join(filter(None, known))
        ts = _now()
        _write(ss, f"AI Summary — Last AI check: {ts} · model {dc.DC_AI_MODEL} · budget left: {rem}", summary)
        cache.update({"hash": h, "summary": summary, "timestamp": ts,
                      "model": dc.DC_AI_MODEL, "status": "ok"})
        save_cache(cache)
        print("  AI Summary -> generated + cached")
    except Exception as e:
        print(f"  [ai] non-fatal error: {e}")
