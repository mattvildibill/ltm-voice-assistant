import os
import json
from typing import Optional

from fastapi import UploadFile
from dotenv import load_dotenv

from app.services.analysis_service import analyze_text
from app.services.realtime_transcription_service import transcribe_realtime
from app.db.database import get_session
from app.models.entry import Entry

load_dotenv()

async def process_entry(text: Optional[str], file: Optional[UploadFile]):
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

    # Run analysis pipeline for richer metadata
    analysis = analyze_text(text)

    # Extract safe fields
    summary = analysis.get("summary")
    themes = analysis.get("themes")
    topics = analysis.get("topics")
    emotions = analysis.get("emotions")
    people = analysis.get("people")
    places = analysis.get("places")
    memory_chunks = analysis.get("memory_chunks")

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

    # Store in database
    with get_session() as session:
        entry = Entry(
            source_type=source_type,
            original_text=text,
            summary=summary,
            themes=themes_str,
            emotions=emotions_str,
            emotion_scores=emotion_scores_str,
            topics=topics_str,
            people=people_str,
            places=places_str,
            memory_chunks=memory_chunks_str,
            word_count=word_count,
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
    }
