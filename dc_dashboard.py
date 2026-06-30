"""
dc_dashboard.py  —  deterministic "Dashboard" tab (no AI, always works).

Computes the heatmap grids (geo×layer, policy, commercial), whitespace/market-entry
targets, top prospects and areas of emphasis from SS1-SS5 + Entities. Heatmap NUMBERS
are computed here (never AI-generated) and rendered with a color scale. compute()
returns the structures so dc_ai reuses them as grounded context.
"""
from datetime import datetime, timezone

import dc_config as dc


def _has(cell, token):
    return token.lower() in (cell or "").lower()


def _geo_of(row):
    return row.get("geo") or row.get("counterparty_region", "") or ""


def _split(cell):
    return [x.strip() for x in (cell or "").split(";") if x.strip()]


def compute(tabs):
    ss1, ss2, ss3, ss4, ss5 = (tabs.get(k, []) for k in ("ss1", "ss2", "ss3", "ss4", "ss5"))
    markets, layers = dc.MARKETS, list(dc.LAYERS)
    ptypes = ["legislation", "regulation", "analysis"]

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
        t = (r.get("type", "") or "").lower()
        t = t if t in ptypes else "analysis"
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

    whitespace = [{"company": r["company"], "geo": r.get("geo", ""),
                   "score": r.get("score", ""), "status": r.get("india_status", "")}
                  for r in ss5
                  if r.get("company") and r.get("india_status", "") in ("unresolved", "")]

    prospects = ss5[:10]

    def _total(m):
        return sum(geo_hm[m].values())
    hottest = max(markets, key=_total) if markets else ""
    hot_layer = max(layers, key=lambda l: geo_hm[hottest][l]) if hottest else ""
    policy_top = max(markets, key=lambda m: sum(policy_hm[m].values())) if markets else ""
    mover = max(ss5, key=lambda r: float(r.get("momentum") or 0), default={})
    emphasis = [
        f"Hottest market: {hottest} ({hot_layer}) — {_total(hottest)} signals",
        f"Whitespace / market-entry targets: {len(whitespace)} operators active with no India entity",
        f"Strongest policy tailwind: {policy_top} — {sum(policy_hm[policy_top].values())} items",
        f"Top momentum: {mover.get('company', '—')} ({mover.get('momentum', '')})",
    ]
    return {"markets": markets, "layers": layers, "ptypes": ptypes,
            "geo_hm": geo_hm, "policy_hm": policy_hm, "comm_hm": comm_hm,
            "whitespace": whitespace, "prospects": prospects, "emphasis": emphasis}


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


def write(ss, c):
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

    add(["WHITESPACE — MARKET-ENTRY TARGETS (active in signals, no India entity)"])
    add(["company", "geo", "score", "india_status"])
    for w in c["whitespace"]:
        add([w["company"], w["geo"], w["score"], w["status"]])
    add()
    add(["TOP PROSPECTS (SS5)"])
    cols = ["company", "cin", "india_status", "score", "momentum", "last_signal", "top_evidence_ids"]
    add(cols)
    for p in c["prospects"]:
        add([p.get(k, "") for k in cols])

    ws = dc_sheets.get_tab(ss, dc.DASHBOARD_TAB, ["Dashboard"])
    dc_sheets._retry(ws.clear)
    dc_sheets._retry(ws.update, "A1", grid, value_input_option="USER_ENTERED")
    try:
        reqs = _gradient_reqs(ss, ws, hm_ranges)
        if reqs:
            dc_sheets._retry(ss.batch_update, {"requests": reqs})
    except Exception as e:
        print(f"  [dashboard] heatmap coloring skipped: {e}")
    return len(grid)
