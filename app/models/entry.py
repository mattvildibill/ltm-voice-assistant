from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class Entry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # "text", "audio", "live" etc.
    source_type: str

    # full text (typed or transcribed audio)
    original_text: str

    # analysis fields
    summary: Optional[str] = None
    themes: Optional[str] = None
    emotions: Optional[str] = None
    memory_chunks: Optional[str] = None  # JSON string or joined text

    created_at: datetime = Field(default_factory=datetime.utcnow)
