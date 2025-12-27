"""Add flag fields to entry

Revision ID: 0005
Revises: 0004
Create Date: 2025-02-06
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("entry", sa.Column("is_flagged", sa.Boolean(), nullable=True))
    op.add_column("entry", sa.Column("flagged_reason", sa.Text(), nullable=True))

    op.execute("UPDATE entry SET is_flagged = COALESCE(is_flagged, 0)")

    with op.batch_alter_table("entry") as batch_op:
        batch_op.alter_column(
            "is_flagged", existing_type=sa.Boolean(), nullable=False, server_default=None
        )


def downgrade():
    op.drop_column("entry", "flagged_reason")
    op.drop_column("entry", "is_flagged")
