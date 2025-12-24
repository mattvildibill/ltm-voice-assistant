import json
import os
from datetime import datetime
from typing import Optional

from fastapi import UploadFile
from dotenv import load_dotenv

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


async def process_entry(
    text: Optional[str],
    file: Optional[UploadFile],
    user_id: str,
    source: Optional[str] = None,
    confidence_score: Optional[float] = None,
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
        return {"error": "No text or audio content provided."}

    # Compute basic metrics
    word_count = len(text.split())

    source_enum = _normalize_source(source, has_audio=bool(file))
    confidence = _normalize_confidence(confidence_score, source_enum)

    # Run analysis pipeline for richer metadata
    analysis = analyze_text(text)
    memory_type = classify_memory_type(text)

    # Extract safe fields
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

    themes_str = ", ".join(themes) if isinstance(themes, list) else None
    topics_str = ", ".join(topics) if isinstance(topics, list) else None
    # Extract emotion names for quick display
    emotion_names = []
    emotion_score_map = {}
    if isinstance(emotions, list):
        for emo in emotions:
            name = emo.get("name") if isinstance(emo, dict) else None
            score = emo.get("score") if isinstance(emo, dict) else None
            if name:
                emotion_names.append(name)
            if name is not None and score is not None:
                try:
                    emotion_score_map[name] = float(score)
                except (TypeError, ValueError):
                    continue
    emotions_str = ", ".join(emotion_names) if emotion_names else None
    emotion_scores_str = json.dumps(emotion_score_map) if emotion_score_map else None
    people_str = ", ".join(people) if isinstance(people, list) else None
    places_str = ", ".join(places) if isinstance(places, list) else None
    memory_chunks_str = json.dumps(memory_chunks) if memory_chunks else None

    # Create embedding for semantic search
    # If embedding model changes, re-embed historical entries via a script/migration.
    embedding_vec = embed_text(text)
    embedding_str = serialize_embedding(embedding_vec)

    # Store in database
    with get_session() as session:
        entry = Entry(
            user_id=user_id,
            source_type=source_type,
            original_text=text,
            content=text,
            summary=summary,
            themes=themes_str,
            emotions=emotions_str,
            emotion_scores=emotion_scores_str,
            topics=topics_str,
            people=people_str,
            places=places_str,
            memory_chunks=memory_chunks_str,
            word_count=word_count,
            embedding=embedding_str,
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            memory_type=memory_type,
            tags=topics if isinstance(topics, list) else None,
            source=source_enum,
            confidence_score=confidence,
            last_confirmed_at=None,
            updated_at=datetime.utcnow(),
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)

    return {
        "entry_id": entry.id,
        "source_type": source_type,
        "input_text": text,
        "analysis": analysis,
        "transcription_meta": transcript_meta,
        "message": "Entry processed and stored successfully",
        "word_count": word_count,
        "memory_type": entry.memory_type,
        "source": entry.source,
        "confidence_score": entry.confidence_score,
        "last_confirmed_at": entry.last_confirmed_at,
        "updated_at": entry.updated_at,
    }
