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

OPERATORS = dc.WATCH_OPERATORS_INDIA + dc.WATCH_OPERATORS_GCC
WEIGHTS = {"momentum": 0.35, "policy": 0.20, "geo": 0.25, "partner": 0.20}


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


def _mentions(op, *texts):
    pat = r"\b" + re.escape(op.lower()) + r"\b"
    return any(re.search(pat, (t or "").lower()) for t in texts)


def rank(ss1, ss2, ss3, ss4):
    """ss1/ss2/ss3/ss4: lists of header-keyed row dicts. Returns SS5 rows, ranked."""
    out = []
    for op in OPERATORS:
        ev, momentum, policy, partner = [], 0.0, 0, 0
        geos, layers, last = set(), set(), ""

        for r in ss1 + ss2:  # article schema
            if _mentions(op, r.get("title"), r.get("summary")):
                ev.append(r.get("id", ""))
                w = _recency(r.get("date", ""))
                if r in ss2:
                    policy += 1
                else:
                    momentum += w
                if r.get("geo"):
                    geos.update(g.strip() for g in r["geo"].split(";"))
                if r.get("layer"):
                    layers.update(l.strip() for l in r["layer"].split(";"))
                last = max(last, r.get("date", "")[:10])
        for r in ss3:  # filings
            if _mentions(op, r.get("filer"), r.get("counterparty")):
                ev.append(r.get("accession", ""))
                momentum += _recency(r.get("filed_date", ""))
                partner += 1
                last = max(last, r.get("filed_date", "")[:10])
        for r in ss4:  # OSINT
            if _mentions(op, r.get("actor"), r.get("excerpt")):
                ev.append(r.get("id", ""))
                momentum += _recency(r.get("observed_date", ""))
                if r.get("geo"):
                    geos.update(g.strip() for g in r["geo"].split(";"))
                last = max(last, r.get("observed_date", "")[:10])

        if not ev:
            continue

        in_geo = 1.0 if geos else 0.0
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
        })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out
