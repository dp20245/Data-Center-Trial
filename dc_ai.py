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
    "Sections:\n"
    "GEOGRAPHICAL READ — where INDIA activity concentrates (states/layers) + the most India-"
    "relevant GCC movements.\n"
    "POLICY READ — India regulatory/policy tailwinds or risks that create a TAG government-affairs hook.\n"
    "COMMERCIAL READ — which value-chain layers and named operators are moving on/into India.\n"
    "RANKED INDIA OPPORTUNITIES — the top BD plays FOR INDIA, highest-conviction first. For each: "
    "company; why-now; cross-signal reasoning (e.g. active in GCC + no India entity => likely India "
    "entry); TAG play (India market-entry / India government-affairs / India partnership / India "
    "site-selection); evidence ids or CIN."
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

    L += ["", "TOP PROSPECTS (SS5, top 5):"]
    for p in c.get("prospects", [])[:5]:
        L.append(f"  {p.get('company')} | cin={p.get('cin')} | status={p.get('india_status')} "
                 f"| score={p.get('score')} | layer={p.get('layer')} | geo={p.get('geo')} "
                 f"| ev={p.get('top_evidence_ids')}")

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


def call_model(key, user):
    body = json.dumps({
        "model": dc.DC_AI_MODEL, "temperature": 0.2, "max_tokens": dc.AI_MAX_TOKENS,
        "reasoning": {"enabled": False},    # disable reasoning (not just hide it)
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(
        dc.OPENROUTER_BASE + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/dp20245/Data-Center-Trial",
                 "X-Title": "Datacentre BI"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode("utf-8", "ignore"))
    return _clean(d["choices"][0]["message"]["content"])


def _write(ss, header, body):
    import dc_sheets
    ws = dc_sheets.get_tab(ss, dc.AI_SUMMARY_TAB, ["AI Summary"])
    grid = [[header], [""]] + [[ln] for ln in (body or "").split("\n")]
    dc_sheets._retry(ws.clear)
    dc_sheets._retry(ws.update, "A1", grid, value_input_option="RAW")


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
