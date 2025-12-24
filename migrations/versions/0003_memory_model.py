"""Introduce memory model fields and UUID ids

Revision ID: 0003
Revises: 0002
Create Date: 2024-11-27
"""

from datetime import datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "entry_new" in inspector.get_table_names():
        op.drop_table("entry_new")

    op.create_table(
        "entry_new",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False, server_default="default-user"),
        sa.Column("memory_type", sa.String(length=32), nullable=False, server_default="event"),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("themes", sa.Text(), nullable=True),
        sa.Column("emotions", sa.Text(), nullable=True),
        sa.Column("memory_chunks", sa.Text(), nullable=True),
        sa.Column("emotion_scores", sa.Text(), nullable=True),
        sa.Column("topics", sa.Text(), nullable=True),
        sa.Column("people", sa.Text(), nullable=True),
        sa.Column("places", sa.Text(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("sentiment_label", sa.Text(), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    rows = conn.exec_driver_sql("SELECT * FROM entry").mappings().all()

    entry_new = sa.table(
        "entry_new",
        sa.column("id", sa.String()),
        sa.column("user_id", sa.String()),
        sa.column("memory_type", sa.String()),
        sa.column("title", sa.Text()),
        sa.column("source_type", sa.String()),
        sa.column("original_text", sa.Text()),
        sa.column("content", sa.Text()),
        sa.column("tags", sa.JSON()),
        sa.column("summary", sa.Text()),
        sa.column("themes", sa.Text()),
        sa.column("emotions", sa.Text()),
        sa.column("memory_chunks", sa.Text()),
        sa.column("emotion_scores", sa.Text()),
        sa.column("topics", sa.Text()),
        sa.column("people", sa.Text()),
        sa.column("places", sa.Text()),
        sa.column("word_count", sa.Integer()),
        sa.column("embedding", sa.Text()),
        sa.column("sentiment_label", sa.Text()),
        sa.column("sentiment_score", sa.Float()),
        sa.column("created_at", sa.DateTime()),
    )

    payload = []
    for row in rows:
        created_at = row.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except Exception:
                created_at = None
        payload.append(
            {
                "id": str(uuid4()),
                "user_id": row.get("user_id", "default-user"),
                "memory_type": row.get("memory_type", "event"),
                "title": row.get("title"),
                "source_type": row.get("source_type"),
                "original_text": row.get("original_text"),
                "content": row.get("content") or row.get("original_text"),
                "tags": row.get("tags"),
                "summary": row.get("summary"),
                "themes": row.get("themes"),
                "emotions": row.get("emotions"),
                "memory_chunks": row.get("memory_chunks"),
                "emotion_scores": row.get("emotion_scores"),
                "topics": row.get("topics"),
                "people": row.get("people"),
                "places": row.get("places"),
                "word_count": row.get("word_count"),
                "embedding": row.get("embedding"),
                "sentiment_label": row.get("sentiment_label"),
                "sentiment_score": row.get("sentiment_score"),
                "created_at": created_at,
            }
        )

    if payload:
        op.bulk_insert(entry_new, payload)

    op.drop_table("entry")
    op.rename_table("entry_new", "entry")

    # Remove server defaults after migration copy
    with op.batch_alter_table("entry") as batch_op:
        batch_op.alter_column("user_id", server_default=None)
        batch_op.alter_column("memory_type", server_default=None)


def downgrade():
    conn = op.get_bind()
    op.create_table(
        "entry_old",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_type", sa.String, nullable=False),
        sa.Column("original_text", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("themes", sa.Text, nullable=True),
        sa.Column("emotions", sa.Text, nullable=True),
        sa.Column("memory_chunks", sa.Text, nullable=True),
        sa.Column("emotion_scores", sa.Text, nullable=True),
        sa.Column("topics", sa.Text, nullable=True),
        sa.Column("people", sa.Text, nullable=True),
        sa.Column("places", sa.Text, nullable=True),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("embedding", sa.Text, nullable=True),
        sa.Column("sentiment_label", sa.Text, nullable=True),
        sa.Column("sentiment_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    rows = conn.exec_driver_sql("SELECT * FROM entry").mappings().all()
    entry_old = sa.table(
        "entry_old",
        sa.column("id", sa.Integer()),
        sa.column("source_type", sa.String()),
        sa.column("original_text", sa.Text()),
        sa.column("summary", sa.Text()),
        sa.column("themes", sa.Text()),
        sa.column("emotions", sa.Text()),
        sa.column("memory_chunks", sa.Text()),
        sa.column("emotion_scores", sa.Text()),
        sa.column("topics", sa.Text()),
        sa.column("people", sa.Text()),
        sa.column("places", sa.Text()),
        sa.column("word_count", sa.Integer()),
        sa.column("embedding", sa.Text()),
        sa.column("sentiment_label", sa.Text()),
        sa.column("sentiment_score", sa.Float()),
        sa.column("created_at", sa.DateTime()),
    )

    payload = []
    for idx, row in enumerate(rows, 1):
        created_at = row.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except Exception:
                created_at = None
        payload.append(
            {
                "id": idx,
                "source_type": row.get("source_type"),
                "original_text": row.get("original_text") or row.get("content"),
                "summary": row.get("summary"),
                "themes": row.get("themes"),
                "emotions": row.get("emotions"),
                "memory_chunks": row.get("memory_chunks"),
                "emotion_scores": row.get("emotion_scores"),
                "topics": row.get("topics"),
                "people": row.get("people"),
                "places": row.get("places"),
                "word_count": row.get("word_count"),
                "embedding": row.get("embedding"),
                "sentiment_label": row.get("sentiment_label"),
                "sentiment_score": row.get("sentiment_score"),
                "created_at": created_at,
            }
        )

    if payload:
        op.bulk_insert(entry_old, payload)

    op.drop_table("entry")
    op.rename_table("entry_old", "entry")
