import json
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.database import get_session
from app.models.entry import Entry
from app.services.openai_service import client
from app.services.retrieval_scoring import rerank_entries

router = APIRouter(prefix="/insights", tags=["insights"])


def get_db_session():
    """Provide a scoped session per request."""
    with get_session() as session:
        yield session


class EntryPreview(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    preview: str
    summary: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    emotions: List[str] = Field(default_factory=list)
    emotion_scores: Dict[str, float] = Field(default_factory=dict)
    people: List[str] = Field(default_factory=list)
    places: List[str] = Field(default_factory=list)
    word_count: Optional[int] = None
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None
    memory_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    confidence_score: Optional[float] = None
    last_confirmed_at: Optional[datetime] = None


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
    average_sentiment_score: Optional[float] = None


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
    average_sentiment: Optional[float] = None
    summary: str
    themes: List[str] = Field(default_factory=list)
    highlights: List[str] = Field(default_factory=list)


class InsightsQueryRequest(BaseModel):
    question: str
    debug: bool = False


class UsedEntry(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    preview: str
    memory_type: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    confidence_score: Optional[float] = None
    last_confirmed_at: Optional[datetime] = None


class InsightsQueryResponse(BaseModel):
    answer: str
    used_entry_ids: List[str]
    used_entries: List[UsedEntry] = Field(default_factory=list)
    debug: Optional[List[Dict]] = None


class PromptResponse(BaseModel):
    prompt: str
    source: str = "ai"
    note: Optional[str] = None


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
                updated_at=entry.updated_at,
                preview=preview_text,
                summary=entry.summary,
                topics=_split(entry.topics),
                emotions=_split(entry.emotions),
                emotion_scores=_json_to_dict(entry.emotion_scores),
                people=_split(entry.people),
                places=_split(entry.places),
                word_count=entry.word_count,
                sentiment_label=entry.sentiment_label,
                sentiment_score=entry.sentiment_score,
                memory_type=_memory_type(entry),
                tags=_listify(entry.tags),
                source=_source(entry),
                confidence_score=_confidence(entry),
                last_confirmed_at=getattr(entry, "last_confirmed_at", None),
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
    total_words = sum(_entry_word_count(entry) for entry in entries)
    average_word_count = (total_words / total_entries) if total_entries else 0

    counts = Counter()
    topic_counts = Counter()
    emotion_counts = Counter()
    people_counts = Counter()
    places_counts = Counter()
    sentiment_scores: List[float] = []

    for entry in entries:
        date_str = entry.created_at.date().isoformat()
        counts[date_str] += 1
        topic_counts.update(_split(entry.topics))
        emotion_counts.update(_split(entry.emotions))
        people_counts.update(_split(entry.people))
        places_counts.update(_split(entry.places))
        if entry.sentiment_score is not None:
            sentiment_scores.append(entry.sentiment_score)

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
        average_sentiment_score=(sum(sentiment_scores) / len(sentiment_scores)) if sentiment_scores else None,
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

    fetched = _fetch_similar_entries(question, session, top_k=6, debug=payload.debug)
    if isinstance(fetched, tuple):
        entries, debug_data = fetched
    else:
        entries = fetched
        debug_data = None
    if not entries:
        raise HTTPException(
            status_code=404, detail="No entries available for insights yet."
        )

    context_lines: List[str] = []
    used_ids: List[str] = []
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
                updated_at=entry.updated_at,
                preview=snippet,
                memory_type=_memory_type(entry),
                tags=_listify(entry.tags),
                source=_source(entry),
                confidence_score=_confidence(entry),
                last_confirmed_at=getattr(entry, "last_confirmed_at", None),
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
        debug=debug_data if payload.debug else None,
    )


@router.get("/weekly", response_model=RecapResponse)
def weekly_recap(session: Session = Depends(get_db_session)):
    return _build_recap(period="weekly", days=7, session=session)


@router.get("/monthly", response_model=RecapResponse)
def monthly_recap(session: Session = Depends(get_db_session)):
    return _build_recap(period="monthly", days=30, session=session)


@router.get("/prompt", response_model=PromptResponse)
def generate_prompt(session: Session = Depends(get_db_session)):
    """
    Generate a writing/chat prompt tailored to recent entries (topics, people, places).
    Falls back to a generic idea if no entries or OpenAI is unavailable.
    """
    entries = session.exec(select(Entry).order_by(Entry.created_at.desc()).limit(20)).all()
    if not entries:
        return PromptResponse(
            prompt="Think back on this week: what moment surprised you and how did it change your mood or plans?",
            source="fallback",
            note="No entries found; returned a generic prompt.",
        )

    topic_counts = Counter()
    people_counts = Counter()
    places_counts = Counter()
    for entry in entries:
        topic_counts.update(_split(entry.topics))
        people_counts.update(_split(entry.people))
        places_counts.update(_split(entry.places))

    context = {
        "top_topics": _top_keys(topic_counts, limit=5),
        "top_people": _top_keys(people_counts, limit=5),
        "top_places": _top_keys(places_counts, limit=5),
        "latest_dates": [entry.created_at.date().isoformat() for entry in entries[:3]],
    }

    prompt = _synthesize_prompt(entries, context)
    if not prompt:
        return PromptResponse(
            prompt="Recall a recent conversation or event that stuck with you. What did it reveal about what you value most right now?",
            source="fallback",
            note="Unable to reach OpenAI; returned a generic prompt.",
        )

    return PromptResponse(prompt=prompt, source="ai")


def _memory_type(entry: Entry) -> str:
    value = getattr(entry, "memory_type", None)
    return value.value if hasattr(value, "value") else (value or "event")


def _listify(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
            if isinstance(loaded, list):
                return [str(v).strip() for v in loaded if str(v).strip()]
        except Exception:
            pass
    return _split(value if isinstance(value, str) else str(value))


def _source(entry: Entry) -> str:
    value = getattr(entry, "source", None)
    return value.value if hasattr(value, "value") else (value or "unknown")


def _confidence(entry: Entry) -> Optional[float]:
    try:
        return float(getattr(entry, "confidence_score", None))
    except (TypeError, ValueError):
        return None


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


def _entry_word_count(entry: Entry) -> int:
    if entry.word_count is not None:
        return entry.word_count
    return len((entry.original_text or "").split())


def _fetch_similar_entries(
    question: str, session: Session, top_k: int = 5, debug: bool = False
) -> Union[List[Entry], Tuple[List[Entry], Optional[List[Dict]]]]:
    """
    Candidate generation (top-50 similarity) followed by reranking with context-aware scoring.
    Returns entries, and debug metadata if requested.
    """
    all_entries = session.exec(select(Entry)).all()
    result = rerank_entries(question, all_entries, top_n=top_k, candidate_k=50, debug=debug)
    if debug:
        return result.entries, result.debug
    return result.entries


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
    total_words = sum(_entry_word_count(entry) for entry in entries)

    emotion_counts = Counter()
    topic_counts = Counter()
    people_counts = Counter()
    places_counts = Counter()
    sentiment_scores: List[float] = []

    mood_points: List[MoodPoint] = []
    for entry in entries:
        emotion_counts.update(_split(entry.emotions))
        topic_counts.update(_split(entry.topics))
        people_counts.update(_split(entry.people))
        places_counts.update(_split(entry.places))
        if entry.sentiment_score is not None:
            sentiment_scores.append(entry.sentiment_score)

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
        "average_sentiment": (sum(sentiment_scores) / len(sentiment_scores)) if sentiment_scores else None,
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
        average_sentiment=stats_context["average_sentiment"],
        summary=summary,
        themes=themes,
        highlights=highlights,
    )


def _synthesize_prompt(entries: List[Entry], context: Dict) -> str:
    """
    Generate a conversational prompt tailored to recent topics/people/places.
    """
    snippets = []
    for entry in entries[:10]:
        text = (entry.summary or entry.original_text or "").strip()
        if len(text) > 140:
            text = text[:137] + "..."
        snippets.append(f"[{entry.created_at.date()}] {text}")

    system_msg = (
        "You are a warm, specific journaling coach. Suggest one question the user can answer. "
        "Blend their recurring topics/people/places into the prompt, keep it brief, grounded, "
        "and conversational. Encourage sensory detail and reflection, not generic advice."
    )
    user_content = (
        f"Top topics: {context.get('top_topics')}\n"
        f"Top people: {context.get('top_people')}\n"
        f"Top places: {context.get('top_places')}\n"
        f"Recent dates: {context.get('latest_dates')}\n\n"
        "Recent snippets:\n" + "\n".join(snippets)
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
        )
    except Exception:
        return ""

    return resp.choices[0].message.content.strip() if resp.choices else ""


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
        "You are a personal memory analyst and gentle storyteller. "
        "Given journal entry snippets and local stats, return a JSON object with keys "
        '`summary` (2-3 sentences, first-person, emotionally aware, grounded in snippets), '
        '`themes` (3 short phrases capturing patterns), and '
        '`highlights` (3 concrete moments or observations, specific and personable). '
        "Do not invent facts beyond the provided snippets."
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
            temperature=0.6,
        )
    except Exception:
        return (
            "Unable to generate a recap right now.",
            [],
            [],
        )

    content = resp.choices[0].message.content if resp.choices else ""
    if not content:
        return "No recap generated.", [], []

    try:
        payload = json.loads(content)
        summary = payload.get("summary") or "No recap generated."
        themes = [t for t in payload.get("themes", []) if t]
        highlights = [h for h in payload.get("highlights", []) if h]
        return summary, themes, highlights
    except Exception:
        # Fallback to lenient parsing if model returns non-JSON text
        summary = content or "No recap generated."
        parts = [p.strip("-• ").strip() for p in summary.split("\n") if p.strip()]
        themes = parts[: min(3, len(parts))] if parts else []
        highlights = parts[min(3, len(parts)) :] if len(parts) > 3 else []
        return summary, themes, highlights
