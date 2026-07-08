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

    # Presence/stage: separate legal-entity match from India presence + expansion stage so
    # established players (AWS/Google/AirTrunk) are never mislabeled "market-entry". The
    # manual Entity Overrides tab wins. Attaches fields in-memory to each ranked row.
    import dc_presence
    ov_header = ["company", "entity_match", "india_presence", "expansion_stage",
                 "presence_evidence_url", "verified_date", "notes"]
    try:
        dc_sheets.get_tab(sheet, dc.ENTITY_OVERRIDES_TAB, ov_header)   # create if missing
        ov_rows = dc_sheets.read_tab(sheet, dc.ENTITY_OVERRIDES_TAB)
    except Exception as e:
        print(f"  [overrides] {e}")
        ov_rows = []
    # R7: seed Entity Overrides with curated known-good rows (once; humans own the tab).
    try:
        have = {(r.get("company") or "").lower() for r in ov_rows}
        seeds = []
        from datetime import date as _date
        for co, (match, pres, stage, note) in dc.PRESET_OVERRIDES.items():
            if co.lower() not in have:
                seeds.append([co, match, pres, stage, "", str(_date.today()), f"seeded: {note}"])
        if seeds:
            ws_ov = dc_sheets.get_tab(sheet, dc.ENTITY_OVERRIDES_TAB, ov_header)
            dc_sheets._retry(ws_ov.append_rows, seeds, value_input_option="RAW")
            ov_rows += [dict(zip(ov_header, s)) for s in seeds]
            print(f"  Entity Overrides seeded -> {[s[0] for s in seeds]}")
    except Exception as e:
        print(f"  [overrides-seed] non-fatal error: {e}")

    overrides = dc_presence.load_overrides(ov_rows)
    for r in ranked:
        r.update(dc_presence.classify(r, a4, overrides))

    # AI adjudicates ONLY the ambiguous residual (deterministic proven cases untouched):
    # grounded on each company's evidence, one cached call, non-fatal.
    amb = [r for r in ranked if r.get("india_presence") in ("unknown", "no_known_presence")
           and r.get("company", "").lower() not in overrides]
    if amb:
        import dc_ai
        evidx = dc_ai._ev_index({"ss1": a1, "ss2": a2, "ss3": a3, "ss4": a4})
        ev_by = {}
        for r in amb:
            ids = [i.strip() for i in (r.get("top_evidence_ids") or "").split(",") if i.strip()]
            ev_by[r["company"]] = [evidx[i] for i in ids if i in evidx][:6]
        try:
            verdicts = dc_presence.ai_adjudicate(amb, ev_by)
        except Exception as e:
            print(f"  [presence-ai] {e}")
            verdicts = {}
        applied = 0
        for r in amb:
            v = verdicts.get(r["company"]) or {}
            if v.get("confidence") in ("high", "med") and v.get("india_presence"):
                r["india_presence"] = v["india_presence"]
                if v.get("expansion_stage"):
                    r["expansion_stage"] = v["expansion_stage"]
                r["presence_source"] = "ai"
                applied += 1
        print(f"  Presence AI adjudicated -> {applied}/{len(amb)} ambiguous")

    # Phase 4a (R1+R4): deterministic role/type + whitespace label per company; AI may
    # only downgrade weak-reason Prospect/Partner rows (locked boundary, dc_classify).
    import dc_classify
    import dc_evidence as _ev
    _reg_for_cls = _ev.build_register(
        {"ss1": a1, "ss2": a2, "ss3": a3, "ss4": a4}, ranked)
    for r in ranked:
        r.update(dc_classify.classify_role(r, _reg_for_cls))
    try:
        import dc_ai as _ai
        _evidx = _ai._ev_index({"ss1": a1, "ss2": a2, "ss3": a3, "ss4": a4})
        _ev_by = {r["company"]: [_evidx[i] for i in
                                 [x.strip() for x in (r.get("top_evidence_ids") or "").split(",") if x.strip()]
                                 if i in _evidx][:6] for r in ranked}
        down = dc_classify.ai_downgrade(ranked, _ev_by)
        if down:
            print(f"  Classify AI downgraded -> {down}")
    except Exception as e:
        print(f"  [classify-ai] non-fatal error: {e}")
    roles = {}
    for r in ranked:
        roles[r["role"]] = roles.get(r["role"], 0) + 1
    print(f"  Roles: {roles}")

    print(f"  SS5 -> {dc_sheets.write_ss5(sheet, ranked)} ranked operators")
    print(f"  Entities spine -> {dc_sheets.write_entities(sheet, list(entities.values()))} resolved")

    # Dashboard + AI Summary + Evidence Register + BD Pipeline. All non-fatal: a failure
    # here never breaks the SS1-SS5 pipeline.
    import dc_dashboard
    import dc_ai
    import dc_evidence
    import dc_bd
    tabs = {"ss1": a1, "ss2": a2, "ss3": a3, "ss4": a4,
            "ss5": ranked, "entities": list(entities.values())}

    # Evidence Register (hash -> readable, clickable record) — feeds descriptive links everywhere.
    register = dc_evidence.build_register(tabs, ranked)
    try:
        print(f"  Evidence Register -> {dc_evidence.write_register(sheet, register)} rows")
    except Exception as e:
        print(f"  [evidence] non-fatal error: {e}")

    # BD Pipeline (P1/P2/P3) + GCC Watch. Soft columns AI-drafted (grounded, marked, non-fatal).
    pipe, gcc, md_rows = [], [], []
    try:
        evidx = dc_ai._ev_index(tabs)
        ev_by = {r["company"]: [evidx[i] for i in
                                [x.strip() for x in (r.get("top_evidence_ids") or "").split(",") if x.strip()]
                                if i in evidx][:5] for r in ranked}
        pipe, gcc = dc_bd.build(ranked, register)
        dc_bd.ai_draft(pipe, ev_by)
        n_bd, n_gcc = dc_bd.write(sheet, pipe, gcc)
        print(f"  BD Pipeline -> {n_bd} opportunities · GCC Watch -> {n_gcc}")
        # MD View — curated P1/P2 top-slice for leadership.
        import dc_md
        from datetime import datetime, timezone
        link_by = {r["company"]: next((i.strip() for i in (r.get("top_evidence_ids") or "").split(",")
                                       if i.strip()), "") for r in ranked}
        stats = (f"MD VIEW — India DC opportunities · {len(register)} evidence sources · "
                 f"{n_bd} pipeline entries · updated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
        md_rows = dc_md.build(pipe, link_by, register)
        print(f"  MD View -> {dc_md.write(sheet, md_rows, stats)} rows")
    except Exception as e:
        print(f"  [bd] non-fatal error: {e}")

    computed, ai_text = {}, None
    try:
        computed = dc_dashboard.compute(tabs)
        print(f"  Dashboard -> {dc_dashboard.write(sheet, computed, register)} rows")
        ai_text = dc_ai.summarize(sheet, tabs, computed, register)
    except Exception as e:
        print(f"  [dashboard/ai] non-fatal error: {e}")

    # Dashboard data feed (dashboard/data.json -> Vercel). Non-fatal; validate()
    # blocks a bad export so the previous data.json survives.
    try:
        import dc_export
        health = {**h2, **h3, **hr, **hj}
        data = dc_export.build(tabs, computed or {"movers": ranked}, register,
                               pipe=pipe, gcc=gcc, md_rows=md_rows,
                               ai_summary=ai_text, health=health)
        dc_export.write(data)
    except Exception as e:
        print(f"  [export] non-fatal error: {e}")


if __name__ == "__main__":
    main()
