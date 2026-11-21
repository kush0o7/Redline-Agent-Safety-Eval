"""add pack to testcases

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.add_column("testcases", sa.Column("pack", sa.Text(), nullable=False, server_default="core"))


def downgrade() -> None:
    op.drop_column("testcases", "pack")
