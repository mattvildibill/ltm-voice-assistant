"""create user

Revision ID: 0005_create_user
Revises: 0004_trust_fields
Create Date: 2025-02-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_create_user"
down_revision = "0004_trust_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.drop_table("user")
