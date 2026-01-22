from __future__ import annotations

import uuid
from sqlalchemy import Boolean, Float, ForeignKey, Integer, Text, DateTime, func
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
