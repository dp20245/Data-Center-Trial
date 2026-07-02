"""
dc_presence.py  —  separate three things the old code wrongly collapsed into one
`india_status`, which mislabeled established players (AWS/Google/AirTrunk) as
"market-entry" just because MCA didn't resolve a foreign name.

For each SS5 operator we attach (deterministically, evidence-backed):
  entity_match  : matched | unmatched          (MCA legal-entity resolution)
  india_presence: established | announced | no_known_presence | unknown
  expansion_stage: entry | scaling | partnership | policy_issue | monitor
  presence_evidence_url / presence_verified_date  (the proof)

Presence is proven, not assumed: real India facility rows (PeeringDB/OSM), a curated
KNOWN_INDIA_PLAYERS list, or an MCA match with India geo => established. The manual
`Entity Overrides` tab always wins (human-in-the-loop truth).
"""
import os
import json
import hashlib

import dc_config as dc

_KNOWN = {k.lower() for k in dc.KNOWN_INDIA_PLAYERS}
PRESENCE_CACHE = os.path.join(os.path.dirname(__file__), "presence_cache.json")

# AI adjudication — ONLY for ambiguous residual (unknown/no_known_presence). Deterministic
# proven cases (facility row / known list / manual override) are never sent and never
# overridden. Strictly grounded on the supplied evidence; cached; non-fatal.
_ADJUDICATE_SYS = (
    "detailed thinking off\n\n"
    "Classify a company's DATA-CENTER presence in INDIA using ONLY the evidence snippets "
    "given for it — no outside knowledge, no invented facts.\n"
    "india_presence: established (operates/owns DCs in India NOW) | announced (a plan/deal, "
    "not yet operational) | no_known_presence (India-relevant but nothing built/announced) | "
    "unknown (insufficient evidence).\n"
    "expansion_stage: entry | scaling | partnership | policy_issue | monitor.\n"
    "NEVER output 'established' without explicit evidence of operating DCs in India; when the "
    "evidence is thin use unknown + low.\n"
    "Output ONLY a JSON array: "
    '[{"company":"..","india_presence":"..","expansion_stage":"..","confidence":"high|med|low"}]'
)
_OVERRIDE_KEYS = ("entity_match", "india_presence", "expansion_stage",
                  "presence_evidence_url", "verified_date")


def load_overrides(rows):
    """Entity Overrides tab rows -> {company_lower: row}. Tolerant of a missing tab."""
    return {(r.get("company") or "").lower(): r for r in (rows or []) if r.get("company")}


def _india_facilities(company, ss4):
    c = (company or "").lower()
    return [r for r in ss4
            if r.get("signal_type") == "facility-presence"
            and c and c in (r.get("actor") or "").lower()
            and "india" in (r.get("geo") or "").lower()]


def classify(row, ss4, overrides):
    company = row.get("company", "")
    matched = row.get("india_status") not in ("unresolved", "", None)
    entity_match = "matched" if matched else "unmatched"

    facs = _india_facilities(company, ss4)
    known = company.lower() in _KNOWN
    has_india = "india" in (row.get("geo") or "").lower()
    ev = facs[0] if facs else None

    if facs or known or (matched and has_india):
        presence = "established"
    elif row.get("deal_value") or (row.get("is_foreign") and has_india):
        presence = "announced"
    elif has_india:
        presence = "no_known_presence"
    else:
        presence = "unknown"

    mom = float(row.get("momentum") or 0)
    part = int(row.get("partnership_strength") or 0)
    pol = int(row.get("policy_tailwind") or 0)
    if presence in ("no_known_presence", "announced") and (row.get("deal_value") or row.get("is_foreign")):
        stage = "entry"
    elif presence == "established" and (mom >= 3 or row.get("deal_value")):
        stage = "scaling"
    elif part > 0:
        stage = "partnership"
    elif pol > 0:
        stage = "policy_issue"
    else:
        stage = "monitor"

    out = {
        "entity_match": entity_match,
        "india_presence": presence,
        "expansion_stage": stage,
        "presence_evidence_url": (ev.get("url") if ev else ""),
        "presence_verified_date": (ev.get("observed_date") if ev else ""),
    }
    ov = overrides.get(company.lower())
    if ov:                                   # manual truth overrides computed values
        for k in _OVERRIDE_KEYS:
            v = ov.get(k)
            if v:
                out["presence_verified_date" if k == "verified_date" else k] = v
    return out


def _load_presence_cache():
    try:
        with open(PRESENCE_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_presence_cache(c):
    with open(PRESENCE_CACHE, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, separators=(",", ":"))


def ai_adjudicate(rows, evidence_by_company):
    """Grounded AI presence call for AMBIGUOUS rows only. rows: ranked dicts;
    evidence_by_company: {company: [snippets]}. Returns {company: verdict}; {} on any
    failure (caller keeps the deterministic value). Cached by company + evidence hash."""
    import dc_ai
    cache = _load_presence_cache()
    todo = []
    for r in rows:
        co = r.get("company", "")
        ev = evidence_by_company.get(co, [])
        h = hashlib.sha1("|".join(ev).encode("utf-8")).hexdigest()[:12]
        if not (cache.get(co) or {}).get("h") == h:
            todo.append((co, ev, h))
    if todo:
        key = os.environ.get("OPENROUTER_API_KEY")
        if key:
            ok, _, _ = dc_ai.test_connection(key)
            if ok:
                user = "Classify:\n" + "\n".join(
                    json.dumps({"company": co, "evidence": ev[:6]}, ensure_ascii=False)
                    for co, ev, _h in todo)
                try:
                    arr = dc_ai._json_array(dc_ai._chat(key, _ADJUDICATE_SYS, user, 1200, 0.0))
                    byco = {o.get("company"): o for o in arr if isinstance(o, dict)}
                    for co, ev, h in todo:
                        o = byco.get(co)
                        if o:
                            cache[co] = {"h": h, "india_presence": o.get("india_presence"),
                                         "expansion_stage": o.get("expansion_stage"),
                                         "confidence": o.get("confidence")}
                    _save_presence_cache(cache)
                except Exception as e:
                    print(f"  [presence-ai] {e}")
    return {r.get("company"): cache[r["company"]] for r in rows if r.get("company") in cache}


def _selfcheck():
    ss4 = [{"signal_type": "facility-presence", "actor": "CtrlS", "geo": "India",
            "url": "http://x/f1", "observed_date": "2026-06-01"}]
    # AirTrunk: no MCA, no facility row, but KNOWN => established (NOT market-entry)
    air = classify({"company": "AirTrunk", "india_status": "unresolved", "geo": "India",
                    "is_foreign": True, "deal_value": "$5 billion", "momentum": 4}, ss4, {})
    assert air["india_presence"] == "established" and air["expansion_stage"] == "scaling", air
    # CtrlS: India facility row => established
    ctr = classify({"company": "CtrlS", "india_status": "active", "geo": "India",
                    "momentum": 5, "partnership_strength": 2}, ss4, {})
    assert ctr["india_presence"] == "established" and ctr["presence_evidence_url"] == "http://x/f1", ctr
    # Unknown foreign co with a deal but no presence => announced/entry
    new = classify({"company": "SomeNewCo", "india_status": "unresolved", "geo": "India",
                    "is_foreign": True, "deal_value": "$1 billion"}, ss4, {})
    assert new["india_presence"] in ("announced", "no_known_presence") and new["expansion_stage"] == "entry", new
    # Override wins
    ovr = classify({"company": "AWS", "india_status": "unresolved", "geo": "India"}, ss4,
                   load_overrides([{"company": "AWS", "india_presence": "established",
                                    "expansion_stage": "scaling"}]))
    assert ovr["india_presence"] == "established", ovr
    # ai_adjudicate is non-fatal without a key (deterministic value stands)
    os.environ.pop("OPENROUTER_API_KEY", None)
    assert ai_adjudicate([{"company": "X", "top_evidence_ids": ""}], {"X": []}) == {}
    print("dc_presence self-check: OK")


if __name__ == "__main__":
    _selfcheck()
