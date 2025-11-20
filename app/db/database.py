import os
from sqlmodel import SQLModel, create_engine, Session

# Location of your SQLite DB file
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ltm.db")

# Create the engine
engine = create_engine(DATABASE_URL, echo=False)


def init_db() -> None:
    """Create database tables on startup."""
    # Import here to avoid circular import issues
    from app.models.entry import Entry  
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    """Return a new SQLModel session."""
    return Session(engine)
