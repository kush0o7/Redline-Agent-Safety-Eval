"""Redline version string for reports: package version plus git commit when available."""
from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from importlib import metadata
from pathlib import Path


FALLBACK_VERSION = "0.2.0"  # keep equal to pyproject.toml (tests/test_packaging.py checks)


@lru_cache(maxsize=1)
def redline_version() -> str:
    version = FALLBACK_VERSION
    for dist in ("redline-evals", "redline-backend"):  # redline-backend: the old name
        try:
            version = metadata.version(dist)
            break
        except metadata.PackageNotFoundError:
            continue
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent, capture_output=True, text=True, timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        sha = ""
    # Code unpacked without .git (the Kaggle notebook) passes its commit in the environment.
    sha = sha or os.environ.get("REDLINE_COMMIT", "").strip()
    return f"{version}+{sha}" if sha else version
