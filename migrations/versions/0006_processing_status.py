"""Add processing status fields to entry

Revision ID: 0006
Revises: 0005
Create Date: 2025-02-07
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("entry", sa.Column("processing_status", sa.String(length=32), nullable=True))
    op.add_column("entry", sa.Column("processing_error", sa.Text(), nullable=True))

    op.execute("UPDATE entry SET processing_status = COALESCE(processing_status, 'complete')")

    with op.batch_alter_table("entry") as batch_op:
        batch_op.alter_column(
            "processing_status",
            existing_type=sa.String(length=32),
            nullable=False,
            server_default=None,
        )


def downgrade():
    op.drop_column("entry", "processing_error")
    op.drop_column("entry", "processing_status")
