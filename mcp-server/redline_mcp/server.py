"""Redline MCP server — run safety evals on LLM agents from Claude Code."""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

REDLINE_URL = os.environ.get("REDLINE_URL", "http://localhost:8001").rstrip("/")
REDLINE_API_KEY = os.environ.get("REDLINE_API_KEY", "")

mcp = FastMCP(
    "Redline Safety Evals",
    instructions=(
        "Run adversarial safety evaluations against LLM agents. "
        "Use quick_safety_eval for a one-shot full report. "
        "Use run_eval + get_results for more control. "
        "Use compare_runs to diff two runs after a change."
    ),
)


def _headers() -> dict[str, str]:
    return {"X-Admin-Key": REDLINE_API_KEY, "Content-Type": "application/json"}


def _tier_emoji(tier: str) -> str:
    return {"Hardened": "💎", "Safe": "✅", "Developing": "🟡", "At Risk": "🔴"}.get(tier, "❓")


async def _poll_run(client: httpx.AsyncClient, run_id: str, timeout_s: int = 300) -> dict[str, Any]:
    """Poll GET /quick-eval/{run_id} until done or timeout."""
    for _ in range(timeout_s):
        resp = await client.get(f"{REDLINE_URL}/quick-eval/{run_id}", headers=_headers())
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") in ("completed", "failed"):
            return data
        await asyncio.sleep(1)
    raise TimeoutError(f"Run {run_id} did not finish within {timeout_s}s")


def _format_report(data: dict[str, Any]) -> str:
    """Format a completed quick-eval response as a readable safety report."""
    summary = data.get("summary") or {}
    pass_rate = summary.get("pass_rate")
    pct = round((pass_rate or 0) * 100)
    tier = data.get("tier", "Unknown")
    emoji = _tier_emoji(tier)

    lines = [
        f"## Redline Safety Report",
        f"",
        f"**Tier:** {emoji} {tier}   **Pass rate:** {pct}%   **Mode:** {data.get('mode', '?')}   **Model:** {data.get('model', '?')}",
        f"",
    ]

    metrics = summary.get("metrics", {})
    if metrics:
        lines.append("### Metric breakdown")
        metric_labels = {
            "policy_compliance": "Policy compliance (refuses when it should, answers when it should)",
            "hallucination": "Hallucination (avoids unverifiable facts)",
            "must_include": "Must-include (required phrases present)",
            "must_not_include": "Must-not-include (forbidden phrases absent)",
            "strongreject": "StrongREJECT (jailbreak: no specific + convincing harmful content)",
        }
        for key, label in metric_labels.items():
            if key in metrics:
                m = metrics[key]
                mpct = round(m.get("pass_rate", 0) * 100)
                icon = "✅" if mpct >= 75 else ("🟡" if mpct >= 60 else "🔴")
                lines.append(f"- {icon} **{mpct}%** — {label}")
        lines.append("")

    results = data.get("results", [])
    if results:
        failures = [r for r in results if not r.get("passed")]
        lines.append(f"### Failures: {len(failures)}/{len(results)}")
        for r in failures[:5]:
            bad = [k for k, v in (r.get("scores") or {}).items() if v is False]
            lines.append(f"- `{r['testcase_id'][:8]}…` failed: {', '.join(bad) or 'unknown'}")
        if len(failures) > 5:
            lines.append(f"- … and {len(failures) - 5} more")
        lines.append("")

    lines.append(f"Run ID: `{data.get('run_id')}`  Project ID: `{data.get('project_id')}`")
    lines.append(f"Full results: `GET /quick-eval/{data.get('run_id')}`")
    return "\n".join(lines)


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
async def quick_safety_eval(
    testcase_count: int = 10,
    mode: str = "baseline",
    model: str | None = None,
    project_name: str | None = None,
) -> str:
    """Run a full safety evaluation using the configured agent (REDLINE_URL + REDLINE_API_KEY).

    Queues a run, waits for it to complete, and returns a formatted safety report with tier,
    pass rate, and per-metric breakdown. Uses the LLM provider configured on the Redline server.

    Args:
        testcase_count: Number of test cases to run (1-50). More = more thorough but slower.
        mode: 'baseline' (direct) or 'debate' (proposer → critic → revision).
        model: Override the default model. Leave None to use the server default.
        project_name: Optional name for this eval run.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        payload: dict[str, Any] = {
            "testcase_count": testcase_count,
            "mode": mode,
            "seed": 7,
        }
        if model:
            payload["model"] = model
        if project_name:
            payload["name"] = project_name

        resp = await client.post(f"{REDLINE_URL}/quick-eval", json=payload, headers=_headers())
        if resp.status_code != 200:
            return f"Error starting eval: {resp.status_code} {resp.text}"
        queued = resp.json()
        run_id = queued["run_id"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            data = await _poll_run(client, run_id, timeout_s=300)
    except TimeoutError as e:
        return str(e)

    if data.get("status") == "failed":
        return f"Eval failed. Run ID: {run_id}\nSummary: {data.get('summary')}"

    return _format_report(data)


@mcp.tool()
async def list_projects() -> str:
    """List all projects on this Redline instance."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{REDLINE_URL}/projects", headers=_headers())
        if resp.status_code != 200:
            return f"Error: {resp.status_code} {resp.text}"
        projects = resp.json()

    if not projects:
        return "No projects found. Run quick_safety_eval to create one."

    lines = ["## Projects", ""]
    for p in projects:
        lines.append(f"- **{p['name']}** — ID: `{p['id']}` created {p.get('created_at', '')[:10]}")
    return "\n".join(lines)


@mcp.tool()
async def get_run_results(project_id: str, run_id: str) -> str:
    """Get the full results for a specific run.

    Args:
        project_id: Project ID (from list_projects or quick_safety_eval output).
        run_id: Run ID.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        run_resp = await client.get(
            f"{REDLINE_URL}/projects/{project_id}/runs/{run_id}",
            headers=_headers(),
        )
        if run_resp.status_code != 200:
            return f"Error fetching run: {run_resp.status_code} {run_resp.text}"
        run = run_resp.json()

        if run["status"] != "completed":
            return f"Run is not completed yet. Status: {run['status']}"

        results_resp = await client.get(
            f"{REDLINE_URL}/projects/{project_id}/runs/{run_id}/results",
            headers=_headers(),
        )
        if results_resp.status_code != 200:
            return f"Error fetching results: {results_resp.status_code} {results_resp.text}"
        results = results_resp.json()

    summary = run.get("summary") or {}
    pass_rate = summary.get("pass_rate")
    pct = round((pass_rate or 0) * 100)

    lines = [f"## Run Results — {pct}% passed", ""]
    failures = [r for r in results if not r.get("passed")]
    lines.append(f"**{len(results) - len(failures)}/{len(results)} passed** | {len(failures)} failures")
    lines.append("")

    if failures:
        lines.append("### Failed test cases")
        for r in failures:
            bad = [k for k, v in (r.get("scores") or {}).items() if v is False]
            lines.append(f"- `{r['testcase_id'][:8]}…` failed metrics: {', '.join(bad)}")
            if r.get("raw_output"):
                lines.append(f"  > {r['raw_output'][:120]}…")

    return "\n".join(lines)


@mcp.tool()
async def compare_runs(project_id: str, base_run_id: str, candidate_run_id: str) -> str:
    """Compare two runs to see if a change improved or regressed safety.

    Args:
        project_id: Project ID.
        base_run_id: The baseline run (before your change).
        candidate_run_id: The candidate run (after your change).
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{REDLINE_URL}/projects/{project_id}/runs/compare",
            params={"base_run_id": base_run_id, "candidate_run_id": candidate_run_id},
            headers=_headers(),
        )
        if resp.status_code != 200:
            return f"Error: {resp.status_code} {resp.text}"
        data = resp.json()

    delta = data.get("pass_rate_delta")
    base_pct = round((data.get("base_pass_rate") or 0) * 100)
    cand_pct = round((data.get("candidate_pass_rate") or 0) * 100)

    if delta is None:
        direction = "no overlap"
    elif delta > 0.01:
        direction = f"🟢 improved +{round(delta * 100)}pp"
    elif delta < -0.01:
        direction = f"🔴 regressed {round(delta * 100)}pp"
    else:
        direction = "➡️ no change"

    lines = [
        f"## Run Comparison — {direction}",
        f"",
        f"| | Pass rate |",
        f"|---|---|",
        f"| Baseline | {base_pct}% |",
        f"| Candidate | {cand_pct}% |",
        f"",
        "### Metric deltas",
    ]

    for metric, m in (data.get("metrics") or {}).items():
        d = m.get("delta")
        if d is None:
            continue
        icon = "🟢" if d > 0.01 else ("🔴" if d < -0.01 else "➡️")
        lines.append(f"- {icon} **{metric}**: {round(m.get('base_pass_rate', 0) * 100)}% → {round(m.get('candidate_pass_rate', 0) * 100)}%")

    changed = data.get("changed_testcases", [])
    if changed:
        lines.append(f"")
        lines.append(f"### {len(changed)} test cases changed outcome")
        for tc in changed[:5]:
            arrow = "❌→✅" if tc["candidate_passed"] else "✅→❌"
            lines.append(f"- `{tc['testcase_id'][:8]}…` {arrow}")

    return "\n".join(lines)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
