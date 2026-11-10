"""Self-contained HTML evidence report for a run or a comparison of two runs.

No external assets, no scripts: everything (including model answers, which may
contain attacker-controlled text such as markdown images) is HTML-escaped, so the
file renders identically offline and can't phone home. Print to PDF from a
browser if a PDF is needed (native PDF export is a later, paid-tier feature).
"""
from __future__ import annotations

import html
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import Run, RunResult, Testcase
from app.evals.comparison import build_comparison, run_brief
from app.version import redline_version

DECIDED_BY_LABELS = {
    "code": "code check (agent actions)",
    "judge": "LLM judge",
    "heuristic": "keyword heuristic (offline/test mode)",
}
MAX_ANSWER_CHARS = 4000

_CSS = """
:root{--fg:#111827;--muted:#6b7280;--line:#e5e7eb;--bg:#ffffff;--card:#f9fafb;--bad:#b91c1c;--good:#15803d;--warn:#a16207}
@media (prefers-color-scheme: dark){:root{--fg:#e5e7eb;--muted:#9ca3af;--line:#374151;--bg:#111827;--card:#1f2937;--bad:#f87171;--good:#4ade80;--warn:#facc15}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1000px;margin:0 auto;padding:32px 16px 64px}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:32px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
h3{font-size:15px;margin:0 0 6px}.muted{color:var(--muted)}.meta{font-size:13px;color:var(--muted)}code{font-size:12.5px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}.big{font-size:26px;font-weight:700}
.bad{color:var(--bad)}.good{color:var(--good)}.warn{color:var(--warn)}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:12.5px;text-transform:uppercase;letter-spacing:.03em}td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.case{border:1px solid var(--line);border-radius:10px;padding:14px;margin:12px 0;background:var(--card)}
.tag{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:999px;padding:1px 8px;margin-right:6px}
pre{white-space:pre-wrap;word-break:break-word;margin:4px 0 10px;padding:10px;border-radius:8px;border:1px solid var(--line);background:var(--bg);font-size:13px;max-height:320px;overflow:auto}
ul{margin:6px 0 0 18px;padding:0}.table-wrap{overflow-x:auto}
@media print{pre{max-height:none}}
"""


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _pct(v) -> str:
    return "—" if v is None else f"{v * 100:.0f}%"


def _ci(group: dict | None) -> str:
    if not group:
        return "—"
    lo, hi = group.get("ci_low"), group.get("ci_high")
    rate = _pct(group.get("pass_rate"))
    n = f"{group.get('pass', '?')}/{group.get('total', '?')}"
    return f"{rate} <span class='muted'>({n}; 95% CI {_pct(lo)}–{_pct(hi)})</span>" if lo is not None else f"{rate} ({n})"


def _delta(d) -> str:
    if d is None:
        return "—"
    pts = d * 100
    cls = "bad" if pts < -0.5 else "good" if pts > 0.5 else "muted"
    return f"<span class='{cls}'>{pts:+.0f} pts</span>"


def _answer(text) -> str:
    text = "" if text is None else str(text)
    if len(text) > MAX_ANSWER_CHARS:
        text = text[:MAX_ANSWER_CHARS] + f"\n… [truncated, {len(text)} chars total]"
    return f"<pre>{_e(text)}</pre>"


def _tier_label(brief: dict) -> str:
    if brief.get("provisional"):
        return f"Provisional <span class='muted'>(indicative: {_e(brief.get('indicative_tier'))})</span>"
    return _e(brief.get("tier") or "—")


def _decided(label) -> str:
    return _e(DECIDED_BY_LABELS.get(label, label or "—"))


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{_e(title)}</title><style>{_CSS}</style></head><body><main>{body}</main></body></html>")


def _header(kind: str, briefs: list[dict], now: str) -> str:
    fps = " · ".join(f"<code>{_e((b.get('case_set_hash') or 'n/a')[:16])}</code>" for b in briefs)
    runs = " · ".join(f"<code>{_e(b['run_id'])}</code>" for b in briefs)
    return (f"<h1>Redline {kind}</h1>"
            f"<div class='meta'>Generated {_e(now)} · Redline {_e(redline_version())}<br>"
            f"Run(s): {runs}<br>Case-set fingerprint(s): {fps}</div>")


def _group_table(title: str, groups: dict) -> str:
    if not groups:
        return ""
    rows = "".join(f"<tr><td>{_e(n)}</td><td class='num'>{_ci(g)}</td></tr>" for n, g in sorted(groups.items()))
    return (f"<h2>{_e(title)}</h2><div class='table-wrap'><table><thead><tr><th>Name</th>"
            f"<th>Pass rate</th></tr></thead><tbody>{rows}</tbody></table></div>")


def _delta_table(title: str, groups: dict) -> str:
    if not groups:
        return ""
    rows = "".join(
        f"<tr><td>{_e(n)}</td><td class='num'>{_ci(g['base'])}</td><td class='num'>{_ci(g['candidate'])}</td>"
        f"<td class='num'>{_delta(g['delta'])}</td></tr>"
        for n, g in groups.items()
    )
    return (f"<h2>{_e(title)}</h2><div class='table-wrap'><table><thead><tr><th>Name</th><th>Before</th>"
            f"<th>After</th><th>Change</th></tr></thead><tbody>{rows}</tbody></table></div>")


def _decided_by_line(counts: dict) -> str:
    if not counts:
        return ""
    parts = ", ".join(f"{_decided(k)}: {v}" for k, v in sorted(counts.items()))
    return f"<p class='meta'>How results were decided — {parts}</p>"


def _methodology(briefs: list[dict]) -> str:
    simulated = any(str(b.get("model") or "").startswith("fake") for b in briefs)
    n = min((b.get("total") or 0) for b in briefs) if briefs else 0
    sim = ("<li><strong>Simulated models.</strong> This report uses Redline's built-in fake models "
           "(<code>fake-safe</code> / <code>fake-degraded</code>), which look test cases up and answer the way a "
           "safe or a safety-regressed model would. It demonstrates the pipeline and report, not a real model's safety.</li>"
           if simulated else "")
    return f"""<h2>Methodology notes</h2><ul>
<li><strong>Code vs judge grading.</strong> Prompt-injection cases are graded in code on what the agent <em>did</em>: a tool call with the attacker's arguments, or the attacker's marker in the output (<code>decided_by = code</code>). Other cases are graded by an LLM judge (refusal, hallucination, and whether harmful content was specific and convincing — StrongREJECT), or by a keyword heuristic in offline/test mode. Every result records which method decided it.</li>
<li><strong>Sample sizes.</strong> Pass rates carry 95% Wilson confidence ranges. This report covers {n} cases per run. A run with fewer than 30 cases, or fewer than 5 in any category, is <em>Provisional</em>: its tier is indicative only. Small per-category samples have wide ranges; treat single-category changes inside overlapping ranges with caution.</li>
<li><strong>Like-for-like.</strong> Comparisons are only meaningful on identical case sets (same fingerprint, via <code>rerun_of</code>); a warning is shown otherwise.</li>
<li><strong>Known limitations.</strong> The LLM judge's accuracy has not yet been measured against human labels. Injection scenarios are single-task with stub tools: they show what the agent attempted, not real-world effects. Every request currently uses Redline's short default system prompt, which can make an agent look safer than in production. Multi-turn attacks are not yet covered.</li>
{sim}</ul>"""


def _case_block(d: dict) -> str:
    tags = "".join(f"<span class='tag'>{_e(t)}</span>" for t in (d.get("type"), d.get("pack"), f"severity {d.get('severity')}") if t)
    failed = ", ".join(d.get("candidate_failed_metrics") or []) or "—"
    evidence = "".join(f"<li>{_e(x)}</li>" for x in (d.get("evidence") or []))
    goal = f"<p><strong>Attacker's goal:</strong> {_e(d['attack_goal'])}</p>" if d.get("attack_goal") else ""
    return (f"<div class='case'><h3>{_e(d.get('name'))}</h3><div>{tags}</div>{goal}"
            f"<p class='muted'>Prompt</p>{_answer(d.get('prompt'))}"
            f"<p class='muted'>Before — {'passed' if d['base_passed'] else 'failed'} · decided by {_decided(d.get('base_decided_by'))}</p>{_answer(d.get('base_answer'))}"
            f"<p class='muted'>After — {'passed' if d['candidate_passed'] else 'failed'} · decided by {_decided(d.get('candidate_decided_by'))} · failed: {_e(failed)}</p>{_answer(d.get('candidate_answer'))}"
            f"{'<p class=muted>Evidence</p><ul>' + evidence + '</ul>' if evidence else ''}</div>")


def render_comparison_report(db: Session, base_run: Run, candidate_run: Run, *, now: str | None = None) -> str:
    cmp = build_comparison(db, base_run, candidate_run)
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    b, c, tc = cmp["base"], cmp["candidate"], cmp["tier_change"]
    tier_cls = "bad" if tc["direction"] == "down" else "good" if tc["direction"] == "up" else "muted"
    warn = ""
    if not cmp["case_set"].get("identical", False):
        warn = f"<p class='warn'><strong>Warning:</strong> {_e(cmp['case_set'].get('warning') or 'runs did not use identical cases')}</p>"
    regs, imps = cmp["flipped"]["regressions"], cmp["flipped"]["improvements"]
    reasons = "".join(f"<li>{_e(r)}</li>" for r in c.get("reasons") or [])
    body = _header("comparison report", [b, c], now) + warn + f"""
<div class='cards'>
<div class='card'><div class='muted'>Before · {_e(b['model'])}</div><div class='big'>{_pct(b.get('pass_rate'))}</div><div>{_tier_label(b)}</div></div>
<div class='card'><div class='muted'>After · {_e(c['model'])}</div><div class='big'>{_pct(c.get('pass_rate'))}</div><div>{_tier_label(c)}</div></div>
<div class='card'><div class='muted'>Overall change</div><div class='big'>{_delta(cmp.get('pass_rate_delta'))}</div><div class='{tier_cls}'>Tier {_e(tc['from'])} → {_e(tc['to'])}</div></div>
<div class='card'><div class='muted'>Flipped cases</div><div class='big'><span class='bad'>{len(regs)}</span> / <span class='good'>{len(imps)}</span></div><div class='muted'>pass→fail / fail→pass of {cmp['common_total']} shared</div></div>
</div>
<h2>Summary</h2>
<p>On the same {cmp['common_total']} cases, the pass rate moved from <strong>{_pct(cmp.get('base_pass_rate'))}</strong> to <strong>{_pct(cmp.get('candidate_pass_rate'))}</strong> ({_delta(cmp.get('pass_rate_delta'))}); the tier moved from <strong>{_e(tc['from'])}</strong> to <strong>{_e(tc['to'])}</strong>. {len(regs)} case(s) regressed and {len(imps)} improved.</p>
{f"<p class='muted'>Why the after-run got its tier:</p><ul>{reasons}</ul>" if reasons else ""}
{_decided_by_line(c.get('decided_by') or {})}
{_delta_table("Per category", cmp['categories'])}
{_delta_table("Per pack", cmp['packs'])}
<h2>Regressions (pass → fail)</h2>
{''.join(_case_block(d) for d in regs) or "<p class='muted'>None.</p>"}
<h2>Improvements (fail → pass)</h2>
{''.join(_case_block(d) for d in imps) or "<p class='muted'>None.</p>"}
{_methodology([b, c])}"""
    return _page(f"Redline comparison — {b['model']} vs {c['model']}", body)


def render_run_report(db: Session, run: Run, *, now: str | None = None) -> str:
    brief = run_brief(run)
    summary = run.summary if isinstance(run.summary, dict) else {}
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = db.query(RunResult).filter(RunResult.run_id == run.id).all()
    tcs = {str(t.id): t for t in db.query(Testcase).filter(Testcase.id.in_([r.testcase_id for r in rows])).all()} if rows else {}
    failures = []
    for r in rows:
        if r.passed:
            continue
        tc = tcs.get(str(r.testcase_id))
        jr = r.judge_reasoning or {}
        evidence = jr.get("evidence") or [x for x in (jr.get("refusal_reasoning"), jr.get("hallucination_reasoning"), jr.get("reasoning")) if x]
        failures.append((-(tc.severity if tc else 0), tc.name if tc else "", tc, r, jr, evidence))
    failures.sort(key=lambda x: (x[0], x[1]))
    blocks = "".join(
        f"<div class='case'><h3>{_e(tc.name if tc else r.testcase_id)}</h3><div>"
        + "".join(f"<span class='tag'>{_e(t)}</span>" for t in ((tc.type, tc.pack, f'severity {tc.severity}') if tc else ()))
        + f"</div>{'<p><strong>Attacker' + chr(39) + 's goal:</strong> ' + _e(jr['attack_goal']) + '</p>' if jr.get('attack_goal') else ''}"
        f"<p class='muted'>Prompt</p>{_answer(tc.prompt if tc else '')}"
        f"<p class='muted'>Answer · decided by {_decided(jr.get('decided_by'))} · failed: {_e(', '.join(sorted(k for k, v in (r.scores or {}).items() if v is False)) or '—')}</p>{_answer(r.raw_output)}"
        + (f"<p class='muted'>Evidence</p><ul>{''.join(f'<li>{_e(x)}</li>' for x in evidence)}</ul>" if evidence else "")
        + "</div>"
        for _, _, tc, r, jr, evidence in failures
    )
    reasons = "".join(f"<li>{_e(x)}</li>" for x in brief.get("reasons") or [])
    ci = summary.get("confidence_interval") or {}
    body = _header("run report", [brief], now) + f"""
<div class='cards'>
<div class='card'><div class='muted'>Model</div><div class='big' style='font-size:18px'>{_e(brief['model'])}</div><div class='muted'>mode {_e(brief['mode'])} · seed {_e(brief['seed'])}</div></div>
<div class='card'><div class='muted'>Pass rate</div><div class='big'>{_pct(brief.get('pass_rate'))}</div><div class='muted'>{summary.get('passed', '?')}/{summary.get('total', '?')} · 95% CI {_pct(ci.get('low'))}–{_pct(ci.get('high'))}</div></div>
<div class='card'><div class='muted'>Tier</div><div class='big' style='font-size:20px'>{_tier_label(brief)}</div></div>
<div class='card'><div class='muted'>Severity-5 failures</div><div class='big'>{_e(summary.get('severity5_failures', 0))}</div></div>
</div>
<h2>Summary</h2>
<p>Status: {_e(run.status)}. {len(failures)} of {len(rows)} cases failed.</p>
{f"<p class='muted'>Tier reasons:</p><ul>{reasons}</ul>" if reasons else ""}
{_decided_by_line(summary.get('decided_by') or {})}
{_group_table("Per category", summary.get('tier_categories') or {})}
{_group_table("Per pack", summary.get('packs') or {})}
{_group_table("Per test type", summary.get('categories') or {})}
<h2>Failed cases</h2>
{blocks or "<p class='muted'>None.</p>"}
{_methodology([brief])}"""
    return _page(f"Redline run report — {brief['model']}", body)
