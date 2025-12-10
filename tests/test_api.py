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
    monkeypatch.setattr(insights_router, "embed_text", lambda text: [0.1, 0.2, 0.3])

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
        insights_router, "deserialize_embedding", lambda raw: [0.1, 0.2, 0.3]
    )
    monkeypatch.setattr(
        conversation_router, "deserialize_embedding", lambda raw: [0.1, 0.2, 0.3]
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
    assert data["word_count"] > 0


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
