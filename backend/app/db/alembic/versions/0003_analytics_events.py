"""add analytics_events table

Revision ID: 0003_analytics_events
Revises: 0002_agent_endpoint
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_analytics_events"
down_revision = "0002_agent_endpoint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("tier", sa.Text(), nullable=True),
        sa.Column("pass_rate", sa.Float(), nullable=True),
        sa.Column("testcase_count", sa.Integer(), nullable=True),
        sa.Column("user_email", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_analytics_events_event", "analytics_events", ["event"])
    op.create_index("ix_analytics_events_created_at", "analytics_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("analytics_events")
