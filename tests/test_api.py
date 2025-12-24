import importlib
import json
import os
from typing import List

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Use isolated SQLite DB per test
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    # Reload config + db modules to pick up new env
    import app.core.config as config_module
    import app.db.database as db_module
    importlib.reload(config_module)
    importlib.reload(db_module)

    # Build test engine and tables
    test_engine = create_engine(config_module.settings.database_url, echo=False)
    SQLModel.metadata.create_all(test_engine)

    # Dependency override for DB sessions
    def get_test_session():
        with Session(test_engine) as session:
            yield session

    import main
    importlib.reload(main)
    from main import app
    from app.routers import insights as insights_router
    from app.routers import conversation as conversation_router
    from app.db import database as db
    from app.services import entry_service

    app.dependency_overrides[insights_router.get_db_session] = get_test_session
    app.dependency_overrides[conversation_router.get_db_session] = get_test_session
    conversation_router.conversation_state["messages"] = []

    # Stub analysis + embeddings to avoid network
    def fake_analysis(text: str):
        return {
            "summary": "stub summary",
            "themes": ["reflection"],
            "topics": ["life"],
            "emotions": [{"name": "joy", "score": 0.9}],
            "people": ["Alex"],
            "places": ["Home"],
            "sentiment": {"label": "positive", "score": 0.9},
            "memory_chunks": ["chunk"],
        }

    monkeypatch.setattr(entry_service, "analyze_text", fake_analysis)
    monkeypatch.setattr(entry_service, "embed_text", lambda text: [0.1, 0.2, 0.3])
    monkeypatch.setattr(entry_service, "serialize_embedding", lambda vec: json.dumps(vec))
    def fake_find_similar_entries(question, entries, top_k=5):
        # return existing entries with a constant score for determinism
        return [(1.0, e) for e in list(entries)[:top_k]]

    from app.services import embedding_service
    # Patch retrieval scoring to avoid network
    import app.services.retrieval_scoring as retrieval_scoring

    class DummyRerankResult:
        def __init__(self, entries):
            self.entries = entries
            self.debug = None

    def fake_rerank(question, entries, top_n=10, candidate_k=50, debug=False, now=None):
        return DummyRerankResult(list(entries)[:top_n])

    monkeypatch.setattr(retrieval_scoring, "embed_text", lambda text: [0.1, 0.2, 0.3])
    monkeypatch.setattr(retrieval_scoring, "deserialize_embedding", lambda raw: [0.1, 0.2, 0.3])
    monkeypatch.setattr(retrieval_scoring, "cosine_similarity", lambda a, b: 0.5)
    monkeypatch.setattr(retrieval_scoring, "rerank_entries", fake_rerank)
    monkeypatch.setattr(insights_router, "rerank_entries", fake_rerank)
    monkeypatch.setattr(conversation_router, "rerank_entries", fake_rerank)

    class DummyChoice:
        def __init__(self, content: str):
            self.message = type("Msg", (), {"content": content})

    class DummyCompletions:
        def __init__(self, content: str):
            self.choices = [DummyChoice(content)]

    def fake_chat_create(**kwargs):
        return DummyCompletions("answer from memories")

    monkeypatch.setattr(insights_router.client.chat.completions, "create", fake_chat_create)
    monkeypatch.setattr(conversation_router.client.chat.completions, "create", fake_chat_create)

    # Ensure deserialize works with stored embeddings
    monkeypatch.setattr(
        embedding_service, "deserialize_embedding", lambda raw: [0.1, 0.2, 0.3]
    )

    # Recreate tables with overrides
    SQLModel.metadata.create_all(test_engine)

    return TestClient(app)


def test_entry_creation(client: TestClient):
    resp = client.post(
        "/entries",
        data={"text": "Today I reflected on life at home with Alex."},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "entry_id" in data
    assert isinstance(data["entry_id"], str)
    assert data["word_count"] > 0
    assert data["memory_type"] == "reflection"
    assert data["source"] == "typed"
    assert data["confidence_score"] == pytest.approx(0.95)
    assert data["last_confirmed_at"] is None
    assert data["updated_at"] is not None

    # Ensure the entry persisted with the expected memory_type
    entries = client.get("/insights/entries").json()
    assert entries, "No entries returned from insights"
    assert entries[0]["memory_type"] == "reflection"
    assert entries[0]["source"] == "typed"
    assert entries[0]["confidence_score"] == pytest.approx(0.95)


def test_insights_summary(client: TestClient):
    # Add two entries
    for text in ["First entry about joy", "Second entry about reflection"]:
        client.post("/entries", data={"text": text})

    resp = client.get("/insights/summary")
    assert resp.status_code == 200, resp.text
    summary = resp.json()
    assert summary["total_entries"] >= 2
    assert summary["total_words"] > 0
    assert "entries_per_day" in summary


def test_insights_query(client: TestClient):
    client.post("/entries", data={"text": "Feeling happy today"})
    resp = client.post("/insights/query", json={"question": "How have I felt?"})
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["answer"]
    assert payload["used_entry_ids"]


def test_backwards_compatibility_memory_type_default(client: TestClient):
    """
    Simulate legacy entry objects missing memory_type and ensure we default to 'event'.
    """
    from app.routers import insights as insights_router

    class Legacy:
        def __init__(self):
            self.id = "legacy-id"
            self.created_at = None
            self.summary = "legacy summary"
            self.original_text = "legacy text"
            self.memory_type = None
            self.tags = None

    legacy_entry = Legacy()
    assert insights_router._memory_type(legacy_entry) == "event"


def test_confirm_entry_updates_confidence_and_timestamp(client: TestClient):
    create = client.post("/entries", data={"text": "I like hiking and coding."}).json()
    entry_id = create["entry_id"]
    confirm = client.post(f"/entries/{entry_id}/confirm").json()
    assert confirm["entry_id"] == entry_id
    assert confirm["confidence_score"] > create["confidence_score"]
    assert confirm["confidence_score"] <= 1.0
    assert confirm["last_confirmed_at"] is not None


def test_invalid_source_rejected(client: TestClient):
    resp = client.post("/entries", data={"text": "Bad source", "source": "not-valid"})
    assert resp.status_code == 400


def test_confidence_clamped(client: TestClient):
    resp = client.post("/entries", data={"text": "High confidence", "confidence_score": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence_score"] == pytest.approx(1.0)
