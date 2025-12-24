"""Add trust/verification fields to entry

Revision ID: 0004
Revises: 0003
Create Date: 2024-11-28
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("entry", sa.Column("confidence_score", sa.Float(), nullable=True))
    op.add_column("entry", sa.Column("source", sa.String(length=32), nullable=True))
    op.add_column("entry", sa.Column("last_confirmed_at", sa.DateTime(), nullable=True))
    op.add_column("entry", sa.Column("updated_at", sa.DateTime(), nullable=True))

    # Backfill existing rows with defaults
    now = datetime.utcnow()
    op.execute(
        "UPDATE entry SET source = COALESCE(source, 'unknown'), "
        "confidence_score = COALESCE(confidence_score, 0.75), "
        "updated_at = COALESCE(updated_at, created_at)"
    )

    # Enforce non-null for source/updated_at after backfill
    with op.batch_alter_table("entry") as batch_op:
        batch_op.alter_column("source", existing_type=sa.String(length=32), nullable=False, server_default=None)
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False, server_default=None)


def downgrade():
    op.drop_column("entry", "updated_at")
    op.drop_column("entry", "last_confirmed_at")
    op.drop_column("entry", "source")
    op.drop_column("entry", "confidence_score")
