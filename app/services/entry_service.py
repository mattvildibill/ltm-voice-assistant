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

    # Run analysis pipeline
    analysis = analyze_text(text)

    # Extract safe fields
    summary = analysis.get("summary")
    themes = analysis.get("themes")
    emotions = analysis.get("emotions")
    memory_chunks = analysis.get("memory_chunks")

    themes_str = ", ".join(themes) if isinstance(themes, list) else None
    emotions_str = ", ".join(emotions) if isinstance(emotions, list) else None
    memory_chunks_str = json.dumps(memory_chunks) if memory_chunks else None

    # Store in database
    with get_session() as session:
        entry = Entry(
            source_type=source_type,
            original_text=text,
            summary=summary,
            themes=themes_str,
            emotions=emotions_str,
            memory_chunks=memory_chunks_str,
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
    }
