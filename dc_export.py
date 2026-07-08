"""
dc_export.py  —  dashboard data feed. Builds dashboard/data.json from the SAME
in-memory objects dc_pipeline already holds (no extra sheet reads, no network).

Contract: schema v1 (see CONTRACT_KEYS). Fields marked nullable in the plan
(role/type/bd_*/fee_viability/source_tier/policy_class/state) stay None until
their milestone lands; the dashboard renders "—" for them.

Safety rails (public artifact — the repo and Vercel site are world-readable):
- WHITELIST-ONLY: every record is built by explicit field picks, never dict dumps.
- validate() checks required keys/types/caps and runs the sanitation scan; on any
  failure the pipeline logs and SKIPS the write (previous data.json survives).
- _selfcheck() also freezes the sheet writer headers (append-only discipline):
  any insert/rename vs the frozen lists fails offline, before a live write.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

import dc_config as dc

SCHEMA_VERSION = "1.0"
EXPORT_PATH = os.path.join(os.path.dirname(__file__), "dashboard", "data.json")

# Caps (keep data.json < ~3 MB)
CAP_SS1, CAP_SS2, CAP_SS3, CAP_SS4 = 200, 150, 100, 150
CAP_EVENTS, CAP_EVIDENCE, CAP_QUOTE_CHARS = 50, 600, 300

CONTRACT_KEYS = ["schema_version", "sector", "generated_at", "scoring_version",
                 "kpis", "emphasis", "heatmaps", "prospects", "gcc_watch",
                 "md_view", "events", "policy", "disclosures", "osint",
                 "evidence_register", "ai_summary", "health"]

# Frozen writer headers (append-only discipline). A new column is legal ONLY as an
# append: update the frozen list in the same PR. Insert/rename fails _selfcheck.
FROZEN_HEADERS = {
    "ARTICLE_HEADER": ["id", "date", "source", "layer", "geo", "title", "url",
                       "summary", "sentiment", "entities", "type", "event_id"],
    "SS3_HEADER": ["accession", "filed_date", "filer", "cik", "form",
                   "counterparty_region", "deal_type", "layer", "matched_terms",
                   "confidence", "section", "relevance", "evidence", "url"],
    "SS4_HEADER": ["id", "observed_date", "signal_type", "actor", "geo", "layer",
                   "magnitude", "confidence", "url", "excerpt"],
    "SS5_HEADER": ["company", "cin", "india_status", "partner", "development_type",
                   "layer", "geo", "score", "momentum", "policy_tailwind",
                   "india_gcc_relevance", "partnership_strength", "last_signal",
                   "top_evidence_ids",
                   "company_type", "role", "role_reason", "whitespace_label"],
}

# Sanitation: none of these may appear anywhere in the exported JSON text.
_SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{16,}", r"AIza[0-9A-Za-z_\-]{20,}", r"api[_-]?key\s*[=:]\s*[A-Za-z0-9]",
    r"apikey=[A-Za-z0-9]{8,}", r"Bearer\s+[A-Za-z0-9\-_\.]{16,}",
    r"BEGIN (RSA )?PRIVATE KEY", r"service_account",
    r"/Users/[A-Za-z]", r"/home/[a-z]+/", r"[A-Z]:\\\\Users",
]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _f(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def _i(v, default=0):
    try:
        return int(float(v))
    except Exception:
        return default


def _clip(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _ids(csv):
    return [i.strip() for i in (csv or "").split(",") if i.strip()]


# --------------------------------------------------------------------------- build
def build(tabs, computed, register, pipe=None, gcc=None, md_rows=None,
          ai_summary=None, health=None):
    """Pure function over pipeline in-memory objects -> contract dict."""
    ss1 = tabs.get("ss1") or []
    ss2 = tabs.get("ss2") or []
    ss3 = tabs.get("ss3") or []
    ss4 = tabs.get("ss4") or []
    enriched = computed.get("movers") or computed.get("prospects") or []
    pipe = pipe or []
    gcc = gcc or []

    bd_by_co = {(r.get("Company") or ""): r for r in pipe}

    def _prospect(p):
        b = bd_by_co.get(p.get("company"), {})

        def soft(col):
            v = (b.get(col) or "").replace("🤖AI-draft: ", "")
            return v or None
        return {
            "company": p.get("company"),
            "type": p.get("company_type"),            # M2
            "role": p.get("role"),                    # M2
            "whitespace_label": p.get("whitespace_label"),  # M2
            "bd_priority": (b.get("Priority") or None),
            "bd_score": p.get("bd_score"),            # M7
            "bd_factors": p.get("bd_factors"),        # M7
            "fee_viability": p.get("fee_viability"),  # M7
            "signal_score": _f(p.get("score")),
            "signal_band": ("Strong" if _f(p.get("score")) >= 60
                            else "Moderate" if _f(p.get("score")) >= 40 else "Weak"),
            "score_delta": p.get("score_delta"),
            "new_ev": p.get("new_ev"),
            "momentum": _f(p.get("momentum")),
            "policy_tailwind": _i(p.get("policy_tailwind")),
            "partnership_strength": _i(p.get("partnership_strength")),
            "india_presence": p.get("india_presence"),
            "expansion_stage": p.get("expansion_stage"),
            "tag_play": p.get("tag_play"),
            "why_now": p.get("why_now"),
            "deal_value": p.get("deal_value") or None,
            "geo": p.get("geo"),
            "layer": p.get("layer"),
            "is_foreign": bool(p.get("is_foreign")),
            "signals": p.get("signals"),
            "last_signal": p.get("last_signal"),
            "confidence": b.get("Confidence") or None,
            "trigger": b.get("Trigger") or None,
            "india_stage": b.get("India stage") or None,
            "source_tier_mix": p.get("source_tier_mix"),   # M3
            "ai_draft": {"pain_point": soft("Pain point"), "tag_wedge": soft("TAG wedge"),
                         "public_buyer": soft("Public buyer + role"),
                         "intro_path": soft("Intro path"), "next_action": soft("Next action")},
            "evidence_ids": _ids(p.get("top_evidence_ids"))[:8],
            "cin": p.get("cin") or None,
        }

    prospects = [_prospect(p) for p in enriched if p.get("company")]

    # SS1 grouped into events by event_id (newest first)
    ev_groups = {}
    for r in sorted(ss1, key=lambda x: x.get("date") or "", reverse=True)[:CAP_SS1 * 3]:
        eid = r.get("event_id") or f"solo-{r.get('id')}"
        g = ev_groups.setdefault(eid, {"event_id": eid, "layer": r.get("layer"),
                                       "geo": r.get("geo"), "headline": r.get("title"),
                                       "first_seen": r.get("date"), "last_seen": r.get("date"),
                                       "articles": []})
        g["first_seen"] = min(g["first_seen"] or "", r.get("date") or "") or r.get("date")
        g["last_seen"] = max(g["last_seen"] or "", r.get("date") or "")
        if len(g["articles"]) < 12:
            g["articles"].append({"id": r.get("id"), "title": _clip(r.get("title"), 200),
                                  "source": r.get("source"),
                                  "source_tier": r.get("source_tier"),   # M3
                                  "date": r.get("date"),
                                  "url": r.get("url"),
                                  "sentiment": r.get("sentiment") or None})
    events = sorted(ev_groups.values(), key=lambda g: (len(g["articles"]), g["last_seen"] or ""),
                    reverse=True)[:CAP_EVENTS]
    for g in events:
        g["n_articles"] = len(g["articles"])
        g["n_sources"] = len({a["source"] for a in g["articles"] if a.get("source")})

    policy = [{"id": r.get("id"), "date": r.get("date"), "geo": r.get("geo"),
               "policy_class": r.get("policy_class"),   # M3
               "type": r.get("type"), "title": _clip(r.get("title"), 200),
               "source": r.get("source"), "source_tier": r.get("source_tier"),
               "url": r.get("url")}
              for r in sorted(ss2, key=lambda x: x.get("date") or "", reverse=True)[:CAP_SS2]]

    disclosures = [{"accession": r.get("accession"), "filer": r.get("filer"),
                    "form": r.get("form"), "filed_date": r.get("filed_date"),
                    "section": r.get("section"), "region": r.get("counterparty_region"),
                    "deal_type": r.get("deal_type"), "layer": r.get("layer"),
                    "confidence": r.get("confidence"),
                    "relevance": _clip(r.get("relevance"), 200),
                    "evidence": _clip(r.get("evidence"), CAP_QUOTE_CHARS * 4),
                    "signals": r.get("signals"),   # M4 machine-readable labels
                    "url": r.get("url")}
                   for r in sorted(ss3, key=lambda x: x.get("filed_date") or "",
                                   reverse=True)[:CAP_SS3]]

    osint = [{"id": r.get("id"), "date": r.get("observed_date"),
              "signal_type": r.get("signal_type"), "actor": _clip(r.get("actor"), 120),
              "geo": r.get("geo"), "layer": r.get("layer"),
              "magnitude": r.get("magnitude") or None, "confidence": r.get("confidence"),
              "excerpt": _clip(r.get("excerpt"), CAP_QUOTE_CHARS), "url": r.get("url")}
             for r in sorted(ss4, key=lambda x: x.get("observed_date") or "",
                             reverse=True)[:CAP_SS4]]

    # Evidence register: only ids actually referenced by exported objects.
    wanted = set()
    for p in prospects:
        wanted.update(p["evidence_ids"])
    for g in events:
        wanted.update(a["id"] for a in g["articles"] if a.get("id"))
    ev_reg = {}
    for eid in list(wanted)[:CAP_EVIDENCE]:
        r = (register or {}).get(eid)
        if not r:
            continue
        ev_reg[eid] = {"publisher": r.get("publisher"),
                       "source_tier": r.get("source_tier"),   # M3
                       "source_type": r.get("source_type"), "date": r.get("date"),
                       "headline": _clip(r.get("headline"), 180), "url": r.get("url"),
                       "geo": r.get("geo"), "layer": r.get("layer"),
                       "company": r.get("company")}

    md_view = [{"priority": m[0], "account": m[1], "india_stage": m[2], "trigger": m[3],
                "why_now": m[4], "tag_wedge": m[5]}
               for m in (md_rows or []) if len(m) >= 6]

    hm = {"markets": computed.get("markets", []), "layers": computed.get("layers", []),
          "geo": computed.get("geo_hm", {}), "policy": computed.get("policy_hm", {}),
          "commercial": computed.get("comm_hm", {})}

    feeds = {}
    for name, n in (health or {}).items():
        n = _i(n, -1)
        feeds[name] = {"items": max(n, 0),
                       "status": "ok" if n > 0 else ("quiet" if n == 0 else "error")}

    now7 = [p for p in enriched if _i(p.get("fresh_7d"))]
    kpis = {
        "prospects_p1": sum(1 for r in pipe if str(r.get("Priority", "")).startswith("P1")),
        "pipeline_total": len(pipe),
        "new_signals_7d": sum(_i(p.get("fresh_7d")) for p in now7),
        "evidence_total": len(register or {}),
        "events_active": len(events),
        "feeds_live": sum(1 for v in feeds.values() if v["status"] == "ok"),
        "feeds_total": len(feeds),
        "operators_ranked": len(prospects),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "sector": {"key": "datacentre", "name": "Data Centres — India + GCC",
                   "thesis": "Power / land / state-policy / partner-selection, not a cloud-growth story."},
        "generated_at": _now(),
        "scoring_version": dc.SCORING_VERSION,
        "kpis": kpis,
        "emphasis": list(computed.get("emphasis", []))[:8],
        "heatmaps": hm,
        "prospects": prospects,
        "gcc_watch": [{"company": g.get("company"), "geo": g.get("geo"),
                       "latest_signal": g.get("latest signal"), "note": g.get("note")}
                      for g in gcc],
        "md_view": md_view,
        "events": events,
        "policy": policy,
        "disclosures": disclosures,
        "osint": osint,
        "evidence_register": ev_reg,
        "ai_summary": {"status": "ok" if ai_summary else "absent",
                       "generated": _now() if ai_summary else None,
                       "text": ai_summary or None},
        "health": {"feeds": feeds},
        "states": None,   # M6
    }


# ----------------------------------------------------------------------- validate
def validate(data):
    """-> list of problem strings (empty = good). Includes the sanitation scan."""
    problems = []
    for k in CONTRACT_KEYS:
        if k not in data:
            problems.append(f"missing key: {k}")
    if data.get("schema_version") != SCHEMA_VERSION:
        problems.append("bad schema_version")
    for k, cap in (("events", CAP_EVENTS), ("policy", CAP_SS2),
                   ("disclosures", CAP_SS3), ("osint", CAP_SS4)):
        v = data.get(k)
        if not isinstance(v, list):
            problems.append(f"{k} not a list")
        elif len(v) > cap:
            problems.append(f"{k} over cap ({len(v)}>{cap})")
    if not isinstance(data.get("prospects"), list):
        problems.append("prospects not a list")
    for p in data.get("prospects", []):
        if not p.get("company"):
            problems.append("prospect without company")
            break
    blob = json.dumps(data, ensure_ascii=False)
    if len(blob) > 3_500_000:
        problems.append(f"data.json too large ({len(blob)} bytes)")
    for pat in _SECRET_PATTERNS:
        m = re.search(pat, blob)
        if m:
            problems.append(f"sanitation: pattern {pat!r} matched near '{blob[max(0,m.start()-20):m.start()+20]}'")
    return problems


def check_headers():
    """Append-only discipline: frozen header must be a PREFIX of the live one."""
    import dc_sheets
    live = {"ARTICLE_HEADER": dc_sheets.ARTICLE_HEADER, "SS3_HEADER": dc_sheets.SS3_HEADER,
            "SS4_HEADER": dc_sheets.SS4_HEADER, "SS5_HEADER": dc_sheets.SS5_HEADER}
    problems = []
    for name, frozen in FROZEN_HEADERS.items():
        cur = live[name]
        if cur[:len(frozen)] != frozen:
            problems.append(f"{name} changed non-append-only: {cur[:len(frozen)]} != {frozen}")
    return problems


def write(data, path=EXPORT_PATH):
    """Validate + write atomically. -> True if written, False if skipped (non-fatal)."""
    problems = validate(data) + check_headers()
    if problems:
        for p in problems:
            print(f"  [export] BLOCKED: {p}")
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    print(f"  [export] dashboard data.json written ({os.path.getsize(path)} bytes)")
    return True


# ---------------------------------------------------------------------- selfcheck
def _fixture_tabs():
    ss1 = [{"id": "n1", "date": "2026-07-06 09:00", "source": "Reuters", "layer": "Build",
            "geo": "India", "title": "AirTrunk plans Mumbai hyperscale campus",
            "url": "https://reuters.com/x", "summary": "5GW pipeline", "sentiment": "0.4",
            "type": "", "event_id": "EVT-1"},
           {"id": "n2", "date": "2026-07-06 10:00", "source": "ET", "layer": "Build",
            "geo": "India", "title": "AirTrunk India campus reported",
            "url": "https://et.com/x", "summary": "", "sentiment": "0.2",
            "type": "", "event_id": "EVT-1"}]
    ss2 = [{"id": "p1", "date": "2026-07-05", "source": "PIB India", "layer": "Power",
            "geo": "India", "title": "State data centre incentive notified",
            "url": "https://pib.gov.in/x", "summary": "", "type": "legislation"}]
    ss3 = [{"accession": "0001-26-1", "filed_date": "2026-07-01", "filer": "Sify",
            "cik": "1", "form": "20-F", "counterparty_region": "India",
            "deal_type": "capex", "layer": "Colo", "matched_terms": "data center",
            "confidence": "high", "section": "Business", "relevance": "yes — 3 signals",
            "evidence": '[capex-commitment|India] "200 MW capacity"',
            "url": "https://sec.gov/x"}]
    ss4 = [{"id": "j1", "observed_date": "2026-07-04", "signal_type": "job",
            "actor": "AirTrunk", "geo": "India", "layer": "Build", "magnitude": "",
            "confidence": "med", "url": "https://boards.greenhouse.io/x",
            "excerpt": "Head of Land Acquisition, Mumbai"}]
    ss5 = [{"company": "AirTrunk", "cin": "", "india_status": "unresolved", "partner": "",
            "development_type": "", "layer": "Build", "geo": "India", "score": "55",
            "momentum": "4.2", "policy_tailwind": "1", "india_gcc_relevance": "1",
            "partnership_strength": "1", "last_signal": "2026-07-06",
            "top_evidence_ids": "n1, j1", "india_presence": "announced",
            "expansion_stage": "entry", "fresh_7d": 2, "score_delta": 3.1, "new_ev": 2,
            "tag_play": "India market-entry", "why_now": "2 new signals ≤7d",
            "signals": "1 news · 1 osint", "is_foreign": True, "deal_value": "$5 billion"}]
    return {"ss1": ss1, "ss2": ss2, "ss3": ss3, "ss4": ss4, "ss5": ss5, "entities": []}


def _fixture_bundle():
    import dc_dashboard
    import dc_evidence
    tabs = _fixture_tabs()
    computed = dc_dashboard.compute(tabs)
    register = dc_evidence.build_register(tabs, tabs["ss5"])
    pipe = [{"Priority": "P1 Act now", "Company": "AirTrunk", "Segment": "Build",
             "Trigger": "$5 billion · AirTrunk plans Mumbai hyperscale campus",
             "Why-now": "2 new signals ≤7d", "India stage": "announced/entry",
             "Pain point": "🤖AI-draft: power procurement", "TAG wedge": "🤖AI-draft: state navigation",
             "Public buyer + role": "", "Intro path": "", "Confidence": "high",
             "Next action": "", "Evidence": "Reuters — 6 Jul", "Owner": "", "Status": "New"}]
    gcc = [{"company": "Khazna", "geo": "UAE", "latest signal": "2026-06-30",
            "note": "GCC-only, no India signal (Signal Score 20)"}]
    md = [["P1 Act now", "AirTrunk", "announced/entry", "$5 billion", "fresh", "state navigation", "=HYPERLINK(...)"]]
    health = {"Reuters": 2, "PIB India": 1, "DeadFeed": 0}
    return tabs, computed, register, pipe, gcc, md, health


def _selfcheck():
    tabs, computed, register, pipe, gcc, md, health = _fixture_bundle()
    data = build(tabs, computed, register, pipe, gcc, md,
                 ai_summary="EXECUTIVE READ\nfixture", health=health)
    probs = validate(data)
    assert not probs, probs
    assert not check_headers(), check_headers()
    p = data["prospects"][0]
    assert p["company"] == "AirTrunk" and p["signal_band"] == "Moderate", p
    assert p["ai_draft"]["tag_wedge"] == "state navigation"       # marker stripped
    assert p["role"] is None and p["bd_score"] is None            # M2/M7 nullables
    assert data["events"][0]["n_articles"] == 2                   # EVT-1 grouped
    assert data["health"]["feeds"]["DeadFeed"]["status"] == "quiet"
    assert data["kpis"]["prospects_p1"] == 1
    assert "n1" in data["evidence_register"]
    # sanitation catches a planted secret
    bad = json.loads(json.dumps(data))
    bad["emphasis"] = ["api_key=SUPERSECRET123 leaked"]
    assert any("sanitation" in x for x in validate(bad))
    print("dc_export self-check: OK")
    return data


if __name__ == "__main__":
    data = _selfcheck()
    if "--fixture" in sys.argv:                     # local dashboard dev feed
        os.makedirs(os.path.dirname(EXPORT_PATH), exist_ok=True)
        write(data)
