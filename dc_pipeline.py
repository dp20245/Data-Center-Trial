"""
dc_pipeline.py  —  daily entry point: SS2 Policy, SS3 Disclosure, SS4 OSINT, SS5 ranking.

Append-only tabs (SS2/SS3/SS4) dedup against what's already in the sheet, so a
re-run never duplicates rows — no extra state file needed. SS5 is rebuilt each run
by scoring the full SS1–SS4 evidence.

Flags:
  --no-ml      skip SS2 sentiment (torch-free)
  --no-sheets  fetch + score in memory, print a summary, write nothing
"""
import sys

import dc_config as dc
import dc_ingest
import dc_edgar
import dc_osint
import dc_score

NO_ML = "--no-ml" in sys.argv
NO_SHEETS = "--no-sheets" in sys.argv


def _reddit_to_osint(rows):
    return [{"id": r["id"], "observed_date": r["date"][:10], "signal_type": "reddit",
             "actor": r["source"], "geo": r["geo"], "layer": r["layer"],
             "magnitude": "", "confidence": "low", "url": r["url"],
             "excerpt": r["summary"][:300]} for r in rows]


def main():
    print("[dc_pipeline] start")

    ss2, h2 = dc_ingest.fetch_policy()
    ss2 = dc_ingest.dedup(ss2, set())
    print(f"  SS2 policy: {sum(1 for v in h2.values() if v>0)}/{len(h2)} feeds live, {len(ss2)} items")

    ss3, h3 = dc_edgar.fetch_filings()
    print(f"  SS3 EDGAR: {len(ss3)} filings")

    reddit, hr = dc_ingest.fetch_reddit()
    reddit = dc_ingest.dedup(reddit, set())
    jobs, hj = dc_osint.fetch_all()
    ss4 = _reddit_to_osint(reddit) + jobs
    print(f"  SS4 OSINT: {len(reddit)} reddit + {len(jobs)} jobs = {len(ss4)}")

    if ss2 and not NO_ML:
        import dc_models
        for r, s in zip(ss2, dc_models.sentiment([r["text"] for r in ss2])):
            r["sentiment"] = s

    if NO_SHEETS:
        ranked = dc_score.rank([], ss2, ss3, ss4)
        print(f"  SS5 (dry, no SS1): {len(ranked)} ranked operators")
        for r in ranked[:10]:
            print(f"    {r['score']:5.1f}  {r['company']:16} {r['geo'][:30]:30} ev={r['top_evidence_ids'][:30]}")
        return

    import dc_sheets
    sheet = dc_sheets.connect()

    seen2 = dc_sheets.dedup_existing(sheet, dc.SS2_POLICY_TAB, [r["id"] for r in ss2])
    new2 = [r for r in ss2 if r["id"] not in seen2]
    print(f"  SS2 -> {dc_sheets.append_articles(sheet, dc.SS2_POLICY_TAB, new2)} new")

    seen3 = dc_sheets.dedup_existing(sheet, dc.SS3_DISCLOSE_TAB, [r["accession"] for r in ss3], id_col="accession")
    new3 = [r for r in ss3 if r["accession"] not in seen3]
    print(f"  SS3 -> {dc_sheets.append_ss3(sheet, new3)} new")

    seen4 = dc_sheets.dedup_existing(sheet, dc.SS4_OSINT_TAB, [r["id"] for r in ss4])
    new4 = [r for r in ss4 if r["id"] not in seen4]
    print(f"  SS4 -> {dc_sheets.append_ss4(sheet, new4)} new")

    # SS5: score the full evidence base (read every tab back).
    a1 = dc_sheets.read_tab(sheet, dc.SS1_NEWS_TAB)
    a2 = dc_sheets.read_tab(sheet, dc.SS2_POLICY_TAB)
    a3 = dc_sheets.read_tab(sheet, dc.SS3_DISCLOSE_TAB)
    a4 = dc_sheets.read_tab(sheet, dc.SS4_OSINT_TAB)
    ranked = dc_score.rank(a1, a2, a3, a4)

    # India entity spine: resolve SS5 operators against MCA (link SS5 by CIN) +
    # a dictionary-NER pass over SS1/SS2/SS4 text to grow the spine. Enrichment,
    # not a trigger (Sheet 7 rule): signals stay the driver via top_evidence_ids.
    import dc_mca
    cache = dc_mca.load_cache()
    entities = {}

    def _add(rec, src):
        cur = entities.setdefault(rec["cin"], {**rec, "sources": ""})
        srcs = set(filter(None, cur["sources"].split("; ")))
        srcs.add(src)
        cur["sources"] = "; ".join(sorted(srcs))

    for r in ranked:                       # SS5 operators (primary)
        rec = dc_mca.resolve(r["company"], cache)
        r["cin"] = rec["cin"] if rec else ""
        r["india_status"] = rec["status"] if rec else "unresolved"
        if rec:
            _add(rec, f"SS5:{r['company']}")

    seen = {r["company"] for r in ranked}
    for row in a1 + a2 + a4:               # NER-lite over signal text
        text = f"{row.get('title', '')} {row.get('summary', '')} {row.get('actor', '')} {row.get('excerpt', '')}"
        for org in dc_mca.extract_orgs(text):
            if org in seen:
                continue
            seen.add(org)
            rec = dc_mca.resolve(org, cache)
            if rec:
                _add(rec, f"NER:{org}")

    dc_mca.save_cache(cache)
    print(f"  SS5 -> {dc_sheets.write_ss5(sheet, ranked)} ranked operators")
    print(f"  Entities spine -> {dc_sheets.write_entities(sheet, list(entities.values()))} resolved")


if __name__ == "__main__":
    main()
