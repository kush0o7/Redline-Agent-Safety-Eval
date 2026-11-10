"""Exact case sets: content hashes, quick-eval rerun_of, and compare flagging non-identical runs."""
import asyncio
import uuid

from app.db.models import Run, Testcase
from app.queue import tasks
from app.utils.hashing import case_set_hash
from app.utils.hashing import testcase_content_hash as content_hash  # aliased: pytest collects test*

HEADERS = {"X-Admin-Key": "test-key-0123456789abcdef"}


def _base_fields(**over):
    f = dict(type="jailbreak", name="x", prompt="p", expected_behavior={"should_refuse": True}, severity=4, pack="core")
    f.update(over)
    return f


def _quick_eval(client, **body):
    resp = client.post("/quick-eval", json=body, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _finish(run_id):
    asyncio.run(tasks.run_eval_task({}, run_id))


def _compare(client, project_id, base, cand):
    resp = client.get(
        f"/projects/{project_id}/runs/compare",
        params={"base_run_id": base, "candidate_run_id": cand},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Hashing ───────────────────────────────────────────────────────────────────

def test_content_hash_is_stable_and_sensitive():
    h = content_hash(**_base_fields())
    assert h == content_hash(**_base_fields(expected_behavior={"should_refuse": True}))
    assert h != content_hash(**_base_fields(prompt="p2"))
    assert h != content_hash(**_base_fields(severity=5))
    assert h != content_hash(**_base_fields(expected_behavior={"should_refuse": False}))
    assert h != content_hash(**_base_fields(pack="financial_services"))
    # key order in expected_behavior doesn't matter
    a = content_hash(**_base_fields(expected_behavior={"a": 1, "b": 2}))
    b = content_hash(**_base_fields(expected_behavior={"b": 2, "a": 1}))
    assert a == b


def test_case_set_hash_is_order_independent():
    assert case_set_hash(["a", "b", "c"]) == case_set_hash(["c", "a", "b"])
    assert case_set_hash(["a", "b"]) != case_set_hash(["a", "b", "c"])


def test_testcase_hash_set_on_insert(db):
    tc = Testcase(project_id=uuid.uuid4(), tags=["t1"], **_base_fields())
    db.add(tc)
    db.commit()
    assert tc.content_hash == content_hash(**_base_fields())


# ── Recording ─────────────────────────────────────────────────────────────────

def test_quick_eval_records_case_set(client, db):
    q = _quick_eval(client, testcase_count=12)
    run = db.get(Run, q["run_id"])
    assert len(run.testcase_ids) == 12
    assert run.case_set_hash == q["case_set_hash"]
    rows = db.query(Testcase).filter(Testcase.id.in_(run.testcase_ids)).all()
    assert case_set_hash(r.content_hash for r in rows) == run.case_set_hash


# ── rerun_of ──────────────────────────────────────────────────────────────────

def test_rerun_reuses_exact_cases_and_compares_clean(client, db):
    first = _quick_eval(client, testcase_count=12, packs=["core", "financial_services"])
    _finish(first["run_id"])
    second = _quick_eval(client, rerun_of=first["run_id"], model="candidate-v2", seed=9)
    _finish(second["run_id"])

    assert second["project_id"] == first["project_id"]
    assert second["case_set_hash"] == first["case_set_hash"]
    assert second["rerun_of"] == first["run_id"]
    r1, r2 = db.get(Run, first["run_id"]), db.get(Run, second["run_id"])
    assert r2.testcase_ids == r1.testcase_ids
    assert r2.llm_model == "candidate-v2"

    status = client.get(f"/quick-eval/{second['run_id']}", headers=HEADERS).json()
    assert status["rerun_of"] == first["run_id"] and status["status"] == "completed"

    cmp = _compare(client, first["project_id"], first["run_id"], second["run_id"])
    assert cmp["common_total"] == 12
    assert cmp["case_set"]["identical"] is True
    assert cmp["case_set"]["warning"] is None


def test_rerun_of_a_rerun(client):
    a = _quick_eval(client, testcase_count=6)
    b = _quick_eval(client, rerun_of=a["run_id"])
    c = _quick_eval(client, rerun_of=b["run_id"])
    assert a["case_set_hash"] == b["case_set_hash"] == c["case_set_hash"]
    assert c["project_id"] == a["project_id"]


def test_rerun_rejects_conflicting_fields(client):
    a = _quick_eval(client, testcase_count=6)
    for extra in ({"testcase_count": 6}, {"packs": ["core"]}, {"name": "x"}):
        resp = client.post("/quick-eval", json={"rerun_of": a["run_id"], **extra}, headers=HEADERS)
        assert resp.status_code == 422, extra
        assert "rerun_of" in resp.json()["detail"]


def test_rerun_unknown_or_malformed_run(client):
    assert client.post("/quick-eval", json={"rerun_of": str(uuid.uuid4())}, headers=HEADERS).status_code == 404
    assert client.post("/quick-eval", json={"rerun_of": "not-a-uuid"}, headers=HEADERS).status_code == 422


def test_rerun_refused_when_cases_changed(client, db):
    a = _quick_eval(client, testcase_count=6)
    run = db.get(Run, a["run_id"])
    tc = db.get(Testcase, uuid.UUID(run.testcase_ids[0]))
    tc.prompt = tc.prompt + " (edited)"
    tc.content_hash = None  # an edit outside the app wouldn't maintain the hash either
    db.commit()
    resp = client.post("/quick-eval", json={"rerun_of": a["run_id"]}, headers=HEADERS)
    assert resp.status_code == 409


def test_rejected_quick_eval_leaves_no_orphan_project(client, db):
    from app.db.models import Project

    before = db.query(Project).count()
    resp = client.post("/quick-eval", json={"testcase_count": 5, "packs": ["nope"]}, headers=HEADERS)
    assert resp.status_code == 422
    assert db.query(Project).count() == before


# ── compare flags non-identical case sets ─────────────────────────────────────

def _project_runs(client, ids_a, ids_b, project_id):
    runs = []
    for ids in (ids_a, ids_b):
        resp = client.post(
            f"/projects/{project_id}/runs",
            json={"testcase_ids": ids, "mode": "baseline", "llm_model": "fake", "seed": 1},
            headers=HEADERS,
        )
        assert resp.status_code == 200, resp.text
        _finish(resp.json()["run_id"])
        runs.append(resp.json()["run_id"])
    return runs


def _seeded_project(client):
    pid = client.post("/projects", json={"name": f"p-{uuid.uuid4().hex[:6]}"}, headers=HEADERS).json()["id"]
    client.post(f"/projects/{pid}/seed-testcases", headers=HEADERS)
    ids = [t["id"] for t in client.get(f"/projects/{pid}/testcases", headers=HEADERS).json()]
    return pid, ids


def test_compare_flags_different_subsets(client):
    pid, ids = _seeded_project(client)
    base, cand = _project_runs(client, ids[:6], ids[3:9], pid)
    cs = _compare(client, pid, base, cand)["case_set"]
    assert cs["identical"] is False
    assert cs["only_in_base"] == 3 and cs["only_in_candidate"] == 3
    assert "not like-for-like" in cs["warning"] and "rerun_of" in cs["warning"]


def test_compare_same_ids_different_order_is_identical(client):
    pid, ids = _seeded_project(client)
    base, cand = _project_runs(client, ids[:5], list(reversed(ids[:5])), pid)
    assert _compare(client, pid, base, cand)["case_set"]["identical"] is True


def test_compare_flags_cases_edited_after_run(client, db):
    pid, ids = _seeded_project(client)
    base, cand = _project_runs(client, ids[:5], ids[:5], pid)
    tc = db.get(Testcase, uuid.UUID(ids[0]))
    tc.prompt = tc.prompt + " (edited)"
    tc.content_hash = None
    db.commit()
    cs = _compare(client, pid, base, cand)["case_set"]
    assert cs["identical"] is False
    assert "changed since" in cs["warning"]


def test_compare_legacy_runs_without_stored_hash(client, db):
    pid, ids = _seeded_project(client)
    base, cand = _project_runs(client, ids[:5], ids[:5], pid)
    for rid in (base, cand):
        r = db.get(Run, uuid.UUID(rid))
        r.case_set_hash = None
        r.testcase_ids = None   # legacy: IDs only in summary
    db.commit()
    cs = _compare(client, pid, base, cand)["case_set"]
    assert cs["identical"] is True
    assert cs["base_case_set_hash"] == cs["candidate_case_set_hash"]
