"""
dc_md.py  —  MD View: a clean, presentation-ready top-slice for leadership. No new logic —
it filters the BD Pipeline to P1/P2 and reformats one tight row per opportunity with a single
clickable evidence link, under a one-line coverage header.
"""
import dc_config as dc
import dc_evidence

MD_HEADER = ["Priority", "Company", "India stage", "Trigger", "Why-now", "TAG wedge", "Evidence"]
_AI_MARK = "🤖AI-draft: "


def build(pipe, link_by_company, register):
    rows = []
    for r in pipe:
        if not str(r.get("Priority", "")).startswith(("P1", "P2")):
            continue
        lid = link_by_company.get(r.get("Company"))
        link = dc_evidence.hyperlink(lid, register) if (lid and register) else r.get("Evidence", "")
        wedge = (r.get("TAG wedge") or "").replace(_AI_MARK, "") or r.get("India stage", "")
        rows.append([r.get("Priority", ""), r.get("Company", ""), r.get("India stage", ""),
                     (r.get("Trigger", "") or "")[:70], r.get("Why-now", ""), wedge, link])
    return rows


def write(ss, rows, header_line):
    import dc_sheets
    ws = dc_sheets.get_tab(ss, dc.MD_VIEW_TAB, MD_HEADER)
    dc_sheets._retry(ws.clear)
    grid = [[header_line], [""], MD_HEADER] + rows
    dc_sheets._retry(ws.update, "A1", grid, value_input_option="USER_ENTERED")  # Evidence = HYPERLINK
    return len(rows)


def _selfcheck():
    reg = {"n1": {"url": "http://x", "publisher": "ET", "date": "2026-07-01"}}
    pipe = [
        {"Priority": "P1 Act now", "Company": "AirTrunk", "India stage": "established/scaling",
         "Trigger": "$5 billion · AirTrunk India", "Why-now": "5GW", "TAG wedge": "🤖AI-draft: expansion",
         "Evidence": "ET — 1 Jul"},
        {"Priority": "P3 Monitor", "Company": "SmallCo", "India stage": "no_known_presence/monitor",
         "Trigger": "activity", "Why-now": "", "TAG wedge": "", "Evidence": ""},
    ]
    rows = build(pipe, {"AirTrunk": "n1"}, reg)
    assert len(rows) == 1 and rows[0][1] == "AirTrunk", rows        # P3 excluded
    assert rows[0][5] == "expansion"                                # marker stripped
    assert rows[0][6].startswith('=HYPERLINK("http://x"'), rows[0][6]
    print("dc_md self-check: OK")


if __name__ == "__main__":
    _selfcheck()
