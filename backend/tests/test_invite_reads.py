"""Invite tokens in production: the token that created a run can read it (and only its own runs)."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.db.models import InviteToken, Run
from app.queue import tasks

ADMIN = {"X-Admin-Key": "test-key-0123456789abcdef"}


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(settings, "redline_env", "production")
    monkeypatch.setattr(settings, "require_eval_auth_override", None)


def _invite(client, max_uses=10):
    return client.post("/admin/invite", params={"label": "t", "max_uses": max_uses}, headers=ADMIN).json()["token"]


def _run(client, headers, **payload):
    body = {"model": "fake-safe", **({} if "rerun_of" in payload else {"testcase_count": 3}), **payload}
    resp = client.post("/quick-eval", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    asyncio.run(tasks.run_eval_task({}, resp.json()["run_id"]))
    return resp.json()["run_id"]


def _reads(base, cand):
    return [f"/quick-eval/{cand}", f"/quick-eval/{cand}/report",
            f"/quick-eval/{cand}/compare?base_run_id={base}", f"/quick-eval/{cand}/compare/report?base_run_id={base}"]


def test_invite_reads_its_own_runs_in_production(client, production, db):
    tok = _invite(client)
    inv = {"X-Invite-Token": tok}
    base = _run(client, inv)
    cand = _run(client, inv, model="fake-degraded", rerun_of=base)
    for url in _reads(base, cand):
        assert client.get(url, headers=inv).status_code == 200, url
        assert client.get(url).status_code == 401, url
        assert client.get(url, headers=ADMIN).status_code == 200, url
    # Only a hash is stored on the run, never the token itself.
    stored = db.get(Run, __import__("uuid").UUID(base)).invite_token_hash
    assert stored and tok not in stored and len(stored) == 64


def test_invite_cannot_read_other_runs(client, production):
    mine, other = {"X-Invite-Token": _invite(client)}, {"X-Invite-Token": _invite(client)}
    admin_run = _run(client, ADMIN)
    other_run = _run(client, other)
    my_run = _run(client, mine)
    for rid in (admin_run, other_run):
        assert client.get(f"/quick-eval/{rid}", headers=mine).status_code == 401
    # A compare needs both runs to be the token's own.
    assert client.get(f"/quick-eval/{my_run}/compare?base_run_id={other_run}", headers=mine).status_code == 401
    assert client.get(f"/quick-eval/{other_run}/compare?base_run_id={my_run}", headers=mine).status_code == 401
    # Nor can it rerun someone else's run (that would reveal its case set).
    resp = client.post("/quick-eval", json={"rerun_of": other_run}, headers=mine)
    assert resp.status_code == 404
    assert client.get("/quick-eval/not-a-uuid", headers=mine).status_code == 401


def test_used_up_invite_still_reads_but_expired_or_deleted_does_not(client, production, db):
    tok = _invite(client, max_uses=1)
    inv = {"X-Invite-Token": tok}
    rid = _run(client, inv)
    # max_uses limits new runs, not reads.
    assert client.post("/quick-eval", json={"testcase_count": 3}, headers=inv).status_code == 401
    assert client.get(f"/quick-eval/{rid}", headers=inv).status_code == 200
    row = db.get(InviteToken, tok)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.get(f"/quick-eval/{rid}", headers=inv).status_code == 401
    db.delete(row)
    db.commit()
    assert client.get(f"/quick-eval/{rid}", headers=inv).status_code == 401


def test_demo_runs_store_no_invite_hash(client, monkeypatch, db):
    monkeypatch.setattr(settings, "redline_env", "demo")
    monkeypatch.setattr(settings, "require_eval_auth_override", None)
    rid = _run(client, {"X-Invite-Token": "anything"})
    assert db.get(Run, __import__("uuid").UUID(rid)).invite_token_hash is None
