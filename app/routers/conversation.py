import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.database import get_session
from app.models.entry import Entry
from app.services.embedding_service import embed_text, deserialize_embedding
from app.services.openai_service import client

router = APIRouter(prefix="/conversation", tags=["conversation"])


class ConversationTurn(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ConversationRequest(BaseModel):
    message: str
    history: List[ConversationTurn] = Field(default_factory=list)


class ConversationResponse(BaseModel):
    response: str
    used_entry_ids: List[int] = Field(default_factory=list)


# Simple in-memory conversation state (single-user use case)
conversation_state: Dict[str, List[ConversationTurn]] = {"messages": []}
MAX_HISTORY = 20


def get_db_session():
    """Provide a scoped session per request."""
    with get_session() as session:
        yield session


@router.post("/respond", response_model=ConversationResponse)
async def conversation_respond(
    payload: ConversationRequest, session: Session = Depends(get_db_session)
):
    """
    Chat with stored entries. Uses embeddings to retrieve relevant memories.
    JSON in: {"message":"...","history":[{"role":"user","content":"..."}, ...]}
    JSON out: {"response":"...","used_entry_ids":[1,2]}
    """
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Merge provided history with server-side state (favor client-provided)
    history = payload.history or conversation_state["messages"]
    history = history[-MAX_HISTORY:]

    entries = _fetch_similar_entries(message, session, top_k=6)
    if not entries:
        raise HTTPException(
            status_code=404, detail="No entries available for conversation yet."
        )

    used_ids: List[int] = []
    entry_context_lines: List[str] = []
    for entry in entries:
        snippet = (entry.summary or entry.original_text or "").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "..."
        entry_context_lines.append(
            f"[Entry {entry.id} | {entry.created_at.date()}] {snippet}"
        )
        used_ids.append(entry.id)

    system_msg = (
        "You are a personal memory companion. "
        "Answer conversationally using ONLY the provided journal entries. "
        "If the context is insufficient, be honest about not knowing."
    )

    messages = [{"role": "system", "content": system_msg}]
    messages.append(
        {
            "role": "system",
            "content": "Relevant entries:\n" + "\n".join(entry_context_lines),
        }
    )
    # Add prior conversation to keep continuity
    for turn in history:
        if turn.role in ("user", "assistant"):
            messages.append({"role": turn.role, "content": turn.content})

    messages.append({"role": "user", "content": message})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.4,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500, detail=f"Failed to generate response: {exc}"
        ) from exc

    reply = response.choices[0].message.content if response.choices else ""
    if not reply:
        reply = "I could not generate a response from your stored entries."

    # Update in-memory state
    conversation_state["messages"].extend(
        [ConversationTurn(role="user", content=message), ConversationTurn(role="assistant", content=reply)]
    )
    conversation_state["messages"] = conversation_state["messages"][-MAX_HISTORY:]

    return ConversationResponse(response=reply, used_entry_ids=used_ids)


def _fetch_similar_entries(
    question: str, session: Session, top_k: int = 5
) -> List[Entry]:
    """
    Embed the question and retrieve top-k entries by cosine similarity.
    Falls back to recent entries if embeddings are missing.
    """
    question_vec = embed_text(question)
    if not question_vec:
        return (
            session.exec(select(Entry).order_by(Entry.created_at.desc()).limit(top_k)).all()
        )

    entries = session.exec(select(Entry)).all()
    scored: List[Tuple[float, Entry]] = []
    for entry in entries:
        vec = deserialize_embedding(entry.embedding)
        if not vec:
            continue
        sim = _cosine_similarity(question_vec, vec)
        if sim is not None:
            scored.append((sim, entry))

    if not scored:
        return (
            session.exec(select(Entry).order_by(Entry.created_at.desc()).limit(top_k)).all()
        )

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]


def _cosine_similarity(a: List[float], b: List[float]) -> Optional[float]:
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return None
    return dot / (norm_a * norm_b)
