"""
dc_sheets.py  —  Google Sheets writer for the ONE "Datacentre" sheet.

Connects via a service-account JSON in the GOOGLE_SERVICE_ACCOUNT_JSON env var
and the sheet id in DC_SPREADSHEET_ID. Writes to NAMED worksheets (SS1..SS5) and
NEVER creates a new spreadsheet — the tab names + headers are fixed contracts.
"""
import os
import re
import json
import time

import gspread

import dc_config as dc

# PRD §5 shared article schema (SS1).
SS1_HEADER = ["id", "date", "source", "layer", "geo", "title", "url",
              "summary", "sentiment", "entities", "type", "event_id"]


def _retry(fn, *args, **kwargs):
    delay = 5
    for attempt in range(6):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (429, 500, 502, 503, 504) and attempt < 5:
                print(f"  [sheets] transient {code}; waiting {delay}s ...")
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise


def connect():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    gc = gspread.service_account_from_dict(info)
    return gc.open_by_key(os.environ["DC_SPREADSHEET_ID"])


def get_tab(ss, title, header):
    """Get the named worksheet (create only if missing); ensure the header row."""
    try:
        ws = ss.worksheet(title)
        if _retry(ws.row_values, 1) != header:
            _retry(ws.update, "A1", [header], value_input_option="RAW")
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=title, rows=2000, cols=len(header))
        _retry(ws.update, "A1", [header], value_input_option="RAW")
    return ws


def append_ss1(ss, rows):
    """Append SS1 News rows. Returns the count written."""
    if not rows:
        return 0
    ws = get_tab(ss, dc.SS1_NEWS_TAB, SS1_HEADER)
    grid = [[
        r["id"],
        r["date"][:16].replace("T", " "),
        r["source"],
        r["layer"],
        r["geo"],
        r["title"],
        r["url"],
        r["summary"],
        r.get("sentiment", ""),
        r.get("entities", ""),   # raw NER strings later; blank until company spine
        r.get("type", ""),
        r.get("event_id", ""),
    ] for r in rows]
    _retry(ws.append_rows, grid, value_input_option="USER_ENTERED",
           insert_data_option="INSERT_ROWS", table_range="A1")
    return len(grid)
