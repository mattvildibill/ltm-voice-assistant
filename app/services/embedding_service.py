import json
from typing import List, Optional

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
