"""record each run's exact case set: testcase content hashes, run case-set hash, rerun_of

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    op.add_column("testcases", sa.Column("content_hash", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("testcase_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("runs", sa.Column("case_set_hash", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("rerun_of", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_runs_rerun_of", "runs", "runs", ["rerun_of"], ["id"])
    # Older rows keep NULL hashes; the app computes them on demand from row content.


def downgrade() -> None:
    op.drop_constraint("fk_runs_rerun_of", "runs", type_="foreignkey")
    op.drop_column("runs", "rerun_of")
    op.drop_column("runs", "case_set_hash")
    op.drop_column("runs", "testcase_ids")
    op.drop_column("testcases", "content_hash")
