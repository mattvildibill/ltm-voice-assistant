from typing import Iterable, Tuple

from sqlmodel import SQLModel, create_engine, Session
from app.core.config import settings

# Create the engine
engine = create_engine(settings.database_url, echo=False)


def init_db() -> None:
    """Create database tables on startup."""
    # Import here to avoid circular import issues
    from app.models.entry import Entry
    from app.models.user import User
    SQLModel.metadata.create_all(engine)


def _ensure_columns_exist(
    table: str, columns: Iterable[Tuple[str, str]]
) -> None:
    """
    Lightweight, idempotent migration helper for SQLite.
    Adds missing columns with provided SQL types.
    """
    with engine.connect() as conn:
        existing = {
            row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
        }
        for name, type_sql in columns:
            if name not in existing:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN {name} {type_sql}"
                )


def migrate_db() -> None:
    """Ensure new metadata columns exist for entries."""
    _ensure_columns_exist(
        "entry",
        [
            ("emotion_scores", "TEXT"),
            ("topics", "TEXT"),
            ("people", "TEXT"),
            ("places", "TEXT"),
            ("word_count", "INTEGER"),
            ("embedding", "TEXT"),
            ("sentiment_label", "TEXT"),
            ("sentiment_score", "FLOAT"),
            ("user_id", "TEXT"),
            ("memory_type", "TEXT"),
            ("title", "TEXT"),
            ("content", "TEXT"),
            ("tags", "TEXT"),
            ("confidence_score", "FLOAT"),
            ("source", "TEXT"),
            ("last_confirmed_at", "DATETIME"),
            ("updated_at", "DATETIME"),
        ],
    )


def get_session() -> Session:
    """Return a new SQLModel session."""
    return Session(engine)
