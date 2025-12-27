from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    email: str = Field(
        sa_column=Column(String(255), unique=True, index=True, nullable=False)
    )
    password_hash: str = Field(sa_column=Column(String(255), nullable=False))
    display_name: Optional[str] = Field(default=None, max_length=120)
    created_at: datetime = Field(default_factory=datetime.utcnow)
