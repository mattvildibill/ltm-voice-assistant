from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.database import get_session
from app.models.entry import Entry
from app.services.embedding_service import find_similar_entries
from app.services.openai_service import client

router = APIRouter(prefix="/conversation", tags=["conversation"])


class ConversationTurn(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ConversationRequest(BaseModel):
    messages: List[ConversationTurn] = Field(default_factory=list)


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
    Chat with stored entries using embeddings to retrieve context.
    JSON in: {"messages":[{"role":"user","content":"..."}, ...]}
    JSON out: {"response":"...","used_entry_ids":[1,2]}
    """
    messages_in = payload.messages[-MAX_HISTORY:] if payload.messages else []
    if not messages_in or messages_in[-1].role != "user":
        raise HTTPException(status_code=400, detail="A final user message is required.")

    user_message = messages_in[-1].content.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    entries = _fetch_similar_entries(user_message, session, top_k=6)
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
    for turn in messages_in:
        if turn.role in ("user", "assistant"):
            messages.append({"role": turn.role, "content": turn.content})

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

    # Update in-memory state as a single-user cache
    conversation_state["messages"] = (conversation_state["messages"] + messages_in)[
        -MAX_HISTORY:
    ]
    conversation_state["messages"].append(ConversationTurn(role="assistant", content=reply))
    conversation_state["messages"] = conversation_state["messages"][-MAX_HISTORY:]

    return ConversationResponse(response=reply, used_entry_ids=used_ids)


def _fetch_similar_entries(
    question: str, session: Session, top_k: int = 5
) -> List[Entry]:
    """
    Embed the question and retrieve top-k entries by cosine similarity.
    Falls back to recent entries if embeddings are missing.
    """
    entries = session.exec(select(Entry)).all()
    scored = find_similar_entries(question, entries, top_k=top_k)
    if scored:
        return [entry for _, entry in scored]
    return (
        session.exec(select(Entry).order_by(Entry.created_at.desc()).limit(top_k)).all()
    )
