"""
dc_state.py  —  persistence across runs (CI runners are wiped each run).

Holds seen article IDs (dedup memory) + live cluster centroids (cross-run event
linking). Committed back to the repo by the workflow. No secrets ever live here.
"""
import os
import json
from datetime import datetime, timezone, timedelta

import dc_config as dc

PATH = os.path.join(os.path.dirname(__file__), "dc_news_state.json")


def load():
    if os.path.exists(PATH):
        try:
            with open(PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"seen_ids": {}, "clusters": [], "counter": 0}


def save(state):
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, separators=(",", ":"))


def _parse(ts):
    try:
        d = datetime.fromisoformat(ts)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)  # coerce naive -> aware
    except Exception:
        return datetime.now(timezone.utc)


def prune(state, now=None):
    """Forget old article IDs and stale clusters."""
    now = now or datetime.now(timezone.utc)
    id_cut = now - timedelta(days=dc.SEEN_ARTICLE_TTL_DAYS)
    state["seen_ids"] = {a: t for a, t in state["seen_ids"].items()
                         if _parse(t) >= id_cut}
    cl_cut = now - timedelta(days=dc.EVENT_DORMANT_DAYS)
    state["clusters"] = [c for c in state["clusters"]
                         if _parse(c.get("last", "")) >= cl_cut]
