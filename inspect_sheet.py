"""Read-only sheet inspector — dumps raw cell values of key tabs to stdout so we can
verify what actually rendered (Dashboard layout, G3 guide, score explanations, SS5)."""
import dc_sheets
import dc_config as dc


def main():
    ss = dc_sheets.connect()
    for tab in [dc.MD_VIEW_TAB, dc.BD_PIPELINE_TAB, dc.DASHBOARD_TAB, dc.GCC_WATCH_TAB,
                dc.EVIDENCE_TAB, dc.SS5_RANKED_TAB, dc.AI_SUMMARY_TAB]:
        print(f"\n===== {tab} =====")
        try:
            vals = ss.worksheet(tab).get_all_values()
            print(f"({len(vals)} rows)")
            for i, row in enumerate(vals[:72]):
                line = " | ".join(c[:26] for c in row)
                print(f"{i + 1:3}| {line[:230]}")
        except Exception as e:
            print("ERR", type(e).__name__, e)


if __name__ == "__main__":
    main()
