"""add invite_tokens table

Revision ID: 0004_invite_tokens
Revises: 0003_analytics_events
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_invite_tokens"
down_revision = "0003_analytics_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invite_tokens",
        sa.Column("token", sa.Text(), primary_key=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("invite_tokens")
