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
    "Output ONLY the four sections below — no preamble, no meta-commentary, no 'we need to' "
    "reasoning, no restating the task. Start directly with 'GEOGRAPHICAL READ'.\n\n"
    "GROUNDING RULE: every company, number, deal, filing, and signal you mention MUST come from "
    "the spreadsheet DATA below — never invent or add ones that are not present. You MAY apply "
    "brief, widely-known background knowledge, but ONLY about entities that already appear in the "
    "DATA, and ONLY to explain why a data signal matters (e.g. what kind of company it is). Mark "
    "any such background with a leading '[context]' tag so it is distinguishable from sheet facts. "
    "If the DATA doesn't support a specific claim, write 'not in data'. When in doubt, stay on the DATA.\n\n"
    "You are a business-development analyst for The Asia Group (TAG). TAG's core business is "
    "helping companies ENTER AND GROW IN INDIA — market entry, government affairs, partnerships, "
    "site selection. Convert this Datacentre intelligence into TAG's best INDIA opportunities. "
    "Use ONLY the DATA provided below (TAG's India + GCC data-center sheet). Do NOT use outside "
    "knowledge, memory, or assumptions. Every claim must cite a company, CIN, or tab/ids; if the "
    "data does not support it, write 'not in data'. Be concise — short, specific bullets, and "
    "name the company every time.\n\n"
    "Lens — always reason toward an INDIA angle:\n"
    "- A company active in the GCC with NO India entity (see WHITESPACE / Entities) is a prime "
    "India MARKET-ENTRY target — flag it explicitly.\n"
    "- An India operator with rising momentum or a fresh filing/partnership is an India "
    "PARTNERSHIP or GOVERNMENT-AFFAIRS target.\n"
    "- Indian policy items (SEBI, PIB, data-localization) are India government-affairs hooks; GCC "
    "policy matters only if it pushes a player toward India.\n"
    "- Hiring spikes or facility presence in Indian states signal India expansion before the news.\n\n"
    "Sections — keep the three READs to 2–4 SHORT lines each:\n"
    "GEOGRAPHICAL READ — where INDIA activity concentrates (states/layers) + the most India-"
    "relevant GCC movements.\n"
    "POLICY READ — India regulatory/policy tailwinds or risks that create a TAG government-affairs hook.\n"
    "COMMERCIAL READ — which value-chain layers and named operators are moving on/into India.\n"
    "RANKED INDIA OPPORTUNITIES — top BD plays FOR INDIA, highest-conviction first. Output ONLY "
    "a pipe-delimited table, one opportunity PER LINE, with EXACTLY these five columns and no "
    "others:\n"
    "Rank | Company | Why-now | TAG play | Evidence\n"
    "Rules: Why-now ≤10 words (the key cross-signal, e.g. 'GCC-active, no India entity'); "
    "TAG play is one of India market-entry / India government-affairs / India partnership / India "
    "site-selection; Evidence = ids or CIN. No prose, no header row, no blank cells, no extra "
    "sentences before or after the table."
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


def compile_context(tabs, c):
    # ponytail: compressed to ~800 tokens; expand sections if model misses signals
    L = ["=== HEATMAPS ===",
         "Geo(market×layer): " + json.dumps(c["geo_hm"]),
         "Policy(market×type): " + json.dumps(c["policy_hm"]),
         "Commercial(layer×market): " + json.dumps(c["comm_hm"])]
    L += ["", "KEY SIGNALS:"] + c["emphasis"]

    ws = c.get("whitespace", [])[:8]
    if ws:
        L += ["", "WHITESPACE(GCC active, no India entity — market-entry targets):"]
        L += [f"  {w['company']} | {w['geo']} | score {w['score']}" for w in ws]

    movers = [p for p in c.get("movers", []) if p.get("score_delta") == "new"
              or (isinstance(p.get("score_delta"), (int, float)) and p["score_delta"] > 0)][:5]
    if movers:
        L += ["", "TOP MOVERS (Δ since last run — validate/refine the play):"]
        for p in movers:
            d = p.get("score_delta")
            dtxt = "new" if d == "new" else f"+{d}"
            L.append(f"  {p.get('company')} | Δ{dtxt} | {p.get('new_ev', 0)} new signals | {p.get('why_now', '')}")

    L += ["", "TOP PROSPECTS (SS5, top 5 — deterministic play is a FLOOR you may override):"]
    for p in c.get("prospects", [])[:5]:
        L.append(f"  {p.get('company')} | {p.get('tier', '')} | play={p.get('tag_play', '')} "
                 f"| status={p.get('india_status')} | score={p.get('score')} | geo={p.get('geo')} "
                 f"| why={p.get('why_now', '')} | ev={p.get('top_evidence_ids')}")

    L += ["", "FILINGS SS3 (top 8):"]
    for r in tabs.get("ss3", [])[:8]:
        L.append(f"  {r.get('filer')} | {r.get('deal_type')} | {r.get('counterparty_region')} "
                 f"| conf={r.get('confidence')} | terms={r.get('matched_terms')}")

    L += ["", "POLICY SS2:"]
    for r in tabs.get("ss2", [])[:12]:
        L.append(f"  {r.get('geo')} | {r.get('type')} | {r.get('title', '')[:100]}")

    india_ents = [r for r in tabs.get("entities", []) if r.get("status") not in ("", None)]
    if india_ents:
        L += ["", "INDIA ENTITIES (resolved):"]
        for r in india_ents[:10]:
            L.append(f"  {r.get('legal_name')} | {r.get('cin')} | {r.get('status')} | {r.get('state')}")

    sig = Counter(r.get("signal_type") for r in tabs.get("ss4", []))
    top_actors = Counter(r.get("actor") for r in tabs.get("ss4", []) if r.get("geo") in ("India", "IN"))
    L += ["", f"OSINT SS4: {json.dumps(dict(sig))}",
          f"Top India actors: {dict(top_actors.most_common(5))}"]

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
    m = re.search(r"(?im)^\s*#*\s*GEOGRAPHICAL READ", text or "")
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
    """Reads render as single-cell text rows; RANKED INDIA OPPORTUNITIES renders as a
    real pipe-split table. Degrades to plain text rows if the model emits no '|'."""
    import re
    rows = [[header], [""]]
    in_table = False
    for ln in (body or "").split("\n"):
        if re.match(r"(?i)^\s*#*\s*RANKED INDIA OPPORTUNITIES", ln):
            rows.append([ln.strip()])
            rows.append(["Rank", "Company", "Why now", "TAG play", "Evidence"])
            in_table = True
            continue
        if in_table and "|" in ln:
            rows.append([c.strip() for c in ln.split("|")])
        else:
            rows.append([ln])            # reads + any non-pipe trailer (e.g. Grounding set)
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
