"""add judge_reasoning to run_results

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.add_column(
        "run_results",
        sa.Column("judge_reasoning", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("run_results", "judge_reasoning")
