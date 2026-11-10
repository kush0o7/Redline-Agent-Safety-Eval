"""system_prompt_mode: none / redline / custom, stored on the run, delivered as chosen, reported, kept on reruns."""
import asyncio
import uuid

import pytest

from app.agents import system_prompt as sp
from app.db.models import Run
from app.evals import runner
from app.llm.prompts import BASELINE_SYSTEM_PROMPT
from app.llm.provider import FakeProvider
from app.queue import tasks

HEADERS = {"X-Admin-Key": "test-key-0123456789abcdef"}
ENDPOINT = "https://agent.test/v1"
MY_PROMPT = "You are AcmeBank's support assistant. Never move money without a signed mandate."


class Recorder(FakeProvider):
    """FakeProvider that records the system messages of every request."""
    def __init__(self):
        self.systems: list[list[str]] = []

    def _note(self, messages):
        self.systems.append([m.content for m in messages if m.role == "system"])

    async def complete(self, messages, model, temperature, seed):
        self._note(messages)
        return await super().complete(messages, model, temperature, seed)

    async def complete_with_tools(self, messages, model, temperature, seed, tools):
        self._note(messages)
        return await super().complete_with_tools(messages, model, temperature, seed, tools)


@pytest.fixture(autouse=True)
def resolvable_endpoint(monkeypatch):
    """agent.test resolves to an allowlisted address, so the SSRF guard accepts it offline."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "agent_endpoint_allowlist", "agent.test,127.0.0.0/8")
    monkeypatch.setattr("app.core.security.socket.getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("127.0.0.1", 0))])


@pytest.fixture
def recorder(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(runner, "get_provider_for_run", lambda run: rec)
    return rec


def _start(client, **payload):
    body = {"model": "fake-safe", **({} if "rerun_of" in payload else {"testcase_count": 8}), **payload}
    resp = client.post("/quick-eval", json=body, headers=HEADERS)
    assert resp.status_code == 200, resp.text
    asyncio.run(tasks.run_eval_task({}, resp.json()["run_id"]))
    return resp.json()


# ── resolve(): defaults and validation ──

@pytest.mark.parametrize("requested,custom,endpoint,mode,expected", [
    (None, None, ENDPOINT, "baseline", ("none", None)),          # agent endpoint: test it as users get it
    (None, None, None, "baseline", ("redline", None)),           # plain model: unchanged behaviour
    (None, MY_PROMPT, None, "baseline", ("custom", MY_PROMPT)),  # a custom prompt implies custom
    ("redline", None, ENDPOINT, "baseline", ("redline", None)),  # explicit choice wins
    ("custom", f"  {MY_PROMPT}\n", ENDPOINT, "baseline", ("custom", MY_PROMPT)),
    (None, None, ENDPOINT, "debate", ("redline", None)),         # debate uses its own role prompts
])
def test_resolve_defaults(requested, custom, endpoint, mode, expected):
    assert sp.resolve(requested, custom, mode=mode, agent_endpoint_url=endpoint) == expected


@pytest.mark.parametrize("requested,custom,mode,msg", [
    ("custom", None, "baseline", "needs a non-empty custom_system_prompt"),
    ("custom", "   ", "baseline", "needs a non-empty custom_system_prompt"),
    ("none", MY_PROMPT, "baseline", "only used with system_prompt_mode=custom"),
    ("none", None, "debate", "debate mode"),
    ("custom", MY_PROMPT, "debate", "debate mode"),
    ("custom", "x" * (sp.MAX_CUSTOM_CHARS + 1), "baseline", "at most"),
])
def test_resolve_rejects(requested, custom, mode, msg):
    with pytest.raises(sp.SystemPromptError, match=msg):
        sp.resolve(requested, custom, mode=mode, agent_endpoint_url=None)


def test_describe_never_includes_custom_text():
    d = sp.describe("custom", MY_PROMPT)
    assert d["mode"] == "custom" and d["custom_chars"] == len(MY_PROMPT) and len(d["custom_sha256"]) == 12
    assert MY_PROMPT not in str(d) and d["label"].startswith("custom (")
    assert sp.describe("none", None)["label"] == "none"
    assert sp.describe("redline", None)["label"] == "Redline default"
    assert sp.describe(None, None)["mode"] == "redline"  # runs from before the option


# ── delivery: what the target actually receives ──

def test_agent_endpoint_run_defaults_to_no_system_prompt(client, db, recorder):
    body = _start(client, agent_endpoint_url=ENDPOINT, packs=["core"])
    run = db.get(Run, uuid.UUID(body["run_id"]))
    assert run.system_prompt_mode == "none" and body["system_prompt"]["label"] == "none"
    assert recorder.systems and all(s == [] for s in recorder.systems)  # plain and tool-loop requests alike
    assert run.summary["system_prompt"]["mode"] == "none"


def test_model_run_keeps_redline_default(client, recorder):
    body = _start(client)
    assert body["system_prompt"]["mode"] == "redline"
    assert recorder.systems and all(s == [BASELINE_SYSTEM_PROMPT] for s in recorder.systems)


def test_custom_prompt_is_sent_verbatim_but_not_echoed(client, db, recorder):
    body = _start(client, agent_endpoint_url=ENDPOINT, system_prompt_mode="custom", custom_system_prompt=MY_PROMPT)
    assert recorder.systems and all(s == [MY_PROMPT] for s in recorder.systems)
    status = client.get(f"/quick-eval/{body['run_id']}", headers=HEADERS)
    report = client.get(f"/quick-eval/{body['run_id']}/report", headers=HEADERS).text
    assert MY_PROMPT not in status.text and MY_PROMPT not in report
    assert f"System prompt: custom ({len(MY_PROMPT)} characters, sha256 {sp.fingerprint(MY_PROMPT)})" in report


def test_api_validation_errors_are_422(client):
    r = client.post("/quick-eval", json={"testcase_count": 3, "system_prompt_mode": "custom"}, headers=HEADERS)
    assert r.status_code == 422 and "custom_system_prompt" in r.json()["detail"]
    r = client.post("/quick-eval", json={"testcase_count": 3, "system_prompt_mode": "bogus"}, headers=HEADERS)
    assert r.status_code == 422
    r = client.post("/quick-eval", json={"testcase_count": 3, "mode": "debate", "system_prompt_mode": "none"}, headers=HEADERS)
    assert r.status_code == 422 and "debate" in r.json()["detail"]


def test_admin_runs_route_takes_the_option(client, db):
    pid = client.post("/projects", json={"name": f"sp-{uuid.uuid4().hex[:6]}"}, headers=HEADERS).json()["id"]
    client.post(f"/projects/{pid}/seed-testcases", headers=HEADERS)
    tc_id = client.get(f"/projects/{pid}/testcases", headers=HEADERS).json()[0]["id"]
    resp = client.post(f"/projects/{pid}/runs", headers=HEADERS, json={
        "testcase_ids": [tc_id], "mode": "baseline", "llm_model": "fake", "agent_endpoint_url": ENDPOINT})
    assert resp.status_code == 200 and resp.json()["system_prompt"]["mode"] == "none"


# ── reruns and compare ──

def test_rerun_keeps_the_original_system_prompt(client, db, recorder):
    base = _start(client, system_prompt_mode="custom", custom_system_prompt=MY_PROMPT)
    again = _start(client, model="fake-degraded", rerun_of=base["run_id"])
    run = db.get(Run, uuid.UUID(again["run_id"]))
    assert run.system_prompt_mode == "custom" and run.custom_system_prompt == MY_PROMPT
    cmp = client.get(f"/quick-eval/{again['run_id']}/compare", params={"base_run_id": base["run_id"]}, headers=HEADERS).json()
    assert cmp["system_prompt"]["identical"] is True and cmp["system_prompt"]["warning"] is None
    assert not any("system prompt" in n for n in cmp["release"]["notes"])


def test_rerun_with_a_different_prompt_is_flagged(client):
    base = _start(client)
    again = _start(client, rerun_of=base["run_id"], system_prompt_mode="none")
    assert again["system_prompt"]["mode"] == "none"
    q = {"base_run_id": base["run_id"]}
    cmp = client.get(f"/quick-eval/{again['run_id']}/compare", params=q, headers=HEADERS).json()
    assert cmp["system_prompt"]["identical"] is False
    assert "different system prompts (before: Redline default; after: none)" in cmp["system_prompt"]["warning"]
    assert any("different system prompts" in n for n in cmp["release"]["notes"])
    html = client.get(f"/quick-eval/{again['run_id']}/compare/report", params=q, headers=HEADERS).text
    assert "System prompt differs." in html and "System prompt: Redline default · none" in html


def test_legacy_runs_report_redline_default(client, db):
    body = _start(client)
    run = db.get(Run, uuid.UUID(body["run_id"]))
    run.system_prompt_mode = None
    db.commit()
    html = client.get(f"/quick-eval/{body['run_id']}/report", headers=HEADERS).text
    assert "System prompt: Redline default (recorded before system_prompt_mode existed)" in html
