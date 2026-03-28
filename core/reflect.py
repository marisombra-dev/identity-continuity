"""
reflect.py
Semantic memory search for mid-conversation retrieval.

Uses sentence-transformers to find memory entries semantically similar
to a query. Complements tag-graph traversal (which is associative/
exploratory) with targeted lookup (which is precise/retrieval-based).

Usage:
    from reflect import reflect
    result = reflect("what did I think about consciousness last week?", top_n=5)
    if result["found"]:
        for r in result["results"]:
            print(r["date"], r["snippet"])
"""

from pathlib import Path
from typing import Optional
import json
import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
LUX_DIR      = Path("./data")
TAGGED_FILE  = LUX_DIR / "memory_tagged.json"
MODEL_NAME   = "all-MiniLM-L6-v2"   # fast, good quality, runs locally
INDEX_FILE   = LUX_DIR / "semantic_index.pkl"

_model  = None
_index  = None
_corpus = None


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _load_corpus():
    """Load tagged memory entries as searchable corpus."""
    global _corpus
    if _corpus is not None:
        return _corpus
    try:
        entries = json.loads(TAGGED_FILE.read_text(encoding="utf-8"))
        _corpus = [
            {
                "id":      e.get("id", ""),
                "content": e.get("content", ""),
                "tags":    e.get("tags", []),
                "date":    e.get("date", ""),
                "source":  e.get("source", ""),
            }
            for e in entries
            if e.get("content", "").strip()
        ]
        return _corpus
    except Exception:
        return []


def _build_embeddings(corpus: list):
    """Build or load cached embeddings."""
    import pickle
    import numpy as np

    if INDEX_FILE.exists():
        try:
            with open(INDEX_FILE, "rb") as f:
                cached = pickle.load(f)
            if cached.get("count") == len(corpus):
                return cached["embeddings"]
        except Exception:
            pass

    model = _load_model()
    texts = [e["content"][:512] for e in corpus]
    embeddings = model.encode(texts, show_progress_bar=False,
                               convert_to_numpy=True)
    try:
        with open(INDEX_FILE, "wb") as f:
            pickle.dump({"count": len(corpus), "embeddings": embeddings}, f)
    except Exception:
        pass
    return embeddings


def reflect(query: str, top_n: int = 5,
            min_score: float = 0.35,
            date_filter: Optional[str] = None) -> dict:
    """
    Search memory semantically.

    Args:
        query:       Natural language query
        top_n:       Maximum results to return
        min_score:   Minimum cosine similarity (0-1). 0.35 is a good default.
        date_filter: Optional ISO date string — only return entries after this date

    Returns:
        {
          "found": bool,
          "query": str,
          "results": [{"content", "tags", "date", "source", "score", "snippet"}]
        }
    """
    import numpy as np

    corpus = _load_corpus()
    if not corpus:
        return {"found": False, "query": query, "results": []}

    embeddings = _build_embeddings(corpus)
    model      = _load_model()

    query_vec = model.encode([query], convert_to_numpy=True)[0]

    # Cosine similarity
    norms  = np.linalg.norm(embeddings, axis=1, keepdims=True)
    normed = embeddings / np.maximum(norms, 1e-10)
    q_norm = query_vec / max(np.linalg.norm(query_vec), 1e-10)
    scores = normed @ q_norm

    # Filter and sort
    results = []
    for i, score in enumerate(scores):
        if score < min_score:
            continue
        entry = corpus[i]
        if date_filter:
            try:
                if entry["date"] < date_filter:
                    continue
            except Exception:
                pass
        results.append({**entry, "score": float(score)})

    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:top_n]

    for r in results:
        r["snippet"] = r["content"][:200].replace("\n", " ").strip()

    return {
        "found":   len(results) > 0,
        "query":   query,
        "results": results,
    }


def format_for_prompt(result: dict, max_entries: int = 4) -> str:
    """Format reflect() results for injection into loop system prompt."""
    if not result["found"]:
        return f"(no memories found for: {result['query']})"
    lines = [f"Memory search: '{result['query']}'"]
    for r in result["results"][:max_entries]:
        lines.append(f"  [{r['date']}] (score {r['score']:.2f}) {r['snippet']}")
    return "\n".join(lines)
