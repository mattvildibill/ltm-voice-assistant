from datetime import datetime, timedelta

import pytest

from app.models.entry import Entry, MemoryType
from app.services.retrieval_scoring import (
    compute_score,
    recency_boost,
    rerank_entries,
    classify_query_domain,
)


def make_entry(
    id: str,
    memory_type: MemoryType,
    created_at: datetime,
    confidence: float = 0.8,
    tags=None,
    embedding=None,
):
    e = Entry(
        id=id,
        user_id="u",
        memory_type=memory_type,
        source_type="text",
        original_text="t",
        content="t",
        created_at=created_at,
        updated_at=created_at,
        confidence_score=confidence,
        tags=tags or [],
    )
    if embedding is not None:
        e.embedding = embedding
    return e


def test_recency_decay_prefers_recent():
    now = datetime.utcnow()
    recent = make_entry("r", MemoryType.EVENT, now - timedelta(days=2))
    old = make_entry("o", MemoryType.EVENT, now - timedelta(days=60))
    assert recency_boost(recent, now) > recency_boost(old, now)


def test_rerank_uses_recency_and_confidence(monkeypatch):
    # Force deterministic embedding similarity: entry1 sim 0.5, entry2 sim 0.5
    monkeypatch.setattr("app.services.retrieval_scoring.embed_text", lambda q: [1, 0])
    monkeypatch.setattr(
        "app.services.retrieval_scoring.deserialize_embedding",
        lambda raw: raw,
    )
    monkeypatch.setattr(
        "app.services.retrieval_scoring.cosine_similarity",
        lambda a, b: 0.5,
    )

    now = datetime.utcnow()
    recent_high_conf = make_entry(
        "a", MemoryType.REFLECTION, now - timedelta(days=1), confidence=0.9, embedding=[1, 0]
    )
    older_low_conf = make_entry(
        "b", MemoryType.REFLECTION, now - timedelta(days=50), confidence=0.3, embedding=[1, 0]
    )

    result = rerank_entries(
        "How have I felt?", [recent_high_conf, older_low_conf], top_n=2, candidate_k=10, debug=True, now=now
    )
    assert result.entries[0].id == "a"
    assert result.debug and result.debug[0]["entry_id"] == "a"


def test_domain_filter_boosts_family():
    now = datetime.utcnow()
    family_entry = make_entry(
        "fam",
        MemoryType.IDENTITY,
        now - timedelta(days=10),
        embedding=[1, 0],
        tags=["family"],
    )
    project_entry = make_entry(
        "proj",
        MemoryType.PROJECT,
        now - timedelta(days=10),
        embedding=[1, 0],
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.services.retrieval_scoring.embed_text", lambda q: [1, 0])
    monkeypatch.setattr(
        "app.services.retrieval_scoring.deserialize_embedding",
        lambda raw: raw,
    )
    monkeypatch.setattr(
        "app.services.retrieval_scoring.cosine_similarity",
        lambda a, b: 0.5,
    )

    result = rerank_entries(
        "How is my family doing?", [family_entry, project_entry], top_n=2, candidate_k=10, debug=False, now=now
    )
    assert result.entries[0].id == "fam"


def test_classify_query_domain_simple():
    assert classify_query_domain("career goals") == "jobs"
    assert classify_query_domain("family dinner") == "family"
