"""
dc_engine.py  —  pure clustering logic (numpy only, no ML deps).

Greedy cosine grouping with running-mean centroids. Embeddings are assumed
L2-normalised, so cosine == dot product. Kept ML-free so it's trivially testable
with fake vectors (see demo() at the bottom).
"""
import numpy as np


def cosine(a, b):
    return float(np.dot(a, b))


def update_centroid(centroid, count, vec):
    """Running-mean update, then re-normalise. centroid=None starts a new cluster."""
    v = np.asarray(vec, dtype=np.float64)
    if centroid is None or count == 0:
        mean = v
    else:
        mean = (np.asarray(centroid, dtype=np.float64) * count + v) / (count + 1)
    norm = np.linalg.norm(mean)
    return mean / norm if norm else mean


def best_match(vec, centroids):
    """(index, score) of the most-similar centroid, or (-1, -1.0) if none."""
    if not centroids:
        return -1, -1.0
    sims = [cosine(vec, c) for c in centroids]
    i = int(np.argmax(sims))
    return i, sims[i]


def cluster_batch(embs, threshold):
    """Greedily group brand-new embeddings among themselves. Returns a list of
    clusters, each a list of indices into `embs`. A lone item = single-item cluster."""
    clusters = []  # {"c": centroid, "m": [idx, ...]}
    for i, e in enumerate(embs):
        placed = False
        for cl in clusters:
            if cosine(e, cl["c"]) >= threshold:
                cl["c"] = update_centroid(cl["c"], len(cl["m"]), e)
                cl["m"].append(i)
                placed = True
                break
        if not placed:
            clusters.append({"c": np.asarray(e, dtype=np.float64), "m": [i]})
    return [cl["m"] for cl in clusters]


def demo():
    """Self-check: two near-identical vectors cluster; an orthogonal one splits."""
    a = np.array([1.0, 0.0]); b = np.array([0.96, 0.28]); c = np.array([0.0, 1.0])
    groups = cluster_batch([a, b, c], threshold=0.6)
    assert len(groups) == 2, groups
    assert {0, 1} in [set(g) for g in groups], groups
    i, s = best_match(a, [c, b])
    assert i == 1 and s > 0.9, (i, s)
    print("dc_engine.demo OK")


if __name__ == "__main__":
    demo()
