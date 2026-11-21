"""The `redline` CLI (Light Mode): compare / scan / report on the simulated models, offline."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from redline import cli, local
from redline.models import (KEYWORD, BoundProvider, ModelError, choose_judge, find_ollama_model, ollama_digest,
                            parse_model)

BACKEND = Path(__file__).resolve().parents[1]


def run_cli(*argv) -> int:
    return cli.main([str(a) for a in argv])


def _rows(out: Path) -> list[dict]:
    return [json.loads(line) for line in (out / "results.jsonl").read_text(encoding="utf-8").splitlines()]


# ── compare / scan / report ──

def test_compare_degraded_fails_with_exit_1_and_writes_files(tmp_path, capsys):
    out = tmp_path / "out"
    assert run_cli("compare", "fake-safe", "fake-degraded", "--cases", 30, "--out", out) == cli.EXIT_FAIL
    text = capsys.readouterr().out
    assert "❌ Don't ship fake-degraded. It's less safe than fake-safe:" in text
    assert "This is very unlikely to be chance." in text
    assert "Chance check (McNemar test)" in text and "Biggest risks" in text and "Tests that broke" in text
    assert "Grader: keyword rules (less reliable than an AI grader)" in text
    assert "We asked:" in text and "fake-safe:" in text and "Why it matters:" in text
    for name in ("report.html", "results.jsonl", "summary.json", "redline.db", "state.json"):
        assert (out / name).exists(), name
    rows = _rows(out)
    assert len(rows) == 60 and {r["model"] for r in rows} == {"fake-safe", "fake-degraded"}
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["release"]["decision"] == "FAIL"
    assert summary["candidate"]["run_info"]["judge"] == "keyword heuristic"
    assert summary["case_set"]["identical"] is True
    assert "Graded by" in (out / "report.html").read_text(encoding="utf-8")


def test_compare_same_model_passes_with_exit_0(tmp_path):
    assert run_cli("compare", "fake-safe", "fake-safe", "--cases", 30, "--out", tmp_path) == cli.EXIT_PASS


def test_scan_exit_codes(tmp_path, capsys):
    assert run_cli("scan", "fake-safe", "--cases", 30, "--out", tmp_path / "a") == cli.EXIT_PASS
    assert "✅ fake-safe passed the bar: safety grade Hardened" in capsys.readouterr().out
    assert run_cli("scan", "fake-degraded", "--cases", 30, "--out", tmp_path / "b") == cli.EXIT_FAIL


def test_report_rewrites_the_files_from_the_folder(tmp_path, capsys):
    run_cli("compare", "fake-safe", "fake-degraded", "--cases", 30, "--out", tmp_path)
    (tmp_path / "report.html").unlink()
    capsys.readouterr()
    assert run_cli("report", tmp_path) == cli.EXIT_FAIL
    assert (tmp_path / "report.html").exists() and "❌ Don't ship fake-degraded" in capsys.readouterr().out


def test_report_on_an_empty_folder_is_an_error(tmp_path, capsys):
    assert run_cli("report", tmp_path) == cli.EXIT_ERROR
    assert "No Redline results" in capsys.readouterr().err


def test_harmful_answers_are_redacted_in_results_jsonl(tmp_path):
    run_cli("compare", "fake-safe", "fake-degraded", "--cases", 40, "--out", tmp_path)
    harmful = [r for r in _rows(tmp_path) if r["model"] == "fake-degraded" and not r["passed"]
               and r["category"] in ("harmful_compliance", "financial_services")]
    assert harmful and all(r["answer"].startswith("[Model") for r in harmful)  # simulated placeholders only


def test_bad_input_exits_2(tmp_path, capsys):
    assert run_cli("compare", "llama3.1", "fake-safe", "--out", tmp_path) == cli.EXIT_ERROR
    assert "use provider/model, e.g. ollama/llama3.1" in capsys.readouterr().err
    assert run_cli("compare", "fake-safe", "fake-degraded", "--packs", "nope", "--out", tmp_path) == cli.EXIT_ERROR
    assert "Unknown test pack" in capsys.readouterr().err


# ── resume, cache, Ctrl-C ──

class _Counter:
    def __init__(self, monkeypatch):
        from redline.llm import provider as p

        self.calls = 0
        original = p.FakeProvider.complete

        async def counting(inner, *a, **k):
            self.calls += 1
            return await original(inner, *a, **k)

        monkeypatch.setattr(p.FakeProvider, "complete", counting)


def test_rerunning_the_same_command_reuses_finished_runs(tmp_path, monkeypatch, capsys):
    run_cli("compare", "fake-safe", "fake-degraded", "--cases", 30, "--out", tmp_path)
    counter = _Counter(monkeypatch)
    capsys.readouterr()
    assert run_cli("compare", "fake-safe", "fake-degraded", "--cases", 30, "--out", tmp_path) == cli.EXIT_FAIL
    assert "already done" in capsys.readouterr().out and counter.calls == 0


def test_new_runs_reuse_cached_answers(tmp_path, monkeypatch):
    """Re-grading (a new job in the same folder) doesn't call the model again."""
    run_cli("compare", "fake-safe", "fake-degraded", "--cases", 30, "--out", tmp_path)
    (tmp_path / "state.json").unlink()
    counter = _Counter(monkeypatch)
    assert run_cli("compare", "fake-safe", "fake-degraded", "--cases", 30, "--out", tmp_path) == cli.EXIT_FAIL
    assert counter.calls == 0
    counter.calls = 0
    (tmp_path / "state.json").unlink()
    assert run_cli("compare", "fake-safe", "fake-degraded", "--cases", 30, "--out", tmp_path, "--no-cache") == cli.EXIT_FAIL
    assert counter.calls > 0


def test_ctrl_c_saves_progress_and_the_same_command_resumes(tmp_path, monkeypatch, capsys):
    from redline.evals import runner

    real_score = runner.score_testcase
    graded = {"n": 0}

    async def interrupt_after_10(*a, **k):
        graded["n"] += 1
        if graded["n"] > 10:
            raise KeyboardInterrupt
        return await real_score(*a, **k)

    monkeypatch.setattr(runner, "score_testcase", interrupt_after_10)
    assert run_cli("compare", "fake-safe", "fake-degraded", "--cases", 30, "--out", tmp_path, "--concurrency", 1) == cli.EXIT_ERROR
    assert "Run the same command again to resume" in capsys.readouterr().err

    store = local.Store(tmp_path / "redline.db")
    state = json.loads((tmp_path / "state.json").read_text())
    from redline.db.models import Run
    import uuid

    with store.Session() as db:
        first = db.get(Run, uuid.UUID(state["runs"][0]))
        assert first.status == "interrupted" and local.stored_results(db, first) == 10

    monkeypatch.setattr(runner, "score_testcase", real_score)
    counter = _Counter(monkeypatch)
    assert run_cli("compare", "fake-safe", "fake-degraded", "--cases", 30, "--out", tmp_path) == cli.EXIT_FAIL
    assert "resuming (10 cases already graded)" in capsys.readouterr().out
    # The first model's 30 answers were all generated before grading started, so only fake-degraded's
    # plain-completion cases call the model now.
    with store.Session() as db:
        first = db.get(Run, uuid.UUID(state["runs"][0]))
        assert first.status == "completed" and local.stored_results(db, first) == 30
        assert first.summary["total"] == 30
    assert counter.calls <= 30


def test_concurrency_does_not_change_results(tmp_path):
    run_cli("compare", "fake-safe", "fake-degraded", "--cases", 30, "--out", tmp_path / "c1", "--concurrency", 1)
    run_cli("compare", "fake-safe", "fake-degraded", "--cases", 30, "--out", tmp_path / "c8", "--concurrency", 8)
    key = lambda out: sorted((r["model"], r["case"], r["passed"]) for r in _rows(out))  # noqa: E731
    assert key(tmp_path / "c1") == key(tmp_path / "c8")


def test_cache_key_changes_with_the_ollama_digest(tmp_path):
    store = local.Store(tmp_path / "x.db")

    class R:
        llm_model, mode, seed = "ollama/hermes3", "baseline", 7

    class T:
        content_hash = "abc"

    a = local.SqliteAnswerCache(store, {"ollama/hermes3": "111111111111"}).key(R, T, "sys")
    b = local.SqliteAnswerCache(store, {"ollama/hermes3": "222222222222"}).key(R, T, "sys")
    assert a != b


# ── model strings and Ollama ──

def test_parse_model_strings():
    assert parse_model("ollama/llama3.1").provider == "ollama"
    assert parse_model("ollama/llama3.1:8b").model == "llama3.1:8b"
    assert parse_model("groq/openai/gpt-oss-120b").model == "openai/gpt-oss-120b"
    spec = parse_model("http://localhost:8000/v1#my-model")
    assert (spec.provider, spec.model, spec.base_url) == ("endpoint", "my-model", "http://localhost:8000/v1")
    assert parse_model("fake-degraded").is_fake
    for bad in ("llama3.1", "mistral/x", "http://localhost:8000/v1", ""):
        with pytest.raises(ModelError):
            parse_model(bad)


def _tags(monkeypatch, names: list[str] | None):
    def fake_get(url, timeout=None):
        if names is None:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, json={"models": [{"name": n, "model": n, "digest": "sha256:" + "ab" * 32} for n in names]},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)


def test_ollama_not_running_is_a_clear_error(tmp_path, monkeypatch, capsys):
    _tags(monkeypatch, None)
    assert run_cli("compare", "ollama/llama3.1", "ollama/hermes3", "--out", tmp_path) == cli.EXIT_ERROR
    err = capsys.readouterr().err
    assert "Ollama isn't running" in err and "ollama serve" in err


def test_missing_ollama_model_says_what_to_pull(tmp_path, monkeypatch, capsys):
    _tags(monkeypatch, ["llama3.1:latest"])
    assert run_cli("compare", "ollama/llama3.1", "ollama/hermes3", "--out", tmp_path) == cli.EXIT_ERROR
    assert "run: ollama pull hermes3" in capsys.readouterr().err.lower()


def test_ollama_name_matching_and_digest():
    models = [{"name": "llama3.1:latest", "digest": "sha256:0123456789abcdef"}]
    assert find_ollama_model("llama3.1", models) and not find_ollama_model("llama3.1:70b", models)
    assert ollama_digest(models[0]) == "0123456789ab"


def test_missing_api_key_is_a_clear_error(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from redline.core.config import settings

    monkeypatch.setattr(settings, "openai_api_key", None)
    assert run_cli("scan", "openai/gpt-4o-mini", "--judge", "keyword", "--out", tmp_path) == cli.EXIT_ERROR
    assert "needs OPENAI_API_KEY" in capsys.readouterr().err


# ── judge choice ──

def test_default_judge_is_a_local_model_not_under_test(monkeypatch):
    specs = [parse_model("ollama/llama3.1"), parse_model("ollama/hermes3")]
    _tags(monkeypatch, ["llama3.1:latest", "hermes3:latest", "qwen2.5:7b"])
    assert choose_judge(None, specs) == ("ollama/qwen2.5:7b", None)
    _tags(monkeypatch, ["llama3.1:latest", "llama3.1:8b", "hermes3:latest"])
    judge, note = choose_judge(None, specs)  # llama3.1:8b is the model under test: it would grade itself
    assert judge == KEYWORD and "isn't under test" in note
    _tags(monkeypatch, None)
    assert choose_judge(None, specs)[0] == KEYWORD


def test_requested_judges(monkeypatch):
    specs = [parse_model("ollama/llama3.1"), parse_model("ollama/hermes3")]
    assert choose_judge("keyword", specs) == (KEYWORD, None)
    assert choose_judge("groq/openai/gpt-oss-120b", specs) == ("groq/openai/gpt-oss-120b", None)
    _tags(monkeypatch, ["llama3.1:latest"])
    assert "may favour its own answers" in choose_judge("ollama/llama3.1", specs)[1]
    with pytest.raises(ModelError, match="ollama pull qwen2.5:7b"):
        choose_judge("ollama/qwen2.5:7b", specs)
    with pytest.raises(ModelError):
        choose_judge("gpt4", specs)


def test_keyword_grader_warning_is_loud_for_real_models(capsys):
    cli._grader_banner(KEYWORD, "no local Ollama found for a judge", [parse_model("ollama/llama3.1")])
    out = capsys.readouterr().out
    assert "KEYWORD RULES — LESS RELIABLE" in out and "ollama pull qwen2.5:7b" in out
    cli._grader_banner("groq/openai/gpt-oss-120b", None, [parse_model("ollama/llama3.1")])
    assert "Free tiers may keep your prompts. Use for demos only, not private data." in capsys.readouterr().out
    cli._grader_banner("ollama/qwen2.5:7b", None, [parse_model("ollama/llama3.1")])
    assert "Free tiers" not in capsys.readouterr().out


def test_ollama_judge_uses_json_mode_and_the_openai_compatible_endpoint(monkeypatch):
    from redline.core.config import settings
    from redline.llm import judge

    monkeypatch.setattr(settings, "judge_model", "ollama/qwen2.5:7b")
    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:11434/")
    assert judge.is_ollama_judge() and judge.judge_model_id() == "openai/qwen2.5:7b"
    assert judge.judge_credentials() == {"api_base": "http://127.0.0.1:11434/v1", "api_key": "ollama"}
    assert judge._get_client().mode.name == "JSON"
    monkeypatch.setattr(settings, "judge_model", "groq/openai/gpt-oss-120b")
    assert judge._get_client().mode.name == "TOOLS" and judge.judge_model_id() == "openai/openai/gpt-oss-120b"


def test_bound_provider_sends_the_real_model_name():
    seen = {}

    class Inner:
        async def complete(self, messages, model, temperature, seed):
            seen["model"] = model
            return "ok"

    import asyncio

    asyncio.run(BoundProvider(Inner(), "hermes3").complete([], model="ollama/hermes3", temperature=0.2, seed=1))
    assert seen["model"] == "hermes3"


# ── packaging: the CLI must not need the server ──

def test_cli_never_imports_the_server_stack(tmp_path):
    code = (
        "import sys\n"
        "from redline.cli import main\n"
        f"rc = main(['compare', 'fake-safe', 'fake-degraded', '--cases', '30', '--out', {str(tmp_path)!r}])\n"
        "server = sorted(m for m in ('fastapi', 'starlette', 'uvicorn', 'arq', 'redis', 'alembic', 'boto3', 'psycopg') if m in sys.modules)\n"
        "print('SERVER_MODULES', server)\n"
        "sys.exit(rc)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=300,
                         env={**__import__("os").environ, "PYTHONPATH": str(BACKEND)})
    assert out.returncode == cli.EXIT_FAIL, out.stderr[-2000:]
    assert "SERVER_MODULES []" in out.stdout


# ── a real `compare ollama/… ollama/…` against a stand-in Ollama server ──

@pytest.fixture
def mock_ollama(monkeypatch):
    """Serves /api/tags and /v1/chat/completions like Ollama: the models refuse everything,
    the judge (asked for JSON) returns a verdict."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, payload: dict) -> None:
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send({"models": [{"name": n, "model": n, "digest": "sha256:" + d * 32}
                                   for n, d in (("llama3.1:latest", "a1"), ("hermes3:latest", "b2"), ("qwen2.5:7b", "c3"))]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(body)
            if body.get("response_format"):  # the judge
                content = json.dumps({"refusal": True, "refusal_reasoning": "declined", "hallucination_detected": False,
                                      "hallucination_reasoning": "none", "specific": False, "convincing": False})
            else:
                content = "I can't help with that."
            self._send({"id": "c", "object": "chat.completion", "created": 1, "model": body["model"],
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OLLAMA_HOST", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    yield seen
    server.shutdown()


def test_compare_two_ollama_models_with_the_auto_picked_local_judge(tmp_path, mock_ollama, capsys):
    code = run_cli("compare", "ollama/llama3.1", "ollama/hermes3", "--cases", 10, "--out", tmp_path)
    out = capsys.readouterr().out
    assert code in (cli.EXIT_PASS, cli.EXIT_FAIL)
    assert "Grader: ollama/qwen2.5:7b" in out and "Grader: ollama/qwen2.5:7b (AI grader)" in out
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    info = summary["candidate"]["run_info"]
    assert info["judge"] == "ollama/qwen2.5:7b" and info["provider"] == "ollama"
    assert info["model_fingerprint"] == "b2" * 6
    models = {b["model"] for b in mock_ollama}
    assert models == {"llama3.1", "hermes3", "qwen2.5:7b"}  # real names reach Ollama; the judge was really called
    assert summary["case_set"]["identical"] is True and len(_rows(tmp_path)) == 20
