from collections import Counter
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.database import get_session
from app.models.entry import Entry
from app.services.openai_service import client

router = APIRouter(prefix="/insights", tags=["insights"])


def get_db_session():
    """Provide a scoped session per request."""
    with get_session() as session:
        yield session


class EntryPreview(BaseModel):
    id: int
    created_at: datetime
    preview: str
    summary: Optional[str] = None


class EntriesPerDay(BaseModel):
    date: str
    count: int


class InsightsSummary(BaseModel):
    total_entries: int
    total_words: int
    entries_per_day: List[EntriesPerDay]


class InsightsQueryRequest(BaseModel):
    question: str


class InsightsQueryResponse(BaseModel):
    answer: str
    used_entry_ids: List[int]


@router.get("/entries", response_model=List[EntryPreview])
def list_entries(session: Session = Depends(get_db_session)):
    """
    Return entry previews for the Insights tab.
    JSON: [{"id":1,"created_at":"ISO","preview":"text","summary":"..."}]
    """
    entries = session.exec(select(Entry).order_by(Entry.created_at.desc())).all()

    previews: List[EntryPreview] = []
    for entry in entries:
        preview_text = (entry.summary or entry.original_text or "").strip()
        if len(preview_text) > 160:
            preview_text = preview_text[:157] + "..."

        previews.append(
            EntryPreview(
                id=entry.id,
                created_at=entry.created_at,
                preview=preview_text,
                summary=entry.summary,
            )
        )

    return previews


@router.get("/summary", response_model=InsightsSummary)
def get_summary(session: Session = Depends(get_db_session)):
    """
    Basic aggregate stats.
    JSON: {"total_entries":0,"total_words":0,"entries_per_day":[{"date":"YYYY-MM-DD","count":1}]}
    """
    entries = session.exec(select(Entry)).all()
    total_entries = len(entries)
    total_words = sum(len((entry.original_text or "").split()) for entry in entries)

    counts = Counter()
    for entry in entries:
        date_str = entry.created_at.date().isoformat()
        counts[date_str] += 1

    entries_per_day = [
        EntriesPerDay(date=date, count=count) for date, count in sorted(counts.items())
    ]

    return InsightsSummary(
        total_entries=total_entries,
        total_words=total_words,
        entries_per_day=entries_per_day,
    )


@router.post("/query", response_model=InsightsQueryResponse)
async def query_insights(
    payload: InsightsQueryRequest, session: Session = Depends(get_db_session)
):
    """
    Answer a user question grounded in stored entries.
    JSON: {"answer":"...","used_entry_ids":[1,2]}
    """
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    entries = (
        session.exec(select(Entry).order_by(Entry.created_at.desc()).limit(12)).all()
    )
    if not entries:
        raise HTTPException(
            status_code=404, detail="No entries available for insights yet."
        )

    context_lines: List[str] = []
    used_ids: List[int] = []
    for entry in entries:
        snippet = (entry.summary or entry.original_text or "").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "..."
        context_lines.append(f"[Entry {entry.id} | {entry.created_at.date()}] {snippet}")
        used_ids.append(entry.id)

    system_msg = (
        "You are a concise personal historian. "
        "Answer the question using only the provided journal entries. "
        "If the context is insufficient, say so politely."
    )
    user_content = (
        f"Question: {question}\n\n"
        "Entries (most recent first):\n"
        + "\n".join(context_lines)
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
    except Exception as exc:  # pragma: no cover - handled at runtime
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate insight: {exc}",
        ) from exc

    answer = response.choices[0].message.content if response.choices else ""
    if not answer:
        answer = "I could not generate an answer from the stored entries."

    return InsightsQueryResponse(answer=answer, used_entry_ids=used_ids)
