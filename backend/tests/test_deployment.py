"""Deployment-mode defaults, SSRF allowlist for self-hosted installs, and `make init`."""
import importlib.util
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import validate_agent_url

HEADERS = {"X-Admin-Key": "test-key-0123456789abcdef"}
ROOT = Path(__file__).resolve().parents[2]


# ── REDLINE_ENV → eval auth ───────────────────────────────────────────────────

@pytest.mark.parametrize("env,expected", [("production", True), ("development", True), ("demo", False)])
def test_eval_auth_derived_from_env(monkeypatch, env, expected):
    monkeypatch.setattr(settings, "redline_env", env)
    monkeypatch.setattr(settings, "require_eval_auth_override", None)
    assert settings.require_eval_auth is expected


def test_eval_auth_explicit_override_wins(monkeypatch):
    monkeypatch.setattr(settings, "redline_env", "production")
    monkeypatch.setattr(settings, "require_eval_auth_override", False)
    assert settings.require_eval_auth is False


def test_production_quick_eval_requires_key(client, monkeypatch):
    monkeypatch.setattr(settings, "redline_env", "production")
    monkeypatch.setattr(settings, "require_eval_auth_override", None)
    assert client.post("/quick-eval", json={"testcase_count": 2}).status_code == 401
    assert client.post("/quick-eval", json={"testcase_count": 2}, headers=HEADERS).status_code == 200


def test_demo_quick_eval_is_open(client, monkeypatch):
    monkeypatch.setattr(settings, "redline_env", "demo")
    monkeypatch.setattr(settings, "require_eval_auth_override", None)
    assert client.post("/quick-eval", json={"testcase_count": 2}).status_code == 200


def test_health_reports_deployment(client, monkeypatch):
    monkeypatch.setattr(settings, "redline_env", "demo")
    monkeypatch.setattr(settings, "require_eval_auth_override", None)
    body = client.get("/health").json()
    assert body["deployment"] == "demo"
    assert body["eval_auth_required"] is False


def test_default_env_is_production():
    assert type(settings).model_fields["redline_env"].default == "production"


# ── SSRF allowlist ────────────────────────────────────────────────────────────

def test_private_ip_blocked_by_default(monkeypatch):
    monkeypatch.setattr(settings, "agent_endpoint_allowlist", "")
    with pytest.raises(HTTPException):
        validate_agent_url("http://10.20.1.5:8000/v1")


def test_allowlisted_cidr_permits_private_ip(monkeypatch):
    monkeypatch.setattr(settings, "agent_endpoint_allowlist", "10.20.0.0/16")
    assert validate_agent_url("http://10.20.1.5:8000/v1") == "http://10.20.1.5:8000/v1"
    with pytest.raises(HTTPException):
        validate_agent_url("http://10.30.1.5:8000/v1")  # outside the allowed range


def test_allowlisted_hostname_permits_internal_host(monkeypatch):
    monkeypatch.setattr(settings, "agent_endpoint_allowlist", "localhost")
    assert validate_agent_url("http://localhost:11434/v1")


def test_metadata_always_blocked_even_if_allowlisted(monkeypatch):
    monkeypatch.setattr(settings, "agent_endpoint_allowlist", "169.254.0.0/16,169.254.169.254,metadata.google.internal")
    for url in ("http://169.254.169.254/latest", "http://metadata.google.internal/"):
        with pytest.raises(HTTPException):
            validate_agent_url(url)


# ── make init ─────────────────────────────────────────────────────────────────

def _load_init_env():
    spec = importlib.util.spec_from_file_location("init_env", ROOT / "scripts" / "init_env.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_init_env_generates_valid_secrets(tmp_path):
    mod = _load_init_env()
    out = tmp_path / ".env"
    assert mod.main(["--output", str(out), "--template", str(ROOT / ".env.example")]) == 0
    env = dict(
        line.split("=", 1) for line in out.read_text().splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
    )
    assert len(env["ADMIN_API_KEY"]) == 64
    assert env["REDLINE_ENV"] == "production"
    Fernet(env["FIELD_ENCRYPTION_KEY"].encode())  # raises if not a valid Fernet key
    assert "change-me" not in out.read_text().split("ADMIN_API_KEY=")[1].splitlines()[0]


def test_init_env_refuses_to_overwrite(tmp_path):
    mod = _load_init_env()
    out = tmp_path / ".env"
    out.write_text("KEEP=me\n")
    assert mod.main(["--output", str(out), "--template", str(ROOT / ".env.example")]) == 1
    assert out.read_text() == "KEEP=me\n"
