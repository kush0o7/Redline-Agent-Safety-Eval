"""runs.system_prompt_mode + runs.custom_system_prompt: which system prompt the target got

NULL on older runs means the Redline default (the only behaviour before this column).

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"


def upgrade() -> None:
    op.add_column("runs", sa.Column("system_prompt_mode", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("custom_system_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "custom_system_prompt")
    op.drop_column("runs", "system_prompt_mode")
