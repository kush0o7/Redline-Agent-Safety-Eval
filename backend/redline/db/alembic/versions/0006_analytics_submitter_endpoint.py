"""rename user_email to submitter, add custom_endpoint flag

Revision ID: 0006_analytics_submitter
Revises: 0005_run_stream_token
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_analytics_submitter"
down_revision = "0005_run_stream_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The column held leaderboard display names, never emails — rename to match reality.
    op.alter_column("analytics_events", "user_email", new_column_name="submitter")
    op.add_column(
        "analytics_events",
        sa.Column("custom_endpoint", sa.Boolean(), nullable=True, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("analytics_events", "custom_endpoint")
    op.alter_column("analytics_events", "submitter", new_column_name="user_email")
