import uuid

from app.queue import tasks


def test_api_smoke(client, db, monkeypatch):
    monkeypatch.setattr(tasks, "enqueue_run", lambda run_id: None)

    headers = {"X-Admin-Key": "test-key"}

    resp = client.post("/projects", json={"name": "demo"}, headers=headers)
    assert resp.status_code == 200
    project_id = resp.json()["id"]

    resp = client.post(f"/projects/{project_id}/seed-testcases", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["inserted"] >= 30

    resp = client.get(f"/projects/{project_id}/testcases", headers=headers)
    testcase_ids = [row["id"] for row in resp.json()][:3]

    resp = client.post(
        f"/projects/{project_id}/runs",
        json={"testcase_ids": testcase_ids, "mode": "baseline", "llm_model": "fake", "seed": 1},
        headers=headers,
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    tasks.run_eval_task(run_id)

    resp = client.get(f"/projects/{project_id}/runs/{run_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    resp = client.get(f"/projects/{project_id}/runs/{run_id}/results", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 3

    tc_id = testcase_ids[0]
    resp = client.get(f"/projects/{project_id}/runs/{run_id}/traces/{tc_id}", headers=headers)
    assert resp.status_code == 200


def test_compare_runs_endpoint(client, db, monkeypatch):
    monkeypatch.setattr(tasks, "enqueue_run", lambda run_id: None)
    headers = {"X-Admin-Key": "test-key"}

    resp = client.post("/projects", json={"name": "compare-demo"}, headers=headers)
    assert resp.status_code == 200
    project_id = resp.json()["id"]

    resp = client.post(f"/projects/{project_id}/seed-testcases", headers=headers)
    assert resp.status_code == 200

    resp = client.get(f"/projects/{project_id}/testcases", headers=headers)
    testcase_ids = [row["id"] for row in resp.json()][:3]

    run_ids = []
    for seed in (1, 2):
        resp = client.post(
            f"/projects/{project_id}/runs",
            json={"testcase_ids": testcase_ids, "mode": "baseline", "llm_model": "fake", "seed": seed},
            headers=headers,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        run_ids.append(run_id)
        tasks.run_eval_task(run_id)

    compare_resp = client.get(
        f"/projects/{project_id}/runs/compare",
        params={"base_run_id": run_ids[0], "candidate_run_id": run_ids[1]},
        headers=headers,
    )
    assert compare_resp.status_code == 200
    payload = compare_resp.json()
    assert payload["base_run_id"] == run_ids[0]
    assert payload["candidate_run_id"] == run_ids[1]
    assert payload["common_total"] == 3
    assert "pass_rate_delta" in payload
    assert "metrics" in payload
