"""
dc_score.py  —  SS5 ranking. Scores watched operators over SS1–SS4 evidence.

Composite 0–100 in the spirit of BD Prospect Framework v3 (PRD §5 weights):
  Momentum 35% · Policy tailwind 20% · India/GCC relevance 25% · Partnership 20%.
Evidence-backed: every row carries top_evidence_ids back to the rows that scored it.
No NER yet (company spine pending) -> match the curated operator watchlist by name.
"""
import re
from datetime import datetime, timezone

import dc_config as dc
import dc_evidence

OPERATORS = dc.WATCH_OPERATORS_INDIA + dc.WATCH_OPERATORS_GCC + dc.WATCH_OPERATORS_FOREIGN
_FOREIGN = {o.lower() for o in dc.WATCH_OPERATORS_FOREIGN}
WEIGHTS = {"momentum": 0.35, "policy": 0.20, "geo": 0.25, "partner": 0.20}

# Deal-size capture for big-ticket foreign investment (deterministic, headline-led).
_MONEY = re.compile(
    r'(?:US\$|\$|₹|Rs\.?|INR|USD)\s?\d[\d,.]*\s?(?:billion|bn|trillion|tn|crore|cr|million|mn|lakh)'
    r'|\d[\d,.]*\s?(?:billion|bn|crore|cr|trillion|tn|million|mn|lakh)',
    re.I)


def _deal_value(snippets):
    """A money figure REQUIRING a unit (drops '$13'/'rs,'). Scans per snippet and prefers one
    that also mentions India (drops global/aspirational figures). Accepts a str or list."""
    if isinstance(snippets, str):
        snippets = [snippets]
    fallback = ""
    for s in snippets:
        m = _MONEY.search(s or "")
        if not m:
            continue
        val = m.group(0).strip()
        if "india" in (s or "").lower():
            return val
        fallback = fallback or val
    return fallback


def _parse(d):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(d[:16] if len(d) >= 16 else d, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _recency(d, half_days=90):
    dt = _parse(d or "")
    if not dt:
        return 0.5
    age = (datetime.now(timezone.utc) - dt).days
    return 0.5 ** (max(age, 0) / half_days)  # 1.0 today -> 0.5 at 90d


def _policy_genuine(r):
    """R5 gate: only genuine policy classes feed policy_tailwind. Legacy rows
    (no policy_class column) are classified on the fly."""
    cls = (r.get("policy_class") or "").strip()
    if not cls:
        import dc_ingest
        cls = dc_ingest.classify_policy(r.get("title"), r.get("summary"))
    return cls in dc.POLICY_GENUINE_CLASSES


def _mentions(op, *texts):
    pat = r"\b" + re.escape(op.lower()) + r"\b"
    return any(re.search(pat, (t or "").lower()) for t in texts)


def rank(ss1, ss2, ss3, ss4):
    """ss1/ss2/ss3/ss4: lists of header-keyed row dicts. Returns SS5 rows, ranked."""
    out = []
    for op in OPERATORS:
        ev, momentum, policy, partner = [], 0.0, 0, 0
        tiers = {}
        geos, layers, last = set(), set(), ""
        hits = []                                     # matched text for deal-size capture
        seen_ev = set()                               # dedup momentum by event (not dup articles)

        for r in ss1 + ss2:  # article schema
            if _mentions(op, r.get("title"), r.get("summary")):
                ev.append(r.get("id", ""))
                hits.append(f"{r.get('title', '')} {r.get('summary', '')}")
                tier = dc_evidence.source_tier(r.get("source"), r.get("url", ""))
                tiers[tier] = tiers.get(tier, 0) + 1
                w = _recency(r.get("date", "")) * dc.SOURCE_TIER_MOMENTUM_WEIGHTS.get(tier, 0.3)
                if r in ss2:
                    if _policy_genuine(r):     # R5: commentary never feeds the tailwind
                        policy += 1
                else:
                    key = r.get("event_id") or r.get("id") or ""
                    if key and key in seen_ev:
                        pass          # duplicate coverage of the same event -> no inflation
                    else:
                        momentum += w
                        seen_ev.add(key)
                if r.get("geo"):
                    geos.update(g.strip() for g in r["geo"].split(";"))
                if r.get("layer"):
                    layers.update(l.strip() for l in r["layer"].split(";"))
                last = max(last, r.get("date", "")[:10])
        for r in ss3:  # filings
            if _mentions(op, r.get("filer"), r.get("counterparty")):
                ev.append(r.get("accession", ""))
                hits.append(r.get("evidence", "") or "")
                momentum += _recency(r.get("filed_date", ""))
                tiers["T1"] = tiers.get("T1", 0) + 1     # SEC filing = primary source
                partner += 1
                last = max(last, r.get("filed_date", "")[:10])
        for r in ss4:  # OSINT
            if _mentions(op, r.get("actor"), r.get("excerpt")):
                ev.append(r.get("id", ""))
                hits.append(r.get("excerpt", "") or "")
                momentum += _recency(r.get("observed_date", ""))
                if r.get("geo"):
                    geos.update(g.strip() for g in r["geo"].split(";"))
                last = max(last, r.get("observed_date", "")[:10])

        if not ev:
            continue

        in_geo = 1.0 if "India" in geos else (0.5 if geos else 0.0)  # India full, GCC-only partial
        s = 100 * (
            WEIGHTS["momentum"] * min(momentum, 10) / 10
            + WEIGHTS["policy"] * min(policy, 5) / 5
            + WEIGHTS["geo"] * in_geo
            + WEIGHTS["partner"] * min(partner, 5) / 5
        )
        out.append({
            "company": op,
            "partner": "",
            "development_type": "partnership/JV" if partner else "activity",
            "layer": "; ".join(sorted(layers)) or "General",
            "geo": "; ".join(sorted(geos)),
            "score": round(s, 1),
            "momentum": round(momentum, 2),
            "policy_tailwind": policy,
            "india_gcc_relevance": "; ".join(sorted(geos)),
            "partnership_strength": partner,
            "last_signal": last,
            "top_evidence_ids": ", ".join(e for e in ev[:8] if e),
            "is_foreign": op.lower() in _FOREIGN,       # non-Indian hyperscaler/investor
            "deal_value": _deal_value(hits),            # big-ticket size (unit-required, India-scoped)
            # Phase 4b (R2): evidence source-tier mix; all-T3 caps BD priority at P3
            "source_tier_mix": " ".join(f"{k}:{tiers[k]}" for k in ("T1", "T2", "T3") if tiers.get(k)),
            "all_t3": bool(tiers) and set(tiers) == {"T3"},
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out


def _selfcheck():
    # R2: identical stories from a T1 wire vs a T3 aggregator produce different momentum.
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    story = {"title": "AirTrunk to invest in Mumbai data centre campus", "summary": "",
             "date": today, "geo": "India", "layer": "Build"}
    t1 = [dict(story, id="a", source="Reuters", url="https://reuters.com/x", event_id="e1")]
    t3 = [dict(story, id="b", source="Whalesbook", url="https://whalesbook.com/x", event_id="e2")]
    r1 = next(r for r in rank(t1, [], [], []) if r["company"] == "AirTrunk")
    r3 = next(r for r in rank(t3, [], [], []) if r["company"] == "AirTrunk")
    assert r1["momentum"] > r3["momentum"] * 2, (r1["momentum"], r3["momentum"])
    assert r3["all_t3"] and not r1["all_t3"]
    assert r1["source_tier_mix"].startswith("T1:") and r3["source_tier_mix"].startswith("T3:")
    # R5: commentary never feeds policy_tailwind; genuine class does.
    comm = [{"id": "p1", "title": "India data centre market to reach $12 billion by 2030",
             "summary": "forecast", "date": today, "geo": "India", "source": "Trade Brains",
             "url": "https://tradebrains.in/x", "policy_class": "market-commentary"}]
    gen = [{"id": "p2", "title": "Maharashtra notifies data centre policy incentive",
            "summary": "stamp duty exemption", "date": today, "geo": "India", "source": "PIB India",
            "url": "https://pib.gov.in/x", "policy_class": "state-DC-policy"}]
    story_ms = {"title": "Microsoft India data centre", "summary": "", "date": today,
                "geo": "India", "layer": "Colo", "source": "Reuters", "url": "https://reuters.com/y",
                "id": "c", "event_id": "e3"}
    rc = next(r for r in rank([story_ms], [dict(c, title=c["title"] + " Microsoft") for c in comm], [], []) if r["company"] == "Microsoft")
    rg = next(r for r in rank([story_ms], [dict(g, title=g["title"] + " Microsoft") for g in gen], [], []) if r["company"] == "Microsoft")
    assert rc["policy_tailwind"] == 0 and rg["policy_tailwind"] == 1, (rc["policy_tailwind"], rg["policy_tailwind"])
    print("dc_score self-check: OK")


if __name__ == "__main__":
    _selfcheck()
