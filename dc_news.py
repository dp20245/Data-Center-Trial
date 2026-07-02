"""
dc_news.py  —  SS1 pipeline entry point. Run by GitHub Actions (~every 3h).

  ingest DC news -> layer/geo tag -> dedup -> embed + sentiment -> cluster
  (cross-run event linking) -> write SS1 tab -> persist state.

Flags:
  --no-ml      skip embeddings/sentiment/clustering (fast, torch-free smoke test;
               sentiment + event_id are left blank)
  --no-sheets  run the full pipeline but skip all Google Sheets writes
"""
import sys
from datetime import datetime, timezone

import numpy as np

import dc_config as dc
import dc_ingest
import dc_engine
import dc_state

NO_ML = "--no-ml" in sys.argv
NO_SHEETS = "--no-sheets" in sys.argv


def _now():
    return datetime.now(timezone.utc).isoformat()


def _assign_events(new, state):
    """Match each new item to a live cluster of the same primary layer, else form
    new clusters. Fills r['event_id']. Mutates state['clusters'] in place."""
    clusters = state["clusters"]
    # hydrate centroids
    for c in clusters:
        c["_c"] = np.asarray(c["centroid"], dtype=np.float64)

    leftovers = []
    for r in new:
        peers = [c for c in clusters if c["layer"] == r["primary_layer"]]
        idx, sim = dc_engine.best_match(r["emb"], [c["_c"] for c in peers])
        if idx >= 0 and sim >= dc.CLUSTER_THRESHOLD:
            c = peers[idx]
            c["_c"] = dc_engine.update_centroid(c["_c"], c["n"], r["emb"])
            c["n"] += 1
            c["last"] = max(c.get("last", ""), r["date"])
            r["event_id"] = c["id"]
        else:
            leftovers.append(r)

    # cluster leftovers among themselves -> brand-new clusters
    groups = dc_engine.cluster_batch([r["emb"] for r in leftovers], dc.CLUSTER_THRESHOLD)
    for members in groups:
        items = [leftovers[i] for i in members]
        centroid = dc_engine.update_centroid(None, 0, items[0]["emb"])
        for it in items[1:]:
            centroid = dc_engine.update_centroid(centroid, 1, it["emb"])
        state["counter"] += 1
        eid = f"EVT-{state['counter']:04d}"
        for it in items:
            it["event_id"] = eid
        clusters.append({
            "id": eid, "layer": items[0]["primary_layer"],
            "centroid": [round(float(x), 6) for x in centroid],
            "n": len(items), "last": max(it["date"] for it in items),
        })

    # dehydrate
    for c in clusters:
        if "_c" in c:
            c["centroid"] = [round(float(x), 6) for x in c["_c"]]
            c.pop("_c", None)


def main():
    state = dc_state.load()
    print(f"[{_now()}] SS1 run start")

    rows, health = dc_ingest.fetch()
    live = sum(1 for v in health.values() if v > 0)
    print(f"  feeds: {live}/{len(health)} live, {len(rows)} in-scope items")
    for src, n in health.items():
        if n == 0:
            print(f"    [dead/empty] {src}")

    new = dc_ingest.dedup(rows, state["seen_ids"])
    print(f"  {len(new)} new after dedup")

    if new and not NO_ML:
        import dc_models
        texts = [r["text"] for r in new]
        embs = dc_models.embed(texts)
        scores = dc_models.sentiment(texts)
        for r, e, s in zip(new, embs, scores):
            r["emb"], r["sentiment"] = e, s
        _assign_events(new, state)

    if NO_SHEETS:
        print("  --no-sheets: skipping Sheets writes")
        for r in new[:8]:
            print(f"    [{r['geo']}|{r['layer']}] {r['title'][:80]}  ({r['source']})")
    elif new:
        import dc_sheets
        ss = dc_sheets.connect()
        seen = dc_sheets.dedup_existing(ss, dc.SS1_NEWS_TAB, [r["id"] for r in new])
        fresh = [r for r in new if r["id"] not in seen]   # idempotent: never re-append (SS2-SS4 already do this)
        wrote = dc_sheets.append_ss1(ss, fresh)
        print(f"  wrote {wrote} rows to '{dc.SS1_NEWS_TAB}'")

    ts = _now()
    for r in new:
        state["seen_ids"][r["id"]] = ts
    dc_state.prune(state)
    dc_state.save(state)
    print(f"  state: {len(state['seen_ids'])} ids, {len(state['clusters'])} clusters")


if __name__ == "__main__":
    main()
