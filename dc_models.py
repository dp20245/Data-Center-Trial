"""
dc_models.py  —  ML layer (heavy imports deferred to first use).

MiniLM sentence embeddings (for clustering) + FinBERT sentiment. Loaded once,
lazily, so `import dc_models` stays cheap and `--no-ml` runs never touch torch.
"""
import numpy as np

_emb = _tok = _fin = _torch = None


def _load():
    global _emb, _tok, _fin, _torch
    if _emb is not None:
        return
    import torch
    from sentence_transformers import SentenceTransformer
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    _torch = torch
    print("  loading MiniLM + FinBERT ...")
    _emb = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    _tok = AutoTokenizer.from_pretrained("ProsusAI/finbert")
    _fin = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
    _fin.eval()
    print("  models ready.")


def embed(texts):
    if not texts:
        return []
    _load()
    vecs = _emb.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [np.asarray(v, dtype=np.float64) for v in vecs]


def sentiment(texts):
    """FinBERT score in [-1, 1] = P(positive) - P(negative). Label order: 0=pos,1=neg,2=neu."""
    if not texts:
        return []
    _load()
    out = []
    for i in range(0, len(texts), 16):
        chunk = texts[i:i + 16]
        inp = _tok(chunk, return_tensors="pt", padding=True,
                   truncation=True, max_length=256)
        with _torch.no_grad():
            logits = _fin(**inp).logits
        probs = _torch.nn.functional.softmax(logits, dim=-1)
        for pos, neg in zip(probs[:, 0].tolist(), probs[:, 1].tolist()):
            out.append(round(pos - neg, 3))
    return out
