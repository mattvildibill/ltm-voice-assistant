"""Initial entry table

Revision ID: 0001
Revises:
Create Date: 2024-01-01
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "entry",
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
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table("entry")
