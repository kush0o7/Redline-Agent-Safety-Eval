"""The Docker image installs requirements.txt; it must match pyproject.toml's dependencies."""
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _requirements() -> list[str]:
    lines = (BACKEND / "requirements.txt").read_text().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def test_requirements_txt_matches_pyproject_dependencies():
    deps = tomllib.loads((BACKEND / "pyproject.toml").read_text())["project"]["dependencies"]
    assert sorted(_requirements()) == sorted(deps)


def test_docker_image_has_encryption_and_no_jailbreakbench():
    reqs = " ".join(_requirements())
    assert "cryptography" in reqs  # FIELD_ENCRYPTION_KEY (make init always sets one)
    assert "jailbreakbench" not in reqs  # data is bundled; the package needs Python < 3.12


def test_dockerfile_copies_what_the_app_needs():
    dockerfile = (BACKEND / "Dockerfile").read_text()
    for needle in ("backend/requirements.txt", "backend/app", "backend/start.sh", "COPY ui"):
        assert needle in dockerfile, needle
    assert (BACKEND / "app" / "evals" / "data" / "jbb_behaviors.json").exists()  # shipped inside backend/app
