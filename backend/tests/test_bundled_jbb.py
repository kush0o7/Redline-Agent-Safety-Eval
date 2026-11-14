"""JailbreakBench behaviors are bundled data: same 20 cases on every machine, no package, no network."""
import json
import sys
import tomllib
from pathlib import Path

from app.evals import testcases
from app.evals.testcases import JBB_DATA, JBB_SEVERITY, build_default_testcases

BACKEND = Path(__file__).resolve().parents[1]


def test_bundled_file_has_licence_source_and_20_behaviors():
    data = json.loads(JBB_DATA.read_text(encoding="utf-8"))
    assert data["license"].startswith("MIT") and "JailbreakBench" in data["dataset"]
    assert len(data["behaviors"]) == 20
    cats = {b["category"] for b in data["behaviors"]}
    assert len(cats) == 10 and cats == set(JBB_SEVERITY)
    assert all(b["goal"].strip() for b in data["behaviors"])


def test_jbb_cases_load_without_the_package_or_network(monkeypatch):
    monkeypatch.setitem(sys.modules, "jailbreakbench", None)  # importing it would now fail
    cases = testcases._load_jailbreakbench_cases()
    assert len(cases) == 20
    assert all(c.type == "jailbreak" and c.expected_behavior["should_refuse"] for c in cases)
    assert all(c.name.startswith("jbb-") and "jailbreakbench" in c.tags for c in cases)
    assert {c.severity for c in cases} == {3, 4, 5}


def test_case_set_is_deterministic_and_counts_match_docs():
    a, b = build_default_testcases(), build_default_testcases()
    assert [(c.name, c.prompt) for c in a] == [(c.name, c.prompt) for c in b]
    core = [c for c in a if c.pack == "core"]
    assert len(a) == 172 and len(core) == 151
    assert len({c.name for c in a}) == len(a)
    # The former fallback cases are always included now.
    assert "jailbreak-malware" in {c.name for c in core}


def test_dependency_removed_and_data_packaged():
    meta = tomllib.loads((BACKEND / "pyproject.toml").read_text())
    assert not any(d.startswith("jailbreakbench") for d in meta["project"]["dependencies"])
    assert "evals/data/*.json" in meta["tool"]["setuptools"]["package-data"]["app"]
