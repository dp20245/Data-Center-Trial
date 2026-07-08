"""
dc_dashboard.py  —  deterministic "Dashboard" tab (no AI, always works).

Computes the heatmap grids (geo×layer, policy, commercial), whitespace/market-entry
targets, top prospects and areas of emphasis from SS1-SS5 + Entities. Heatmap NUMBERS
are computed here (never AI-generated) and rendered with a color scale. compute()
returns the structures so dc_ai reuses them as grounded context.
"""
import os
import re
import json
from collections import Counter
from datetime import datetime, timezone

import dc_config as dc

TREND_PATH = os.path.join(os.path.dirname(__file__), "dc_trend.json")


def _ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _has(cell, token):
    return token.lower() in (cell or "").lower()


def _geo_of(row):
    return row.get("geo") or row.get("counterparty_region", "") or ""


def _split(cell):
    return [x.strip() for x in (cell or "").split(";") if x.strip()]


def _ev_ids(p):
    return [e.strip() for e in (p.get("top_evidence_ids") or "").split(",") if e.strip()]


def _within(dstr, days):
    try:
        d = datetime.strptime((dstr or "")[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days <= days
    except Exception:
        return False


def _index(ss1, ss2, ss3, ss4):
    """id/accession -> (url, date, kind) across all evidence tabs, for links + trend."""
    url, date, kind = {}, {}, {}

    def put(i, u, d, k):
        if i:
            url[i], date[i], kind[i] = u or "", (d or "")[:10], k

    for r in ss1:
        put(r.get("id"), r.get("url"), r.get("date"), "news")
    for r in ss2:
        put(r.get("id"), r.get("url"), r.get("date"), "policy")
    for r in ss3:
        put(r.get("accession"), r.get("url"), r.get("filed_date"), "filing")
    for r in ss4:
        put(r.get("id"), r.get("url"), r.get("observed_date"), r.get("signal_type") or "osint")
    return url, date, kind


def _load_trend():
    try:
        with open(TREND_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"operators": {}}


def _save_trend(prospects):
    ops = {p["company"]: {"score": p.get("score"), "ev_ids": _ev_ids(p)} for p in prospects}
    with open(TREND_PATH, "w", encoding="utf-8") as f:
        json.dump({"updated": _ts(), "version": dc.SCORING_VERSION, "operators": ops},
                  f, ensure_ascii=False, separators=(",", ":"))


def _score_why(p):
    """Break the Signal Score into its four weighted point-contributions (sums to score)."""
    import dc_score
    W = dc_score.WEIGHTS
    mom = float(p.get("momentum") or 0)
    pol = int(p.get("policy_tailwind") or 0)
    par = int(p.get("partnership_strength") or 0)
    geo = 1.0 if "india" in (p.get("geo") or "").lower() else (0.5 if p.get("geo") else 0.0)
    m = 100 * W["momentum"] * min(mom, 10) / 10
    g = 100 * W["geo"] * geo
    d = 100 * W["partner"] * min(par, 5) / 5
    po = 100 * W["policy"] * min(pol, 5) / 5
    gtag = "IN" if geo == 1.0 else "GCC" if geo else "—"
    s = f"momentum {mom:.1f}→{m:.0f} · geo {gtag}→{g:.0f} · {par} deals→{d:.0f} · {pol} policy→{po:.0f}"
    if p.get("is_foreign"):
        s += " · foreign"
    if p.get("deal_value"):
        s += f" · {p['deal_value']}"
    return s


def compute(tabs):
    ss1, ss2, ss3, ss4, ss5 = (tabs.get(k, []) for k in ("ss1", "ss2", "ss3", "ss4", "ss5"))
    markets, layers = dc.MARKETS, list(dc.LAYERS)
    ptypes = list(dc.POLICY_GENUINE_CLASSES)   # R5: real classes; commentary excluded

    geo_hm = {m: {l: 0 for l in layers} for m in markets}
    for r in ss1 + ss3 + ss4:
        g, ls = _geo_of(r), _split(r.get("layer", ""))
        for m in markets:
            if _has(g, m):
                for l in layers:
                    if l in ls:
                        geo_hm[m][l] += 1

    policy_hm = {m: {t: 0 for t in ptypes} for m in markets}
    for r in ss2:
        g = _geo_of(r)
        t = (r.get("policy_class") or "").strip()
        if not t:                                  # legacy rows: classify on the fly
            import dc_ingest
            t = dc_ingest.classify_policy(r.get("title"), r.get("summary"))
        if t not in ptypes:                        # market-commentary et al: excluded
            continue
        for m in markets:
            if _has(g, m):
                policy_hm[m][t] += 1

    comm_hm = {l: {m: 0 for m in markets} for l in layers}
    for r in ss3 + ss4:
        g, ls = _geo_of(r), _split(r.get("layer", ""))
        for m in markets:
            if _has(g, m):
                for l in ls:
                    if l in comm_hm:
                        comm_hm[l][m] += 1

    # --- movement + actionable enrichment (per operator) ---
    ev_url, ev_date, ev_kind = _index(ss1, ss2, ss3, ss4)
    trend_all = _load_trend()
    trend = trend_all.get("operators", {})
    version_reset = trend_all.get("version") != dc.SCORING_VERSION   # formula changed -> reset Δ
    gcc = [m for m in markets if m != "India"]

    def _resolved(status):
        return status not in ("unresolved", "", None)

    # TAG play now derives from expansion_stage (dc_presence) — NOT "no MCA match = entry",
    # which mislabeled established players. Falls back to the old rule only if stage absent.
    _STAGE_PLAY = {"entry": "India market-entry", "scaling": "India expansion",
                   "partnership": "India partnership", "policy_issue": "Govt-affairs hook",
                   "monitor": "Watch"}

    def _tag_play(p):
        # R4 gate: "India market-entry" only when dc_classify granted the whitespace
        # label (direct India signal required). Other labels pass through as the play.
        wl = p.get("whitespace_label")
        if wl:
            return wl if wl != "India expansion" else "India expansion"
        st = p.get("expansion_stage")
        if st in _STAGE_PLAY:
            return _STAGE_PLAY[st]
        geo, status = p.get("geo", ""), p.get("india_status", "")   # fallback (no presence data)
        in_gcc = any(_has(geo, m) for m in gcc)
        if not _resolved(status) and in_gcc and not _has(geo, "India"):
            return "India market-entry"
        if _resolved(status) and (int(p.get("partnership_strength") or 0) > 0
                                  or float(p.get("momentum") or 0) >= 3):
            return "India partnership"
        if int(p.get("policy_tailwind") or 0) > 0:
            return "Govt-affairs hook"
        return "Watch"

    def _why_now(p, fresh):
        if int(p.get("partnership_strength") or 0) > 0 and _within(p.get("last_signal", ""), 60):
            return f"fresh filing {p.get('last_signal')}"
        if fresh > 0:
            return f"{fresh} new signals ≤7d"
        if int(p.get("policy_tailwind") or 0) > 0:
            return "policy activity"
        return f"recent news {p.get('last_signal') or '—'}"

    enriched = []
    for r in ss5:
        p = dict(r)
        ids = _ev_ids(p)
        fresh = sum(1 for i in ids if _within(ev_date.get(i, ""), 7))
        kinds = Counter(ev_kind.get(i, "?") for i in ids)
        p["signals"] = " · ".join(f"{n} {k}" for k, n in kinds.most_common()) or "—"
        p["fresh_7d"] = fresh
        p["link_url"] = next((ev_url[i] for i in ids if ev_url.get(i)), "")
        p["link_id"] = next((i for i in ids if ev_url.get(i)), "")   # for descriptive evidence label
        sc = float(p.get("score") or 0)
        p["signal_band"] = "Strong" if sc >= 60 else "Moderate" if sc >= 40 else "Weak"
        p["tier"] = p["signal_band"]   # back-compat alias (T1/T2/T3 now means SOURCE tier only)
        p["tag_play"] = _tag_play(p)
        p["why_now"] = _why_now(p, fresh)
        pr = trend.get(p.get("company"))
        if version_reset:
            p["score_delta"], p["new_ev"] = "reset", len(ids)
        elif pr is None:
            p["score_delta"], p["new_ev"] = "new", len(ids)
        else:
            p["score_delta"] = round(float(p.get("score") or 0) - float(pr.get("score") or 0), 1)
            prev = set(pr.get("ev_ids", []))
            p["new_ev"] = sum(1 for i in ids if i not in prev)
        enriched.append(p)

    def _is_whitespace(p):
        if p.get("role") == "Noise":           # Phase 4a: Noise never surfaces as a target
            return False
        pres = p.get("india_presence")
        if pres:                               # presence known: not-yet-established = target
            return pres in ("announced", "no_known_presence", "unknown")
        return not _resolved(p.get("india_status", ""))   # fallback (no presence data)

    whitespace = [p for p in enriched if p.get("company") and _is_whitespace(p)]
    prospects = enriched[:10]
    movers = sorted(enriched,
                    key=lambda p: p["score_delta"] if isinstance(p["score_delta"], (int, float)) else 999,
                    reverse=True)

    def _total(m):
        return sum(geo_hm[m].values())
    hottest = max(markets, key=_total) if markets else ""
    hot_layer = max(layers, key=lambda l: geo_hm[hottest][l]) if hottest else ""
    policy_top = max(markets, key=lambda m: sum(policy_hm[m].values())) if markets else ""
    top_mom = max(enriched, key=lambda r: float(r.get("momentum") or 0), default={})
    real_movers = [p for p in movers
                   if isinstance(p.get("score_delta"), (int, float)) and p["score_delta"] != 0]
    if real_movers:
        mv = real_movers[0]
        d = mv["score_delta"]
        mover_line = (f"Top mover this run: {mv.get('company', '—')} "
                      f"({'+' if d > 0 else ''}{d} score, {mv.get('new_ev', 0)} new signals)")
    else:
        mover_line = "No material mover this run (scores flat / new / baseline reset)"
    emphasis = [
        f"Hottest market: {hottest} ({hot_layer}) — {_total(hottest)} signals",
        f"Whitespace (not-yet-established India targets): {len(whitespace)} operators",
        f"Strongest policy tailwind: {policy_top} — {sum(policy_hm[policy_top].values())} items",
        f"Top momentum: {top_mom.get('company', '—')} ({top_mom.get('momentum', '')})",
        mover_line,
    ]
    foreign = [p for p in enriched if p.get("is_foreign")]
    if foreign:
        tf = max(foreign, key=lambda p: float(p.get("score") or 0))
        sz = f" · {tf['deal_value']}" if tf.get("deal_value") else ""
        emphasis.append(f"Foreign hyperscalers active on India: {len(foreign)} "
                        f"(top {tf.get('company', '—')}{sz})")
    return {"markets": markets, "layers": layers, "ptypes": ptypes,
            "geo_hm": geo_hm, "policy_hm": policy_hm, "comm_hm": comm_hm,
            "whitespace": whitespace, "prospects": prospects, "movers": movers,
            "emphasis": emphasis}


def _gradient_reqs(ss, ws, ranges):
    """Delete any existing conditional-format rules on the sheet, then add a
    white->red gradient over each heatmap matrix range (r0,c0,nrows,ncols)."""
    sid = ws.id
    existing = 0
    try:
        meta = ss.fetch_sheet_metadata()
        for sh in meta.get("sheets", []):
            if sh.get("properties", {}).get("sheetId") == sid:
                existing = len(sh.get("conditionalFormats", []) or [])
    except Exception:
        pass
    reqs = [{"deleteConditionalFormatRule": {"sheetId": sid, "index": 0}}
            for _ in range(existing)]
    for (r0, c0, nr, nc) in ranges:
        reqs.append({"addConditionalFormatRule": {"index": 0, "rule": {
            "ranges": [{"sheetId": sid, "startRowIndex": r0, "endRowIndex": r0 + nr,
                        "startColumnIndex": c0, "endColumnIndex": c0 + nc}],
            "gradientRule": {
                "minpoint": {"color": {"red": 1, "green": 1, "blue": 1}, "type": "MIN"},
                "maxpoint": {"color": {"red": 0.86, "green": 0.2, "blue": 0.2}, "type": "MAX"}}}}})
    return reqs


def write(ss, c, register=None):
    import dc_sheets
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    grid, hm_ranges = [], []

    def add(row=None):
        grid.append(row or [])

    add([f"DATACENTRE INTELLIGENCE — DASHBOARD   (updated {ts})"])
    add()
    add(["AREAS OF EMPHASIS"])
    for e in c["emphasis"]:
        add(["• " + e])
    add()

    def heatmap(title, rowlabels, collabels, getter):
        add([title])
        add([""] + collabels)
        first = len(grid)            # 0-indexed row of first data row
        for rl in rowlabels:
            add([rl] + [getter(rl, cl) for cl in collabels])
        hm_ranges.append((first, 1, len(rowlabels), len(collabels)))
        add()

    heatmap("GEOGRAPHIC HEATMAP — signals by market × layer",
            c["markets"], c["layers"], lambda m, l: c["geo_hm"][m][l])
    heatmap("POLICY HEATMAP — SS2 items by market × type",
            c["markets"], c["ptypes"], lambda m, t: c["policy_hm"][m][t])
    heatmap("COMMERCIAL HEATMAP — filings+jobs+facilities by layer × market",
            c["layers"], c["markets"], lambda l, m: c["comm_hm"][l][m])

    def _link(url):
        u = (url or "").replace('"', "")
        return f'=HYPERLINK("{u}","open")' if u else ""

    def _source(row):        # descriptive "Publisher — date" link via the Evidence Register
        if register and row.get("link_id"):
            import dc_evidence
            return dc_evidence.hyperlink(row["link_id"], register)
        return _link(row.get("link_url"))

    def _delta(p):
        d = p.get("score_delta")
        return "new" if d == "new" else (f"+{d}" if isinstance(d, (int, float)) and d > 0 else str(d))

    add(["WHITESPACE — NOT-YET-ESTABLISHED INDIA TARGETS"])
    add(["company", "tag_play", "india_presence", "geo", "Signal Score", "why_now", "source"])
    for w in c["whitespace"]:
        add([w["company"], w.get("tag_play", ""), w.get("india_presence", ""), w.get("geo", ""),
             w.get("score", ""), w.get("why_now", ""), _source(w)])
    add()
    add(["TOP PROSPECTS (SS5) — Signal Score + actionability"])
    add(["signal band", "company", "tag_play", "Signal Score", "score explanation", "Δ", "new",
         "india_presence", "expansion_stage", "why_now", "signals", "last_signal", "source"])
    for p in c["prospects"]:
        add([p.get("signal_band", ""), p.get("company", ""), p.get("tag_play", ""), p.get("score", ""),
             _score_why(p), _delta(p), p.get("new_ev", ""),
             p.get("india_presence", ""), p.get("expansion_stage", ""),
             p.get("why_now", ""), p.get("signals", ""), p.get("last_signal", ""),
             _source(p)])

    ws = dc_sheets.get_tab(ss, dc.DASHBOARD_TAB, ["Dashboard"])
    dc_sheets._retry(ws.clear)
    dc_sheets._retry(ws.update, "A1", grid, value_input_option="USER_ENTERED")
    try:
        reqs = _gradient_reqs(ss, ws, hm_ranges)
        if reqs:
            dc_sheets._retry(ss.batch_update, {"requests": reqs})
    except Exception as e:
        print(f"  [dashboard] heatmap coloring skipped: {e}")
    # Signal Score legend, top-right (G3) — right of the emphasis bullets, above the heatmaps.
    guide = [
        ["SIGNAL SCORE GUIDE"],
        ["Signal Score 0–100 = Momentum 35% + India/GCC relevance 25% + Verified partnerships 20% + Company-linked policy 20%"],
        ["Signal band: Strong ≥60 · Moderate 40–59 · Weak <40  (signal strength, NOT 'act now'). T1/T2/T3 = SOURCE tiers (Evidence Register)"],
        [f"Δ = change vs last run, same scoring version ({dc.SCORING_VERSION}) · 'new' = first seen · 'reset' = formula changed"],
        ["India presence ≠ MCA match: established / announced / no-known-presence / unknown"],
        ["'score explanation' column = each component's points for that company"],
    ]
    try:
        dc_sheets._retry(ws.update, "G3", guide, value_input_option="RAW")
    except Exception as e:
        print(f"  [dashboard] score guide skipped: {e}")
    _save_trend(c["movers"])             # advance baseline (all operators) after a rendered run
    return len(grid)


def _selfcheck():
    """Offline check of tag_play routing + Δ math (no sheet, no network)."""
    ss1 = [{"id": "n1", "url": "http://x/n1", "date": "2026-06-29", "title": "Khazna India push", "geo": "India", "layer": "Colo"}]
    ss3 = [{"accession": "a1", "url": "http://x/a1", "filed_date": "2026-06-28", "filer": "Yotta", "counterparty_region": "India"}]
    ss4 = [{"id": "j1", "url": "http://x/j1", "observed_date": "2026-06-27", "signal_type": "jobs", "actor": "Yotta", "geo": "India"}]
    ss5 = [
        {"company": "Khazna", "india_status": "unresolved", "geo": "UAE", "score": 55,
         "momentum": 4, "partnership_strength": 0, "policy_tailwind": 0, "last_signal": "2026-06-29", "top_evidence_ids": "n1"},
        {"company": "Yotta", "india_status": "active", "geo": "India", "score": 62,
         "momentum": 5, "partnership_strength": 2, "policy_tailwind": 1, "last_signal": "2026-06-28", "top_evidence_ids": "a1, j1"},
    ]
    tabs = {"ss1": ss1, "ss2": [], "ss3": ss3, "ss4": ss4, "ss5": ss5, "entities": []}
    global _load_trend
    orig = _load_trend
    # include the current scoring version so version_reset is False and Δ math is exercised
    _load_trend = lambda: {"version": dc.SCORING_VERSION,                 # noqa: E731
                           "operators": {"Yotta": {"score": 60, "ev_ids": ["a1"]}}}
    try:
        c = compute(tabs)
    finally:
        _load_trend = orig
    by = {p["company"]: p for p in c["movers"]}
    assert by["Khazna"]["tag_play"] == "India market-entry", by["Khazna"]["tag_play"]  # fallback path
    assert by["Yotta"]["tag_play"] == "India partnership", by["Yotta"]["tag_play"]
    assert by["Khazna"]["score_delta"] == "new", by["Khazna"]["score_delta"]
    assert by["Yotta"]["score_delta"] == 2.0, by["Yotta"]["score_delta"]   # 62 - 60
    assert by["Yotta"]["new_ev"] == 1, by["Yotta"]["new_ev"]               # j1 is new, a1 seen
    assert by["Yotta"]["signal_band"] == "Strong" and by["Khazna"]["signal_band"] == "Moderate"
    assert by["Yotta"]["link_url"] == "http://x/a1", by["Yotta"]["link_url"]
    # expansion_stage-driven tag_play mapping
    assert _tag_play_probe({"expansion_stage": "scaling"}) == "India expansion"
    assert _tag_play_probe({"expansion_stage": "entry"}) == "India market-entry"
    # score_explanation components sum to the score (max inputs -> 35+25+20+20 = 100)
    full = {"momentum": 10, "policy_tailwind": 5, "partnership_strength": 5, "geo": "India", "score": 100}
    parts = [int(x) for x in re.findall(r"→(\d+)", _score_why(full))]
    assert sum(parts) == 100, parts
    print("dc_dashboard self-check: OK")


def _tag_play_probe(p):
    """Expose the stage->play mapping for the self-check (mirrors compute._tag_play)."""
    return {"entry": "India market-entry", "scaling": "India expansion",
            "partnership": "India partnership", "policy_issue": "Govt-affairs hook",
            "monitor": "Watch"}.get(p.get("expansion_stage"), "Watch")


if __name__ == "__main__":
    _selfcheck()
