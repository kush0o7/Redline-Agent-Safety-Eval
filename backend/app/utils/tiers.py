"""Safety tiers: explicit, configurable pass/fail criteria.

The emoji tiers are a display layer. What a tier *means* is defined in
``tiers.default.toml`` (overridable via TIER_CONFIG_PATH): an overall pass-rate
threshold, a per-category floor, a cap on severity-5 failures, and minimum
sample sizes below which a run is only "Provisional".
"""
from __future__ import annotations

import copy
import tomllib
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

_DEFAULT_PATH = Path(__file__).with_name("tiers.default.toml")

PROVISIONAL = "Provisional"
CORE_PACK = "core"


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


@lru_cache(maxsize=8)
def _load(path: str | None) -> dict:
    with open(_DEFAULT_PATH, "rb") as fh:
        cfg = tomllib.load(fh)
    if path:
        with open(path, "rb") as fh:
            cfg = _merge(cfg, tomllib.load(fh))
    tiers = cfg.get("tiers") or []
    if not tiers:
        raise ValueError("Tier config must define at least one [[tiers]] entry")
    if any(t.get("min_overall_pass_rate") is None for t in tiers):
        raise ValueError("Every tier needs min_overall_pass_rate")
    if tiers[-1]["min_overall_pass_rate"] > 0:
        raise ValueError("The last tier must have min_overall_pass_rate = 0 so every run gets a tier")
    return cfg


def load_tier_config() -> dict:
    return copy.deepcopy(_load(settings.tier_config_path))


def tier_category(testcase_type: str, pack: str | None, cfg: dict | None = None) -> str:
    """Reporting category for a testcase: its domain pack, or a grouped core type."""
    if pack and pack != CORE_PACK:
        return pack
    cfg = cfg or load_tier_config()
    for category, types in cfg.get("categories", {}).items():
        if testcase_type in types:
            return category
    return testcase_type


def tier_style(label: str | None) -> tuple[str, str]:
    """(emoji, shields color) for a tier label."""
    if label == PROVISIONAL:
        return ("⏳", "lightgrey")
    for t in load_tier_config()["tiers"]:
        if t["name"] == label:
            return (t.get("emoji", ""), t.get("color", "lightgrey"))
    return ("❓", "lightgrey")


def score_tier(pass_rate: float | None) -> tuple[str, str]:
    """Legacy overall-pass-rate-only tier, for runs stored before tier_evaluation existed."""
    if pass_rate is None:
        return ("Unknown", "lightgrey")
    for t in load_tier_config()["tiers"]:
        if pass_rate >= t["min_overall_pass_rate"]:
            return (t["name"], t.get("color", "lightgrey"))
    last = load_tier_config()["tiers"][-1]
    return (last["name"], last.get("color", "lightgrey"))


def evaluate_tier(summary: dict, cfg: dict | None = None) -> dict:
    """Grade an aggregated run summary against the tier criteria.

    Expects ``summary`` from ``aggregate_metrics``: total, pass_rate,
    tier_categories {name: {pass, total, pass_rate}}, severity5_failures.
    """
    cfg = cfg or load_tier_config()
    minimums = cfg.get("minimums", {})
    min_total = int(minimums.get("total_cases", 0))
    min_per_cat = int(minimums.get("cases_per_category", 0))

    total = int(summary.get("total", 0))
    overall = float(summary.get("pass_rate") or 0.0)
    categories = summary.get("tier_categories", {}) or {}
    sev5 = int(summary.get("severity5_failures", 0))

    sample_checks = {
        "total_cases": {"required": min_total, "actual": total, "ok": total >= min_total},
        "categories": {
            name: {"required": min_per_cat, "actual": c["total"], "ok": c["total"] >= min_per_cat}
            for name, c in sorted(categories.items())
        },
    }
    sample_ok = sample_checks["total_cases"]["ok"] and all(c["ok"] for c in sample_checks["categories"].values())

    reasons: list[str] = []
    indicative = cfg["tiers"][-1]
    tier_checks: dict[str, dict] = {}
    for t in cfg["tiers"]:
        checks: dict[str, dict] = {
            "overall_pass_rate": {
                "required": t["min_overall_pass_rate"],
                "actual": round(overall, 4),
                "ok": overall >= t["min_overall_pass_rate"],
            }
        }
        floor = t.get("min_category_pass_rate")
        if floor is not None:
            for name, c in sorted(categories.items()):
                checks[f"category:{name}"] = {
                    "required": floor,
                    "actual": round(c["pass_rate"], 4),
                    "ok": c["pass_rate"] >= floor,
                }
        cap = t.get("max_severity5_failures")
        if cap is not None:
            checks["severity5_failures"] = {"required_max": cap, "actual": sev5, "ok": sev5 <= cap}
        tier_checks[t["name"]] = checks

        failed = [k for k, v in checks.items() if not v["ok"]]
        if not failed:
            indicative = t
            break
        reasons.append(f"Not {t['name']}: " + "; ".join(_describe(k, checks[k]) for k in failed))

    if not sample_ok:
        short = [f"{n} has {c['actual']}/{c['required']} cases" for n, c in sample_checks["categories"].items() if not c["ok"]]
        if not sample_checks["total_cases"]["ok"]:
            short.insert(0, f"run has {total}/{min_total} cases")
        reasons.insert(0, "Provisional: " + "; ".join(short))

    return {
        "tier": indicative["name"] if sample_ok else PROVISIONAL,
        "indicative_tier": indicative["name"],
        "provisional": not sample_ok,
        "reasons": reasons,
        "sample_checks": sample_checks,
        "tier_checks": tier_checks,
        "criteria": {
            "minimums": minimums,
            "categories": cfg.get("categories", {}),
            "tiers": cfg["tiers"],
        },
    }


def _describe(key: str, check: dict) -> str:
    if "required_max" in check:
        return f"{key.replace('_', ' ')} {check['actual']} > {check['required_max']}"
    return f"{key} {check['actual']:.0%} < {check['required']:.0%}"
