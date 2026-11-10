"""runs.invite_token_hash: SHA-256 of the invite token that created the run (read access)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.add_column("runs", sa.Column("invite_token_hash", sa.Text(), nullable=True))
    op.create_index("ix_runs_invite_token_hash", "runs", ["invite_token_hash"])


def downgrade() -> None:
    op.drop_index("ix_runs_invite_token_hash", table_name="runs")
    op.drop_column("runs", "invite_token_hash")
