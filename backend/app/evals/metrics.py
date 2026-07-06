from __future__ import annotations

import math
from collections import defaultdict


def wilson_ci(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion."""
    if total == 0:
        return 0.0, 1.0
    p = passed / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    margin = (z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def aggregate_metrics(results: list[dict]) -> dict:
    summary: dict = {"total": len(results), "passed": 0, "pass_rate": 0.0, "metrics": {}, "categories": {}}
    if not results:
        return summary

    metric_totals: dict[str, int] = defaultdict(int)
    metric_pass: dict[str, int] = defaultdict(int)
    category_totals: dict[str, int] = defaultdict(int)
    category_pass: dict[str, int] = defaultdict(int)

    for result in results:
        passed = bool(result.get("passed"))
        if passed:
            summary["passed"] += 1

        cat = result.get("type", "unknown")
        category_totals[cat] += 1
        if passed:
            category_pass[cat] += 1

        for metric, value in result.get("scores", {}).items():
            if value is None:
                continue
            metric_totals[metric] += 1
            if value:
                metric_pass[metric] += 1

    n = summary["total"]
    p = summary["passed"]
    summary["pass_rate"] = p / max(n, 1)
    lo, hi = wilson_ci(p, n)
    summary["confidence_interval"] = {"low": round(lo, 3), "high": round(hi, 3), "n": n}
    summary["sample_size_warning"] = n < 30

    for metric, total in metric_totals.items():
        mp = metric_pass[metric]
        mlo, mhi = wilson_ci(mp, total)
        summary["metrics"][metric] = {
            "pass": mp,
            "total": total,
            "pass_rate": mp / max(total, 1),
            "ci_low": round(mlo, 3),
            "ci_high": round(mhi, 3),
        }

    for cat, total in category_totals.items():
        cp = category_pass[cat]
        clo, chi = wilson_ci(cp, total)
        summary["categories"][cat] = {
            "pass": cp,
            "total": total,
            "pass_rate": round(cp / max(total, 1), 3),
            "ci_low": round(clo, 3),
            "ci_high": round(chi, 3),
        }

    return summary
