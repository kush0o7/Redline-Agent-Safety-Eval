"""drop traces.injection_detected (regex annotation removed; injection is graded in code)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.drop_column("traces", "injection_detected")


def downgrade() -> None:
    op.add_column("traces", sa.Column("injection_detected", sa.Boolean(), server_default=sa.text("false"), nullable=False))
