import json
from typing import Iterable, List, Optional, Tuple

from app.services.openai_service import client


def embed_text(text: str) -> Optional[List[float]]:
    """
    Create an embedding for the given text using OpenAI's embedding model.
    Returns a list of floats or None on failure.
    """
    if not text or not text.strip():
        return None

    try:
        resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )
    except Exception:
        return None

    if not resp.data:
        return None

    return resp.data[0].embedding


def serialize_embedding(vec: Optional[List[float]]) -> Optional[str]:
    if not vec:
        return None
    try:
        return json.dumps(vec)
    except Exception:
        return None


def deserialize_embedding(raw: Optional[str]) -> Optional[List[float]]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [float(x) for x in data]
    except Exception:
        return None
    return None


def cosine_similarity(a: List[float], b: List[float]) -> Optional[float]:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return None
    import math

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return None
    return dot / (norm_a * norm_b)


def find_similar_entries(
    question: str,
    entries: Iterable,
    top_k: int = 5,
) -> List[Tuple[float, object]]:
    """
    Embed the question and score entries by cosine similarity.
    Returns a list of (score, entry) sorted desc.
    If embeddings are missing, returns empty list so callers can fall back.
    """
    query_vec = embed_text(question)
    if not query_vec:
        return []

    scored: List[Tuple[float, object]] = []
    for entry in entries:
        vec = deserialize_embedding(getattr(entry, "embedding", None))
        if not vec:
            continue
        sim = cosine_similarity(query_vec, vec)
        if sim is not None:
            scored.append((sim, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]
