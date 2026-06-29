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

# PRD §5 shared article schema (SS1 + SS2).
ARTICLE_HEADER = ["id", "date", "source", "layer", "geo", "title", "url",
                  "summary", "sentiment", "entities", "type", "event_id"]
SS1_HEADER = ARTICLE_HEADER  # back-compat
SS3_HEADER = ["accession", "filed_date", "filer", "cik", "form", "counterparty",
              "counterparty_region", "deal_type", "layer", "excerpt", "url"]
SS4_HEADER = ["id", "observed_date", "signal_type", "actor", "geo", "layer",
              "magnitude", "confidence", "url", "excerpt"]
SS5_HEADER = ["company", "partner", "development_type", "layer", "geo", "score",
              "momentum", "policy_tailwind", "india_gcc_relevance",
              "partnership_strength", "last_signal", "top_evidence_ids"]


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


def _append(ws, grid):
    if grid:
        _retry(ws.append_rows, grid, value_input_option="USER_ENTERED",
               insert_data_option="INSERT_ROWS", table_range="A1")
    return len(grid)


def append_articles(ss, tab, rows):
    """SS1/SS2 shared article schema."""
    if not rows:
        return 0
    ws = get_tab(ss, tab, ARTICLE_HEADER)
    grid = [[r["id"], r["date"][:16].replace("T", " "), r["source"], r["layer"],
             r["geo"], r["title"], r["url"], r["summary"], r.get("sentiment", ""),
             r.get("entities", ""), r.get("type", ""), r.get("event_id", "")]
            for r in rows]
    return _append(ws, grid)


def append_ss1(ss, rows):
    return append_articles(ss, dc.SS1_NEWS_TAB, rows)


def append_ss3(ss, rows):
    """SS3 filings sub-schema."""
    if not rows:
        return 0
    ws = get_tab(ss, dc.SS3_DISCLOSE_TAB, SS3_HEADER)
    grid = [[r[k] for k in SS3_HEADER] for r in rows]
    return _append(ws, grid)


def append_ss4(ss, rows):
    """SS4 OSINT sub-schema."""
    if not rows:
        return 0
    ws = get_tab(ss, dc.SS4_OSINT_TAB, SS4_HEADER)
    grid = [[r.get(k, "") for k in SS4_HEADER] for r in rows]
    return _append(ws, grid)


def read_tab(ss, tab):
    """Return tab rows as header-keyed dicts (empty list if tab missing)."""
    try:
        ws = ss.worksheet(tab)
    except gspread.WorksheetNotFound:
        return []
    values = _retry(ws.get_all_values)
    if not values or len(values) < 2:
        return []
    header = values[0]
    return [dict(zip(header, row)) for row in values[1:]]


def write_ss5(ss, rows):
    """Rebuild the SS5 ranked tab (one row per scored development)."""
    ws = get_tab(ss, dc.SS5_RANKED_TAB, SS5_HEADER)
    grid = [SS5_HEADER] + [[r.get(k, "") for k in SS5_HEADER] for r in rows]
    _retry(ws.clear)
    _retry(ws.update, "A1", grid, value_input_option="USER_ENTERED")
    return len(rows)


def dedup_existing(ss, tab, ids, id_col="id"):
    """IDs already present in `tab` (so re-runs don't duplicate append-only rows)."""
    existing = read_tab(ss, tab)
    return {row.get(id_col, "") for row in existing} & set(ids)
