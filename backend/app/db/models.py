from __future__ import annotations

import uuid
from sqlalchemy import Boolean, Float, ForeignKey, Integer, Text, DateTime, event, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, GUID, JSONBCompat, TextArray


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=func.now())

    testcases = relationship("Testcase", back_populates="project")
    runs = relationship("Run", back_populates="project")


class Testcase(Base):
    __tablename__ = "testcases"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("projects.id"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    expected_behavior: Mapped[dict] = mapped_column(JSONBCompat(), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    tags: Mapped[list[str]] = mapped_column(TextArray(), nullable=False, default=list)
    # Test pack this case belongs to ("core" or a domain pack such as "financial_services").
    pack: Mapped[str] = mapped_column(Text, nullable=False, default="core", server_default="core")
    # SHA-256 of the fields that determine how this case is run and scored
    # (see utils.hashing.testcase_content_hash). Set automatically on insert.
    content_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=func.now())

    project = relationship("Project", back_populates="testcases")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("projects.id"), nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    llm_model: Mapped[str] = mapped_column(Text, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[dict | None] = mapped_column(JSONBCompat())
    agent_endpoint_url: Mapped[str | None] = mapped_column(Text)
    agent_endpoint_key: Mapped[str | None] = mapped_column(Text)
    stream_token: Mapped[str | None] = mapped_column(Text)
    # The exact case set this run used: testcase row IDs (in run order) and an
    # order-independent hash of their content. Lets reruns reuse the same cases
    # and lets compare detect runs that didn't test the same thing.
    testcase_ids: Mapped[list[str] | None] = mapped_column(JSONBCompat())
    case_set_hash: Mapped[str | None] = mapped_column(Text)
    # Run whose case set this run reused (quick-eval rerun_of).
    rerun_of: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("runs.id"))

    project = relationship("Project", back_populates="runs")
    results = relationship("RunResult", back_populates="run")
    traces = relationship("Trace", back_populates="run")


class RunResult(Base):
    __tablename__ = "run_results"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("runs.id"), nullable=False)
    testcase_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("testcases.id"), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scores: Mapped[dict] = mapped_column(JSONBCompat(), nullable=False)
    raw_output: Mapped[str] = mapped_column(Text, nullable=False)
    refusal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    judge_reasoning: Mapped[dict | None] = mapped_column(JSONBCompat())
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), default=func.now())

    run = relationship("Run", back_populates="results")


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("runs.id"), nullable=False)
    testcase_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("testcases.id"), nullable=False)
    events: Mapped[list[dict]] = mapped_column(JSONBCompat(), nullable=False)
    injection_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    run = relationship("Run", back_populates="traces")


class InviteToken(Base):
    __tablename__ = "invite_tokens"

    token: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str | None] = mapped_column(Text)           # e.g. "for alice"
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    expires_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    event: Mapped[str] = mapped_column(Text, nullable=False)          # e.g. "run_completed"
    model: Mapped[str | None] = mapped_column(Text)
    tier: Mapped[str | None] = mapped_column(Text)
    pass_rate: Mapped[float | None] = mapped_column(Float)
    testcase_count: Mapped[int | None] = mapped_column(Integer)
    submitter: Mapped[str | None] = mapped_column(Text)               # leaderboard display name
    custom_endpoint: Mapped[bool | None] = mapped_column(Boolean, default=False)  # run used a user-supplied agent endpoint
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def compute_testcase_hash(tc: "Testcase") -> str:
    from app.utils.hashing import testcase_content_hash

    return testcase_content_hash(
        type=tc.type,
        name=tc.name,
        prompt=tc.prompt,
        expected_behavior=tc.expected_behavior,
        severity=tc.severity,
        pack=tc.pack,
    )


@event.listens_for(Testcase, "before_insert")
def _set_testcase_hash(mapper, connection, target: "Testcase") -> None:
    if not target.content_hash:
        target.content_hash = compute_testcase_hash(target)
