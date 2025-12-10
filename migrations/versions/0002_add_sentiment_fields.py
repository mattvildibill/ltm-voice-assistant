"""Add sentiment fields to entry

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("entry", sa.Column("sentiment_label", sa.Text(), nullable=True))
    op.add_column("entry", sa.Column("sentiment_score", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("entry", "sentiment_label")
    op.drop_column("entry", "sentiment_score")
