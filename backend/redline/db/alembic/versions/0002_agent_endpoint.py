"""add agent_endpoint_url and agent_endpoint_key to runs

Revision ID: 0002_agent_endpoint
Revises: 0001_initial
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_agent_endpoint"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("agent_endpoint_url", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("agent_endpoint_key", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "agent_endpoint_key")
    op.drop_column("runs", "agent_endpoint_url")
