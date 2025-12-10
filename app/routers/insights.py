import json
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.database import get_session
from app.models.entry import Entry
from app.services.openai_service import client
from app.services.embedding_service import (
    embed_text,
    deserialize_embedding,
)

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
    topics: List[str] = Field(default_factory=list)
    emotions: List[str] = Field(default_factory=list)
    emotion_scores: Dict[str, float] = Field(default_factory=dict)
    people: List[str] = Field(default_factory=list)
    places: List[str] = Field(default_factory=list)
    word_count: Optional[int] = None


class EntriesPerDay(BaseModel):
    date: str
    count: int


class InsightsSummary(BaseModel):
    total_entries: int
    total_words: int
    average_word_count: float
    entries_per_day: List[EntriesPerDay]
    top_emotions: List[str] = Field(default_factory=list)
    top_topics: List[str] = Field(default_factory=list)
    top_people: List[str] = Field(default_factory=list)
    top_places: List[str] = Field(default_factory=list)


class RecapRequest(BaseModel):
    period: str  # "weekly" or "monthly"


class MoodPoint(BaseModel):
    date: str
    top_emotion: Optional[str] = None
    score: Optional[float] = None


class RecapResponse(BaseModel):
    period: str
    total_entries: int
    total_words: int
    top_emotions: List[str] = Field(default_factory=list)
    top_topics: List[str] = Field(default_factory=list)
    top_people: List[str] = Field(default_factory=list)
    top_places: List[str] = Field(default_factory=list)
    mood_trajectory: List[MoodPoint] = Field(default_factory=list)
    summary: str
    themes: List[str] = Field(default_factory=list)
    highlights: List[str] = Field(default_factory=list)


class InsightsQueryRequest(BaseModel):
    question: str


class UsedEntry(BaseModel):
    id: int
    created_at: datetime
    preview: str


class InsightsQueryResponse(BaseModel):
    answer: str
    used_entry_ids: List[int]
    used_entries: List[UsedEntry] = Field(default_factory=list)


@router.get("/entries", response_model=List[EntryPreview])
def list_entries(session: Session = Depends(get_db_session)):
    """
    Return entry previews for the Insights tab.
    JSON: [{"id":1,"created_at":"ISO","preview":"text","summary":"...","topics":[],"emotions":[],"word_count":0}]
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
                topics=_split(entry.topics),
                emotions=_split(entry.emotions),
                emotion_scores=_json_to_dict(entry.emotion_scores),
                people=_split(entry.people),
                places=_split(entry.places),
                word_count=entry.word_count,
            )
        )

    return previews


@router.get("/summary", response_model=InsightsSummary)
def get_summary(session: Session = Depends(get_db_session)):
    """
    Basic aggregate stats.
    JSON: {"total_entries":0,"total_words":0,"average_word_count":0,"entries_per_day":[...]}
    """
    entries = session.exec(select(Entry)).all()
    total_entries = len(entries)
    total_words = sum(entry.word_count or len((entry.original_text or "").split()) for entry in entries)
    average_word_count = (total_words / total_entries) if total_entries else 0

    counts = Counter()
    topic_counts = Counter()
    emotion_counts = Counter()
    people_counts = Counter()
    places_counts = Counter()

    for entry in entries:
        date_str = entry.created_at.date().isoformat()
        counts[date_str] += 1
        topic_counts.update(_split(entry.topics))
        emotion_counts.update(_split(entry.emotions))
        people_counts.update(_split(entry.people))
        places_counts.update(_split(entry.places))

    entries_per_day = [
        EntriesPerDay(date=date, count=count) for date, count in sorted(counts.items())
    ]

    return InsightsSummary(
        total_entries=total_entries,
        total_words=total_words,
        average_word_count=average_word_count,
        entries_per_day=entries_per_day,
        top_emotions=_top_keys(emotion_counts),
        top_topics=_top_keys(topic_counts),
        top_people=_top_keys(people_counts),
        top_places=_top_keys(places_counts),
    )


@router.post("/query", response_model=InsightsQueryResponse)
async def query_insights(
    payload: InsightsQueryRequest, session: Session = Depends(get_db_session)
):
    """
    Answer a user question grounded in stored entries using semantic search.
    JSON: {"answer":"...","used_entry_ids":[1,2],"used_entries":[{"id":1,"created_at":"...","preview":"..."}]}
    """
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    entries = _fetch_similar_entries(question, session, top_k=6)
    if not entries:
        raise HTTPException(
            status_code=404, detail="No entries available for insights yet."
        )

    context_lines: List[str] = []
    used_ids: List[int] = []
    used_entries_meta: List[UsedEntry] = []

    for entry in entries:
        snippet = (entry.summary or entry.original_text or "").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "..."
        context_lines.append(f"[Entry {entry.id} | {entry.created_at.date()}] {snippet}")
        used_ids.append(entry.id)
        used_entries_meta.append(
            UsedEntry(
                id=entry.id,
                created_at=entry.created_at,
                preview=snippet,
            )
        )

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

    return InsightsQueryResponse(
        answer=answer,
        used_entry_ids=used_ids,
        used_entries=used_entries_meta,
    )


@router.get("/weekly", response_model=RecapResponse)
def weekly_recap(session: Session = Depends(get_db_session)):
    return _build_recap(period="weekly", days=7, session=session)


@router.get("/monthly", response_model=RecapResponse)
def monthly_recap(session: Session = Depends(get_db_session)):
    return _build_recap(period="monthly", days=30, session=session)


def _split(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _json_to_dict(value: Optional[str]) -> Dict[str, float]:
    if not value:
        return {}
    try:
        data = json.loads(value)
        if isinstance(data, dict):
            return {k: float(v) for k, v in data.items() if _is_number(v)}
    except Exception:
        return {}
    return {}


def _is_number(val) -> bool:
    try:
        float(val)
        return True
    except Exception:
        return False


def _top_keys(counter: Counter, limit: int = 5) -> List[str]:
    return [item for item, _ in counter.most_common(limit) if item]


def _fetch_similar_entries(
    question: str, session: Session, top_k: int = 5
) -> List[Entry]:
    """
    Embed the question and retrieve top-k entries by cosine similarity.
    Falls back to recent entries if embeddings are missing.
    """
    question_vec = embed_text(question)
    if not question_vec:
        return session.exec(select(Entry).order_by(Entry.created_at.desc()).limit(top_k)).all()

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
        return session.exec(select(Entry).order_by(Entry.created_at.desc()).limit(top_k)).all()

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored[:top_k]]


def _cosine_similarity(a: List[float], b: List[float]) -> Optional[float]:
    if not a or not b or len(a) != len(b):
        return None
    import math

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return None
    return dot / (norm_a * norm_b)


def _build_recap(period: str, days: int, session: Session) -> RecapResponse:
    """
    Build weekly/monthly recaps: gather stats locally, then synthesize summary via OpenAI.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    entries = session.exec(
        select(Entry).where(Entry.created_at >= cutoff).order_by(Entry.created_at)
    ).all()

    if not entries:
        raise HTTPException(status_code=404, detail=f"No entries found for {period} recap.")

    total_entries = len(entries)
    total_words = sum(entry.word_count or len((entry.original_text or "").split()) for entry in entries)

    emotion_counts = Counter()
    topic_counts = Counter()
    people_counts = Counter()
    places_counts = Counter()

    mood_points: List[MoodPoint] = []
    for entry in entries:
        emotion_counts.update(_split(entry.emotions))
        topic_counts.update(_split(entry.topics))
        people_counts.update(_split(entry.people))
        places_counts.update(_split(entry.places))

        scores = _json_to_dict(entry.emotion_scores)
        if scores:
            top_name, top_score = max(scores.items(), key=lambda kv: kv[1])
            mood_points.append(
                MoodPoint(
                    date=entry.created_at.date().isoformat(),
                    top_emotion=top_name,
                    score=round(float(top_score), 3),
                )
            )

    stats_context = {
        "period": period,
        "total_entries": total_entries,
        "total_words": total_words,
        "top_emotions": _top_keys(emotion_counts),
        "top_topics": _top_keys(topic_counts),
        "top_people": _top_keys(people_counts),
        "top_places": _top_keys(places_counts),
        "mood_points": [mp.model_dump() for mp in mood_points],
    }

    summary, themes, highlights = _synthesize_recap(entries, stats_context)

    return RecapResponse(
        period=period,
        total_entries=total_entries,
        total_words=total_words,
        top_emotions=stats_context["top_emotions"],
        top_topics=stats_context["top_topics"],
        top_people=stats_context["top_people"],
        top_places=stats_context["top_places"],
        mood_trajectory=mood_points,
        summary=summary,
        themes=themes,
        highlights=highlights,
    )


def _synthesize_recap(entries: List[Entry], stats: Dict) -> Tuple[str, List[str], List[str]]:
    """
    Use OpenAI to synthesize a recap from locally computed stats + entry snippets.
    """
    snippets = []
    for entry in entries:
        text = (entry.summary or entry.original_text or "").strip()
        if len(text) > 240:
            text = text[:240] + "..."
        snippets.append(f"[{entry.created_at.date()}] {text}")

    system_msg = (
        "You are a personal memory analyst. Given journal entry snippets and local stats, "
        "write a concise recap that feels personal and grounded in the user's entries. "
        "Keep it brief and do not invent facts beyond the provided snippets."
    )
    user_content = (
        f"Period: {stats['period']}\n"
        f"Total entries: {stats['total_entries']}\n"
        f"Total words: {stats['total_words']}\n"
        f"Top emotions: {stats['top_emotions']}\n"
        f"Top topics: {stats['top_topics']}\n"
        f"Top people: {stats['top_people']}\n"
        f"Top places: {stats['top_places']}\n"
        f"Mood points: {stats['mood_points']}\n\n"
        "Entry snippets:\n" + "\n".join(snippets)
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_content},
            ],
            temperature=0.5,
        )
    except Exception:
        return (
            "Unable to generate a recap right now.",
            [],
            [],
        )

    content = resp.choices[0].message.content if resp.choices else ""
    summary = content or "No recap generated."

    themes: List[str] = []
    highlights: List[str] = []
    if summary:
        parts = [p.strip("-• ").strip() for p in summary.split("\n") if p.strip()]
        if len(parts) > 1:
            themes = parts[: min(3, len(parts))]
            highlights = parts[min(3, len(parts)) :]

    return summary, themes, highlights
