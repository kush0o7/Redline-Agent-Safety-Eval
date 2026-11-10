"""Redline version string for reports: package version plus git commit when available."""
from __future__ import annotations

import subprocess
from functools import lru_cache
from importlib import metadata
from pathlib import Path


@lru_cache(maxsize=1)
def redline_version() -> str:
    try:
        version = metadata.version("redline-backend")
    except metadata.PackageNotFoundError:
        version = "0.1.0"
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent, capture_output=True, text=True, timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        sha = ""
    return f"{version}+{sha}" if sha else version
