"""Agent endpoint API keys must never be stored in plain text, on any code path."""
import ast
import uuid
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import settings
from app.core.security import decrypt_field
from app.db.models import Run

HEADERS = {"X-Admin-Key": "test-key-0123456789abcdef"}
SECRET = "sk-agent-secret-DO-NOT-STORE-0123456789"
APP_DIR = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture()
def fernet_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "field_encryption_key", key)
    # Allow the test endpoint URL through the SSRF guard without DNS.
    monkeypatch.setattr(settings, "agent_endpoint_allowlist", "agent.test,127.0.0.0/8")
    monkeypatch.setattr("app.core.security.socket.getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("127.0.0.1", 0))])
    return key


def _raw_key(db, run_id: str) -> str:
    # Core select on the table: returns exactly what is stored (the column is plain
    # Text, so nothing in the ORM decrypts it on the way out).
    runs = Run.__table__
    return db.execute(select(runs.c.agent_endpoint_key).where(runs.c.id == uuid.UUID(run_id))).scalar_one()


def _assert_encrypted(stored: str):
    assert stored and SECRET not in stored
    assert decrypt_field(stored) == SECRET


def test_quick_eval_stores_ciphertext(client, db, fernet_key):
    resp = client.post(
        "/quick-eval",
        json={"testcase_count": 2, "agent_endpoint_url": "https://agent.test/v1", "agent_endpoint_key": SECRET},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    _assert_encrypted(_raw_key(db, resp.json()["run_id"]))


def test_project_runs_endpoint_stores_ciphertext(client, db, fernet_key):
    pid = client.post("/projects", json={"name": f"enc-{uuid.uuid4().hex[:6]}"}, headers=HEADERS).json()["id"]
    client.post(f"/projects/{pid}/seed-testcases", headers=HEADERS)
    tc_id = client.get(f"/projects/{pid}/testcases", headers=HEADERS).json()[0]["id"]
    resp = client.post(
        f"/projects/{pid}/runs",
        json={
            "testcase_ids": [tc_id], "mode": "baseline", "llm_model": "fake", "seed": 1,
            "agent_endpoint_url": "https://agent.test/v1", "agent_endpoint_key": SECRET,
        },
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    _assert_encrypted(_raw_key(db, resp.json()["run_id"]))


def test_every_write_of_agent_endpoint_key_is_encrypted():
    """Static guard: any `agent_endpoint_key=` keyword or attribute assignment in app code
    must wrap its value in encrypt_field(...). Catches new code paths that forget."""
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            values = []
            if isinstance(node, ast.keyword) and node.arg == "agent_endpoint_key":
                values.append(node.value)
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Attribute) and t.attr == "agent_endpoint_key":
                        values.append(node.value)
            for v in values:
                ok = isinstance(v, ast.Call) and getattr(v.func, "id", getattr(v.func, "attr", None)) == "encrypt_field"
                if not ok:
                    offenders.append(f"{path.relative_to(APP_DIR)}:{v.lineno}")
    assert not offenders, f"agent_endpoint_key written without encrypt_field at: {offenders}"
