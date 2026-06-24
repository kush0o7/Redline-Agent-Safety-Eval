"""add stream_token to runs

Revision ID: 0005_run_stream_token
Revises: 0004_invite_tokens
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_run_stream_token"
down_revision = "0004_invite_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("stream_token", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "stream_token")
