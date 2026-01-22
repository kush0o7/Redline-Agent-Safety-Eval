from __future__ import annotations

from collections import defaultdict


def aggregate_metrics(results: list[dict]) -> dict:
    summary = {"total": len(results), "passed": 0, "pass_rate": 0.0, "metrics": {}}
    if not results:
        return summary

    metric_totals = defaultdict(int)
    metric_pass = defaultdict(int)

    for result in results:
        if result.get("passed"):
            summary["passed"] += 1
        for metric, value in result.get("scores", {}).items():
            if value is None:
                continue
            metric_totals[metric] += 1
            if value:
                metric_pass[metric] += 1

    summary["pass_rate"] = summary["passed"] / max(summary["total"], 1)
    for metric, total in metric_totals.items():
        summary["metrics"][metric] = {
            "pass": metric_pass[metric],
            "total": total,
            "pass_rate": metric_pass[metric] / max(total, 1),
        }
    return summary
