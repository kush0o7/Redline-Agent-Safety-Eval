"""runs.excluded_categories: scoring categories a quick-eval chose not to test

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    op.add_column("runs", sa.Column("excluded_categories", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "excluded_categories")
