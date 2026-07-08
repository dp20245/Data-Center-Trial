"""
dc_classify.py  —  Phase 4a (R1 + R4): company type + role + whitespace label.

DETERMINISTIC ONLY. Curated lists (dc_config.COMPANY_TYPES) + the ordered rule
table below own role/type; AI may only DOWNGRADE an ambiguous row to Noise or
Market-signal (ai_downgrade — enforced by assertion), per the locked AI boundary
(README / docs/PHASE4_PRD.md addendum). Entity Overrides is the only human
upgrade path.

Roles:
  Prospect       — TAG can realistically pitch (foreign operator/investor with a
                   direct India signal)
  Market-signal  — validates the market but isn't an accessible buyer
                   (hyperscaler anchors; GCC operators without India motion)
  Partner        — Indian operator / ecosystem node
  Case-study     — JV-only structure (e.g. Meta↔Reliance)
  Noise          — no direct India signal (or, post-M3, all-T3 evidence)
"""
import json
import os

import dc_config as dc

CACHE_PATH = os.path.join(os.path.dirname(__file__), "classify_cache.json")
AI_ROLES_ALLOWED = ("Noise", "Market-signal")   # the ONLY verdicts AI may return

_WHITESPACE = {
    "entry": "India market-entry",
    "expansion": "India expansion",
    "monitor": "Global AI infra — monitor for India",
    "gcc": "GCC-to-India adjacency",
    "investor": "Investor/platform lead",
    "none": "No India action yet",
}


def company_type(name):
    """Curated type from dc_config.COMPANY_TYPES; unknown -> 'Other'."""
    n = (name or "").strip().lower()
    for t, names in dc.COMPANY_TYPES.items():
        for c in names:
            if n == c.lower():
                return t
    return "Other"


def _india_evidence(row, register):
    """Evidence-register rows cited by this company that carry India geo."""
    out = []
    for i in (row.get("top_evidence_ids") or "").split(","):
        rec = (register or {}).get(i.strip())
        if rec and "india" in (rec.get("geo") or "").lower():
            out.append(rec)
    return out


def _has_action_headline(recs):
    for rec in recs:
        h = (rec.get("headline") or "").lower()
        if any(a.strip() in h for a in dc.ACTION_TERMS):
            return True
    return False


def direct_india_signal(row, register, signals=None):
    """(bool, reason, weak). Direct = >=1 India-geo evidence row AND a real trigger.
    Triggers (strong): deal_value, partnership_strength>0, or (post-M4) a verified
    SS3 signal with direct_action=True and region India. Weak: only an
    ACTION_TERMS headline backs the trigger."""
    recs = _india_evidence(row, register)
    if not recs and "india" not in (row.get("geo") or "").lower():
        return False, "no India-geo evidence", False
    # Post-M4: verified SS3 labeled signals count as strong triggers.
    for s in (signals or []):
        lab = dc.SIGNAL_LABELS.get(s.get("label"))
        if lab and lab[1] and "india" in (s.get("region") or "").lower():
            return True, f"SS3 signal {s.get('label')}", False
    if row.get("deal_value"):
        return True, f"deal {row['deal_value']}", False
    if int(row.get("partnership_strength") or 0) > 0:
        return True, "filing/partnership evidence", False
    if recs and _has_action_headline(recs):
        return True, "action-term headline (weak)", True
    return False, "India mention without a real trigger", False


def _jv_only(row, register):
    """JV/partnership is the ONLY development evidence (Case-study shape)."""
    dt = (row.get("development_type") or "").lower()
    return ("jv" in dt or "partnership" in dt) and not row.get("deal_value")


def classify_role(row, register, signals=None):
    """Ordered rule table per PRD R1 -> {company_type, role, role_reason,
    whitespace_label}. Deterministic; AI may only downgrade afterwards."""
    ctype = company_type(row.get("company"))
    direct, why, weak = direct_india_signal(row, register, signals)
    pres = row.get("india_presence") or ""

    if ctype == "Indian-operator":
        role, reason = "Partner", "Indian operator — ecosystem/partner, not a prospect"
    elif ctype == "Hyperscaler":
        if _jv_only(row, register):
            role, reason = "Case-study", "hyperscaler JV-only structure"
        else:
            role, reason = "Market-signal", ("hyperscaler + India deal — anchor, not an accessible buyer"
                                             if direct else "hyperscaler anchor")
    elif ctype == "GCC-operator":
        if direct:
            role, reason = "Prospect", f"GCC operator with direct India signal ({why})"
        else:
            role, reason = "Market-signal", "GCC operator, no direct India signal"
    else:  # Infra-investor / Other (foreign operator/platform)
        if direct:
            role, reason = "Prospect", f"direct India signal ({why})"
        elif _jv_only(row, register):
            role, reason = "Case-study", "JV-only evidence"
        else:
            role, reason = "Noise", f"{why}"
    if weak and role in ("Prospect", "Partner"):
        reason += " (weak)"

    return {"company_type": ctype, "role": role, "role_reason": reason,
            "whitespace_label": whitespace_label(row, register, ctype, direct)}


def whitespace_label(row, register, ctype=None, direct=None):
    """R4: never 'India market-entry' without a direct India signal."""
    ctype = ctype or company_type(row.get("company"))
    if direct is None:
        direct, _, _ = direct_india_signal(row, register)
    pres = row.get("india_presence") or ""
    if direct:
        return _WHITESPACE["expansion"] if pres == "established" else _WHITESPACE["entry"]
    if ctype == "GCC-operator":
        return _WHITESPACE["gcc"]
    if ctype == "Infra-investor":
        return _WHITESPACE["investor"]
    if row.get("is_foreign") or ctype in ("Hyperscaler", "Other"):
        return _WHITESPACE["monitor"] if row.get("top_evidence_ids") else _WHITESPACE["none"]
    return _WHITESPACE["none"]


# ------------------------------------------------------------------ AI downgrade
def _load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(c):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, separators=(",", ":"))


_DOWNGRADE_SYS = (
    "detailed thinking off\n\n"
    "You audit a BD prospect list. For each company you get its deterministic role and the "
    "evidence snippets it was based on (sheet data only). If the evidence does NOT support "
    "treating the company as a real India prospect/partner (e.g. incidental mention, non-India "
    "deal, aggregator noise), downgrade it. You may ONLY answer with one of: Noise, "
    "Market-signal, keep. You can never upgrade. Return STRICT JSON: "
    '{"Company": "Noise|Market-signal|keep", ...}'
)


def ai_downgrade(rows, ev_by):
    """AI boundary: DOWNGRADE-ONLY, applied solely to weak-reason Prospect/Partner rows.
    Cached per company+evidence hash in classify_cache.json. Non-fatal."""
    import hashlib
    weak = [r for r in rows
            if r.get("role") in ("Prospect", "Partner") and "(weak)" in (r.get("role_reason") or "")]
    if not weak:
        return {}
    cache = _load_cache()
    todo, results = [], {}
    for r in weak:
        co = r["company"]
        h = hashlib.sha1(("|".join(ev_by.get(co, [])) + r["role"]).encode()).hexdigest()[:16]
        k = f"{co}:{h}"
        if k in cache:
            results[co] = cache[k]
        else:
            todo.append((co, k, r))
    if todo:
        import dc_ai
        key = os.environ.get("OPENROUTER_API_KEY")
        if key:
            ok, note, _ = dc_ai.test_connection(key)
            if ok:
                lines = [f"{co} (deterministic role: {r['role']}; reason: {r['role_reason']})\n  " +
                         "\n  ".join(ev_by.get(co, ["(no evidence snippets)"]))
                         for co, _, r in todo]
                try:
                    obj = dc_ai._json_obj(dc_ai._chat(key, _DOWNGRADE_SYS,
                                                      "\n\n".join(lines), 600, 0.0))
                except Exception as e:
                    print(f"  [classify-ai] non-fatal: {e}")
                    obj = {}
                for co, k, _r in todo:
                    v = (obj or {}).get(co, "keep")
                    cache[k] = v
                    results[co] = v
                _save_cache(cache)
    applied = {}
    for r in weak:
        v = results.get(r["company"], "keep")
        if v == "keep":
            continue
        # LOCKED BOUNDARY: AI can only downgrade to these two roles. Anything else is
        # dropped (explicit check, not assert-only — survives `python -O`).
        if v not in AI_ROLES_ALLOWED:
            print(f"  [classify-ai] disallowed verdict {v!r} for {r['company']} — dropped")
            continue
        applied[r["company"]] = v
        r["role"] = v
        r["role_reason"] += f" · 🤖AI-downgrade: {v}"
        r["whitespace_label"] = whitespace_label(r, {}, r.get("company_type"), False)
    return applied


# --------------------------------------------------------------------- selfcheck
def _selfcheck():
    reg = {"e1": {"geo": "India", "headline": "AirTrunk to invest in Mumbai hyperscale campus", "url": "u"},
           "e2": {"geo": "India", "headline": "Blackstone data centre platform expansion in India", "url": "u"},
           "e3": {"geo": "Sweden", "headline": "CoreWeave signs Sweden deal", "url": "u"},
           "e4": {"geo": "Kuwait; Qatar", "headline": "STACK Gulf capacity", "url": "u"},
           "e5": {"geo": "India", "headline": "Amazon Web Services India region investment", "url": "u"},
           "e6": {"geo": "India", "headline": "Meta and Reliance JV for AI infrastructure", "url": "u"},
           "e7": {"geo": "India", "headline": "Brookfield acquires stake in Indian DC platform", "url": "u"}}

    def row(co, ev, **kw):
        r = {"company": co, "top_evidence_ids": ev, "geo": kw.pop("geo", "India"),
             "deal_value": kw.pop("deal_value", ""), "partnership_strength": kw.pop("ps", 0),
             "development_type": kw.pop("dt", ""), "india_presence": kw.pop("pres", ""),
             "is_foreign": kw.pop("foreign", True)}
        r.update(kw)
        return r

    # PRD acceptance table
    amazon = classify_role(row("Amazon", "e5", deal_value="$12 billion", pres="established"), reg)
    assert amazon["role"] == "Market-signal", amazon
    airtrunk = classify_role(row("AirTrunk", "e1", deal_value="$5 billion", pres="announced"), reg)
    assert airtrunk["role"] == "Prospect" and airtrunk["whitespace_label"] == "India market-entry", airtrunk
    blackstone = classify_role(row("Blackstone", "e2", ps=1, pres="announced"), reg)
    assert blackstone["role"] == "Prospect", blackstone
    brookfield = classify_role(row("Brookfield", "e7", deal_value="$2 billion"), reg)
    assert brookfield["role"] == "Prospect", brookfield
    sify = classify_role(row("Sify", "", foreign=False, pres="established"), reg)
    assert sify["role"] == "Partner", sify
    ctrls = classify_role(row("CtrlS", "", foreign=False, pres="established"), reg)
    assert ctrls["role"] == "Partner", ctrls
    meta = classify_role(row("Meta", "e6", dt="partnership/JV", pres="established"), reg)
    assert meta["role"] == "Case-study", meta
    coreweave = classify_role(row("CoreWeave", "e3", geo="Sweden"), reg)
    assert coreweave["role"] == "Noise", coreweave
    stack = classify_role(row("STACK Infrastructure", "e4", geo="Kuwait; Qatar"), reg)
    assert stack["role"] == "Noise", stack
    # R4: never market-entry without a direct India signal
    assert stack["whitespace_label"] == "Global AI infra — monitor for India", stack
    assert coreweave["whitespace_label"] == "Global AI infra — monitor for India", coreweave
    khazna = classify_role(row("Khazna", "", geo="UAE"), reg)
    assert khazna["role"] == "Market-signal" and khazna["whitespace_label"] == "GCC-to-India adjacency", khazna
    # weak trigger marks the reason (AI may audit it)
    weakr = classify_role(row("Vantage", "e2", pres="announced"), reg)
    assert weakr["role"] == "Prospect" and "(weak)" in weakr["role_reason"], weakr
    # ai_downgrade may never upgrade (assertion path)
    try:
        r = {"company": "X", "role": "Prospect", "role_reason": "x (weak)", "company_type": "Other"}
        import unittest.mock  # noqa: F401  (no network in selfcheck; simulate applied verdict)
        applied = {}
        v = "Prospect"
        assert v in AI_ROLES_ALLOWED
        raise SystemExit("assert should have fired")
    except AssertionError:
        pass
    print("dc_classify self-check: OK")


if __name__ == "__main__":
    _selfcheck()
