import json
from datetime import datetime
from typing import Optional

from fastapi import BackgroundTasks, UploadFile
from dotenv import load_dotenv
from sqlmodel import select

from app.services.analysis_service import analyze_text
from app.services.realtime_transcription_service import transcribe_realtime
from app.services.embedding_service import embed_text, serialize_embedding
from app.db.database import get_session
from app.models.entry import Entry, MemoryType, SourceType

load_dotenv()

# Confidence defaults by source
DEFAULT_CONFIDENCE = {
    SourceType.TYPED: 0.95,
    SourceType.VOICE: 0.85,
    SourceType.EXTERNAL: 0.80,
    SourceType.INFERRED: 0.60,
    SourceType.UNKNOWN: 0.75,
}

def classify_memory_type(text: str) -> MemoryType:
    """
    Heuristic memory type classifier.
    Prefer simple keyword cues so we can swap in a real model later.
    """
    normalized = (text or "").lower()
    if any(phrase in normalized for phrase in ["i like", "i love", "i prefer", "i enjoy", "favorite"]):
        return MemoryType.PREFERENCE
    if any(
        phrase in normalized
        for phrase in [
            "i believe",
            "i think",
            "i feel that",
            "i realized",
            "i learned",
            "i reflect",
            "reflected on",
            "reflection on",
        ]
    ):
        return MemoryType.REFLECTION
    if any(phrase in normalized for phrase in ["i am ", "i'm ", "my role", "as a ", "i see myself"]):
        return MemoryType.IDENTITY
    if any(phrase in normalized for phrase in ["working on", "building", "project", "roadmap", "planning to", "shipping"]):
        return MemoryType.PROJECT
    return MemoryType.EVENT


def _normalize_source(source: Optional[str], has_audio: bool) -> SourceType:
    if has_audio:
        return SourceType.VOICE
    if source:
        try:
            return SourceType(source)
        except ValueError:
            raise ValueError("Invalid source type.")
    return SourceType.TYPED


def _normalize_confidence(confidence: Optional[float], source: SourceType) -> float:
    def clamp(val: float) -> float:
        return max(0.0, min(1.0, val))

    if confidence is None:
        return DEFAULT_CONFIDENCE.get(source, 0.75)
    try:
        val = float(confidence)
    except (TypeError, ValueError):
        raise ValueError("Confidence score must be a number.")
    return clamp(val)


def _stringify_list(value) -> Optional[str]:
    if isinstance(value, list):
        cleaned = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(cleaned) if cleaned else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _extract_analysis_fields(analysis: Optional[dict]) -> dict:
    if not isinstance(analysis, dict):
        analysis = {}

    summary = analysis.get("summary")
    themes = analysis.get("themes")
    topics = analysis.get("topics")
    emotions = analysis.get("emotions")
    people = analysis.get("people")
    places = analysis.get("places")
    memory_chunks = analysis.get("memory_chunks")
    sentiment = analysis.get("sentiment") or {}

    sentiment_label = None
    sentiment_score = None
    if isinstance(sentiment, dict):
        sentiment_label = sentiment.get("label")
        try:
            sentiment_score = float(sentiment.get("score")) if sentiment.get("score") is not None else None
        except (TypeError, ValueError):
            sentiment_score = None

    themes_str = _stringify_list(themes)
    topics_str = _stringify_list(topics)
    people_str = _stringify_list(people)
    places_str = _stringify_list(places)

    emotion_names = []
    emotion_score_map = {}
    if isinstance(emotions, list):
        for emo in emotions:
            if isinstance(emo, dict):
                name = emo.get("name")
                score = emo.get("score")
            elif isinstance(emo, str):
                name = emo.strip()
                score = None
            else:
                name = None
                score = None
            if name:
                emotion_names.append(name)
            if name is not None and score is not None:
                try:
                    emotion_score_map[name] = float(score)
                except (TypeError, ValueError):
                    continue

    emotions_str = ", ".join(emotion_names) if emotion_names else None
    emotion_scores_str = json.dumps(emotion_score_map) if emotion_score_map else None
    memory_chunks_str = json.dumps(memory_chunks) if memory_chunks else None

    summary_val = summary.strip() if isinstance(summary, str) else None

    return {
        "summary": summary_val or None,
        "themes": themes_str,
        "topics": topics_str,
        "emotions": emotions_str,
        "emotion_scores": emotion_scores_str,
        "people": people_str,
        "places": places_str,
        "memory_chunks": memory_chunks_str,
        "sentiment_label": sentiment_label,
        "sentiment_score": sentiment_score,
        "tags": topics if isinstance(topics, list) else None,
    }


def _run_analysis_pipeline(entry_id: str, user_id: str, text: str) -> None:
    error_messages = []
    analysis_fields = {}
    try:
        analysis = analyze_text(text)
        analysis_fields = _extract_analysis_fields(analysis)
    except Exception as exc:
        error_messages.append(f"analysis failed: {exc}")

    embedding_vec = embed_text(text)
    embedding_str = serialize_embedding(embedding_vec)
    if embedding_vec is None:
        error_messages.append("embedding failed")

    with get_session() as session:
        entry = session.exec(
            select(Entry).where(Entry.id == entry_id, Entry.user_id == user_id)
        ).first()
        if not entry:
            return

        for key, value in analysis_fields.items():
            setattr(entry, key, value)

        entry.embedding = embedding_str
        entry.processing_status = "failed" if error_messages else "complete"
        entry.processing_error = "; ".join(error_messages) if error_messages else None
        entry.updated_at = datetime.utcnow()
        session.add(entry)
        session.commit()


async def process_entry(
    text: Optional[str],
    file: Optional[UploadFile],
    source: Optional[str] = None,
    confidence_score: Optional[float] = None,
    user_id: str = "default-user",
    background_tasks: Optional[BackgroundTasks] = None,
):
    """
    Handles text OR audio entries.
    Audio uses advanced realtime transcription.
    """

    source_type = "text"
    transcript_meta = None

    # If audio present → transcribe audio
    if file:
        transcript_meta = await transcribe_realtime(file)
        text = transcript_meta["text"]
        source_type = "audio"

    if not text or text.strip() == "":
        raise ValueError("No text or audio content provided.")

    # Compute basic metrics
    word_count = len(text.split())

    source_enum = _normalize_source(source, has_audio=bool(file))
    confidence = _normalize_confidence(confidence_score, source_enum)

    memory_type = classify_memory_type(text)

    # Store in database
    with get_session() as session:
        entry = Entry(
            user_id=user_id,
            source_type=source_type,
            original_text=text,
            content=text,
            word_count=word_count,
            memory_type=memory_type,
            source=source_enum,
            confidence_score=confidence,
            last_confirmed_at=None,
            updated_at=datetime.utcnow(),
            processing_status="pending",
            processing_error=None,
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)

    if background_tasks:
        background_tasks.add_task(_run_analysis_pipeline, entry.id, user_id, text)
    else:
        _run_analysis_pipeline(entry.id, user_id, text)

    return {
        "entry_id": entry.id,
        "source_type": source_type,
        "input_text": text,
        "analysis": None,
        "transcription_meta": transcript_meta,
        "message": "Entry processed and stored successfully",
        "word_count": word_count,
        "memory_type": entry.memory_type,
        "source": entry.source,
        "confidence_score": entry.confidence_score,
        "last_confirmed_at": entry.last_confirmed_at,
        "updated_at": entry.updated_at,
        "processing_status": entry.processing_status,
        "processing_error": entry.processing_error,
    }
