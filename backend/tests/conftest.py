import os

os.environ.setdefault("ADMIN_API_KEY", "test-key-0123456789abcdef")
os.environ.setdefault("POSTGRES_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("DEV_FAKE_PROVIDER", "true")
os.environ.setdefault("DEV_FAKE_JUDGE", "true")
os.environ.setdefault("REDLINE_ENV", "development")
# The rate limiter keeps per-IP state for the whole process, and the suite makes
# more calls than the defaults allow (5 quick-evals per 5 min, 60+20 requests per min).
os.environ.setdefault("EVAL_RATE_LIMIT", "100000")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100000")

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db import session as db_session
from app.main import app


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def db(db_engine):
    TestingSessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db_session.engine = db_engine
    db_session.SessionLocal = TestingSessionLocal
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    fake_pool = MagicMock()
    fake_pool.enqueue_job = AsyncMock()
    app.state.arq_pool = fake_pool
    return TestClient(app)
