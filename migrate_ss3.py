"""One-shot SS3 schema migration (2026-07-06): clear the SS3 Disclosure tab and rewrite the
new header (adds `section` + `relevance` columns). The daily pipeline then repopulates fresh
so every filing is re-judged under the section-scoped extractor. Run once via migrate.yml,
then this file + workflow can be deleted. Idempotent — safe to re-run."""
import dc_sheets
import dc_config as dc


def main():
    ss = dc_sheets.connect()
    ws = dc_sheets.get_tab(ss, dc.SS3_DISCLOSE_TAB, dc_sheets.SS3_HEADER)
    dc_sheets._retry(ws.clear)
    dc_sheets._retry(ws.update, "A1", [dc_sheets.SS3_HEADER], value_input_option="RAW")
    print(f"SS3 '{dc.SS3_DISCLOSE_TAB}' cleared; header -> {dc_sheets.SS3_HEADER}")


if __name__ == "__main__":
    main()
