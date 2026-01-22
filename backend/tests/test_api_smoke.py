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
