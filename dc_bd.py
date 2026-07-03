"""
dc_bd.py  —  the actionable layer. Turns ranked operators + presence + evidence into a
BD Pipeline (P1/P2/P3), independent of the Signal Score (a low-score company with a real
recent India deal is still P1). GCC-only operators go to a separate GCC Watch.

Hard columns are deterministic. Soft judgement columns (pain point / TAG wedge / buyer /
intro / next action) are AI-DRAFTED, grounded ONLY on sheet evidence, and every drafted
cell is prefixed "🤖AI-draft: " so the team sees exactly what's model-generated.
"""
import os
import json
import hashlib

import dc_config as dc
import dc_evidence

BD_HEADER = ["Priority", "Company", "Segment", "Trigger", "Why-now", "India stage",
             "Pain point", "TAG wedge", "Public buyer + role", "Intro path", "Confidence",
             "Next action", "Evidence", "Owner", "Status"]
GCC_HEADER = ["company", "geo", "latest signal", "note"]
BD_CACHE = os.path.join(os.path.dirname(__file__), "bd_cache.json")
AI_MARK = "🤖AI-draft: "
_SOFT = [("Pain point", "pain_point"), ("TAG wedge", "tag_wedge"),
         ("Public buyer + role", "public_buyer"), ("Intro path", "intro_path"),
         ("Next action", "next_action")]

_BD_SYS = (
    "detailed thinking off\n\n"
    "You are a TAG (The Asia Group) business-development strategist. For each company you get a "
    "validated Trigger, India stage, and evidence snippets FROM THE SHEET ONLY. Draft five short "
    "fields, grounded ONLY in that data — no outside facts, no invented names or numbers:\n"
    "pain_point (the India challenge the trigger implies), tag_wedge (TAG's specific service: "
    "market-entry / government & regulatory / state land+power coordination / partnerships), "
    "public_buyer (the Indian public/government stakeholder + role, ONLY if implied by the data, "
    "else empty), intro_path (how TAG reaches them; generic if unknown), next_action (one concrete "
    "step). Each field <= 14 words. Output ONLY a JSON array: "
    '[{"company":"..","pain_point":"..","tag_wedge":"..","public_buyer":"..","intro_path":"..","next_action":".."}]'
)


def _india_relevant(r):
    return ("india" in (r.get("geo") or "").lower()
            or r.get("india_presence") not in (None, "", "unknown"))


def _priority(r):
    pres = r.get("india_presence")
    recent_trigger = bool(r.get("deal_value")) or int(r.get("partnership_strength") or 0) > 0
    if pres in ("established", "announced") and recent_trigger:
        return "P1 Act now"
    if _india_relevant(r) and float(r.get("momentum") or 0) >= 3:
        return "P2 Qualify"
    return "P3 Monitor"


def _confidence(r):
    if r.get("deal_value") or int(r.get("partnership_strength") or 0) > 0:
        return "high"
    return "med" if r.get("india_presence") in ("established", "announced") else "low"


def _trigger(r, register):
    ids = [i.strip() for i in (r.get("top_evidence_ids") or "").split(",") if i.strip()]
    head = next((register[i]["headline"][:80] for i in ids
                 if register.get(i) and register[i].get("headline")), "")
    return " · ".join(p for p in (r.get("deal_value"), head) if p) or (r.get("development_type") or "activity")


def build(ranked, register):
    """-> (pipeline_rows, gcc_rows). India-relevant => pipeline; GCC-only => watch."""
    pipeline, gcc = [], []
    for r in ranked:
        if not _india_relevant(r):
            gcc.append({"company": r.get("company"), "geo": r.get("geo", ""),
                        "latest signal": r.get("last_signal", ""),
                        "note": f"GCC-only, no India signal (Signal Score {r.get('score')})"})
            continue
        ev_ids = [i.strip() for i in (r.get("top_evidence_ids") or "").split(",") if i.strip()][:4]
        ev = "; ".join(dc_evidence.label(i, register) for i in ev_ids)
        pipeline.append({
            "Priority": _priority(r), "Company": r.get("company"),
            "Segment": (r.get("layer") or "").split(";")[0].strip() or "General",
            "Trigger": _trigger(r, register),
            "Why-now": r.get("why_now") or r.get("last_signal", ""),
            "India stage": f"{r.get('india_presence', '?')}/{r.get('expansion_stage', '?')}",
            "Pain point": "", "TAG wedge": "", "Public buyer + role": "", "Intro path": "",
            "Confidence": _confidence(r), "Next action": "", "Evidence": ev,
            "Owner": "", "Status": "New",
        })
    order = {"P1 Act now": 0, "P2 Qualify": 1, "P3 Monitor": 2}
    pipeline.sort(key=lambda x: order.get(x["Priority"], 9))
    return pipeline, gcc


def _load_cache():
    try:
        with open(BD_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(c):
    with open(BD_CACHE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, separators=(",", ":"))


def ai_draft(rows, evidence_by_company):
    """Fill the soft columns with grounded, explicitly-marked AI drafts. Non-fatal + cached."""
    import dc_ai
    cache = _load_cache()
    todo = []
    for r in rows:
        co = r["Company"]
        ev = evidence_by_company.get(co, [])
        h = hashlib.sha1(("|".join([r["Trigger"], r["India stage"]] + ev)).encode("utf-8")).hexdigest()[:12]
        r["_h"] = h
        if (cache.get(co) or {}).get("h") != h:
            todo.append((co, r["Trigger"], r["India stage"], ev, h))
    if todo:
        key = os.environ.get("OPENROUTER_API_KEY")
        if key and dc_ai.test_connection(key)[0]:
            user = "Draft for:\n" + "\n".join(
                json.dumps({"company": co, "trigger": tr, "stage": st, "evidence": ev[:5]},
                           ensure_ascii=False) for co, tr, st, ev, _h in todo)
            try:
                arr = dc_ai._json_array(dc_ai._chat(key, _BD_SYS, user, 1800, 0.2))
                byco = {o.get("company"): o for o in arr if isinstance(o, dict)}
                for co, tr, st, ev, h in todo:
                    o = byco.get(co)
                    if o:
                        cache[co] = {"h": h, **{k: o.get(k, "") for _c, k in _SOFT}}
                _save_cache(cache)
            except Exception as e:
                print(f"  [bd-ai] {e}")
    for r in rows:
        v = cache.get(r["Company"]) or {}
        if v.get("h") == r.get("_h"):
            for col, k in _SOFT:
                val = (v.get(k) or "").strip()
                if val:
                    r[col] = AI_MARK + val
        r.pop("_h", None)
    return rows


def write(ss, pipeline, gcc):
    import dc_sheets
    ws = dc_sheets.get_tab(ss, dc.BD_PIPELINE_TAB, BD_HEADER)
    dc_sheets._retry(ws.clear)
    grid = [BD_HEADER] + [[r.get(k, "") for k in BD_HEADER] for r in pipeline]
    dc_sheets._retry(ws.update, "A1", grid, value_input_option="USER_ENTERED")  # Evidence has HYPERLINK-free labels; USER_ENTERED harmless
    gw = dc_sheets.get_tab(ss, dc.GCC_WATCH_TAB, GCC_HEADER)
    dc_sheets._retry(gw.clear)
    ggrid = [GCC_HEADER] + [[r.get(k, "") for k in GCC_HEADER] for r in gcc]
    dc_sheets._retry(gw.update, "A1", ggrid, value_input_option="RAW")
    return len(pipeline), len(gcc)


def _selfcheck():
    reg = {"n1": {"headline": "AirTrunk $5B India DC", "publisher": "ET", "date": "2026-07-01", "url": "http://x"}}
    ranked = [
        {"company": "AirTrunk", "india_presence": "established", "expansion_stage": "scaling",
         "deal_value": "$5 billion", "geo": "India", "layer": "Build; Colo", "momentum": 6,
         "partnership_strength": 0, "score": 57, "top_evidence_ids": "n1", "why_now": "5GW plan"},
        {"company": "Khazna", "india_presence": "unknown", "expansion_stage": "monitor",
         "geo": "GCC; UAE", "layer": "Colo", "momentum": 2, "score": 20, "top_evidence_ids": ""},
        {"company": "SmallCo", "india_presence": "no_known_presence", "expansion_stage": "monitor",
         "geo": "India", "layer": "Colo", "momentum": 1, "partnership_strength": 0, "score": 12,
         "top_evidence_ids": ""},
    ]
    pipe, gcc = build(ranked, reg)
    assert [g["company"] for g in gcc] == ["Khazna"], gcc          # GCC-only routed out
    byco = {r["Company"]: r for r in pipe}
    assert byco["AirTrunk"]["Priority"] == "P1 Act now", byco["AirTrunk"]
    assert byco["SmallCo"]["Priority"] == "P3 Monitor", byco["SmallCo"]
    assert "AirTrunk $5B India DC" in byco["AirTrunk"]["Trigger"]
    assert byco["AirTrunk"]["Evidence"] == "ET — 1 Jul"
    # AI draft marks cells (stub) and stays non-fatal without a key
    os.environ.pop("OPENROUTER_API_KEY", None)
    open(BD_CACHE, "w").write('{}')
    ai_draft(pipe, {"AirTrunk": ["evidence"]})
    assert byco["AirTrunk"]["Pain point"] == "", "no key => soft cols blank"
    os.remove(BD_CACHE)
    print("dc_bd self-check: OK")


if __name__ == "__main__":
    _selfcheck()
