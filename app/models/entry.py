from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON, String
from sqlmodel import SQLModel, Field


class MemoryType(str, Enum):
    EVENT = "event"
    REFLECTION = "reflection"
    PREFERENCE = "preference"
    IDENTITY = "identity"
    PROJECT = "project"


class SourceType(str, Enum):
    TYPED = "typed"
    VOICE = "voice"
    INFERRED = "inferred"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class Entry(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)

    user_id: str = Field(default="default-user", index=True)
    memory_type: MemoryType = Field(
        default=MemoryType.EVENT,
        sa_column=Column(String(32), nullable=False, index=True),
    )
    title: Optional[str] = None

    # "text", "audio", "live" etc.
    source_type: str

    # full text (typed or transcribed audio)
    original_text: str
    # normalized content field for memory schema
    content: str

    # tags as a JSON array stored in the DB
    tags: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Optional list of tags for the memory",
    )

    # analysis fields
    summary: Optional[str] = None
    themes: Optional[str] = None
    emotions: Optional[str] = None
    memory_chunks: Optional[str] = None  # JSON string or joined text
    emotion_scores: Optional[str] = None  # JSON string of emotion->score
    topics: Optional[str] = None  # comma-delimited topics
    people: Optional[str] = None  # comma-delimited people
    places: Optional[str] = None  # comma-delimited places
    word_count: Optional[int] = None
    embedding: Optional[str] = None  # JSON array of floats
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None

    # trust/verification fields
    confidence_score: float = Field(default=0.75)
    source: SourceType = Field(
        default=SourceType.UNKNOWN,
        sa_column=Column(String(32), nullable=False, index=True),
    )
    last_confirmed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    created_at: datetime = Field(default_factory=datetime.utcnow)
