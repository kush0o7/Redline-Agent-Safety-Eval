"""Self-contained HTML evidence report for a run or a comparison of two runs.

No external assets, no scripts: everything (including model answers, which may
contain attacker-controlled text such as markdown images) is HTML-escaped, so the
file renders identically offline and can't phone home. Print to PDF from a
browser if a PDF is needed (native PDF export is a later, paid-tier feature).
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import Run, RunResult, Testcase
from app.evals.comparison import build_comparison, run_brief
from app.evals.redaction import REDACTED, redact_text
from app.evals.release import injection_impact, risk_sentence
from app.utils.tiers import load_tier_config, tier_category
from app.version import redline_version

DECIDED_BY_LABELS = {
    "code": "code check (agent actions)",
    "judge": "LLM judge",
    "heuristic": "keyword heuristic (offline/test mode)",
}
MAX_ANSWER_CHARS = 4000
MAX_INJECTION_ANSWER_CHARS = 600   # an injected agent's final text can echo the whole attacker payload
MAX_ARG_CHARS = 160                # per tool-call argument (e.g. an exfiltrated email body)
MAX_EVIDENCE_CHARS = 300

_CSS = """
:root{--fg:#111827;--muted:#6b7280;--line:#e5e7eb;--bg:#ffffff;--card:#f9fafb;--bad:#b91c1c;--good:#15803d;--warn:#a16207}
@media (prefers-color-scheme: dark){:root{--fg:#e5e7eb;--muted:#9ca3af;--line:#374151;--bg:#111827;--card:#1f2937;--bad:#f87171;--good:#4ade80;--warn:#facc15}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1000px;margin:0 auto;padding:32px 16px 64px;overflow-wrap:break-word}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:32px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}
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
.banner{border-radius:10px;padding:12px 14px;margin:0 0 16px;font-size:15px}
.banner.sim{background:#fef3c7;color:#78350f;border:1px solid #f59e0b}
.banner.danger{background:#fee2e2;color:#7f1d1d;border:1px solid #ef4444}
.exec{border:2px solid var(--line);border-radius:12px;padding:16px 18px;margin:20px 0 4px;background:var(--card)}
.exec.fail{border-color:var(--bad)}.exec.pass{border-color:var(--good)}
.exec .decision{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline}
.exec .verdict{font-size:22px;font-weight:800}.exec.fail .verdict{color:var(--bad)}.exec.pass .verdict{color:var(--good)}
.exec h3{margin:14px 0 4px}.exec ol{margin:4px 0 0 20px;padding:0}.exec .action{margin:12px 0 0}
.flips{font-size:18px;font-weight:700;margin:4px 0}
details.group{border:1px solid var(--line);border-radius:10px;margin:12px 0;padding:6px 12px}
details.group>summary{cursor:pointer;padding:6px 0;font-size:15px}
details.case{border:1px solid var(--line);border-radius:10px;margin:8px 0;background:var(--card)}
details.case>summary{cursor:pointer;padding:10px 12px;list-style-position:outside}
details.case .line{font-size:13.5px;margin:3px 0 0 2px;overflow-wrap:anywhere}
.impact,.exec li{overflow-wrap:anywhere}
details.case .body{padding:0 12px 12px}
.sev{display:inline-block;font-size:11.5px;font-weight:700;border-radius:6px;padding:0 6px;margin-right:4px}
.sev5{background:var(--bad);color:var(--bg)}.sev4{background:var(--warn);color:var(--bg)}.sevn{border:1px solid var(--line)}
.impact{border-left:3px solid var(--bad);padding-left:10px}
pre.redacted{color:var(--muted);font-style:italic}
table.calls td{font-size:13px;word-break:break-word}
@media print{pre{max-height:none}details>summary{list-style:none}}
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




# ── Banners, redaction, case rendering ──

def is_simulated(briefs: list[dict]) -> bool:
    return any(str(b.get("model") or "").startswith("fake") for b in briefs)


def _banners(briefs: list[dict], include_full_outputs: bool) -> str:
    out = ""
    if is_simulated(briefs):
        out += ("<div class='banner sim' role='note'><strong>Simulated models</strong> — illustrative results, "
                "not a measurement of any real model.</div>")
    if include_full_outputs:
        out += ("<div class='banner danger' role='alert'><strong>Full model outputs included.</strong> This report "
                "contains unredacted answers to harmful requests. Handle it as sensitive material and do not "
                "circulate it beyond the review.</div>")
    return out


def _redacted(text) -> str:
    return f"<pre class='redacted'>{_e(redact_text(text))}</pre>"


def _output(text, *, harmful_failure: bool, include_full: bool, limit: int = MAX_ANSWER_CHARS) -> str:
    """A model answer: redacted when it is a failed answer to a harmful request (unless full outputs)."""
    if harmful_failure and not include_full:
        return _redacted(text)
    text = "" if text is None else str(text)
    if len(text) > limit:
        text = text[:limit] + f"\n… [truncated, {len(text):,} chars total]"
    return f"<pre>{_e(text)}</pre>"


def _clip(value, n: int = MAX_ARG_CHARS) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= n else text[:n] + f"… [{len(text):,} chars]"


def _tool_calls(calls: list[dict]) -> str:
    if not calls:
        return ""
    rows = "".join(
        f"<tr><td><code>{_e(c.get('name'))}</code></td><td>"
        + "<br>".join(f"<code>{_e(k)}</code> = {_e(_clip(v))}" for k, v in (c.get("arguments") or {}).items())
        + "</td></tr>"
        for c in calls
    )
    return (f"<p class='muted'>Tool calls the agent made</p><div class='table-wrap'><table class='calls'>"
            f"<thead><tr><th>Tool</th><th>Arguments</th></tr></thead><tbody>{rows}</tbody></table></div>")


def _tags(d: dict) -> str:
    return "".join(f"<span class='tag'>{_e(t)}</span>" for t in (d.get("type"), d.get("pack")) if t)


def _sev(sev) -> str:
    cls = "sev5" if (sev or 0) >= 5 else "sev4" if (sev or 0) == 4 else "sevn"
    return f"<span class='sev {cls}'>S{_e(sev if sev is not None else '?')}</span>"


def _case_summary_line(d: dict, verdict: str) -> str:
    line = d.get("impact") or (risk_sentence(d) if not d.get("candidate_passed") else None)
    return (f"<summary>{_sev(d.get('severity'))} <strong>{_e(d.get('name'))}</strong> "
            f"<span class='muted'>· {verdict}</span>"
            f"{f'<div class=line>{_e(line)}</div>' if line else ''}</summary>")


def _case_block(d: dict, include_full: bool) -> str:
    harmful = bool(d.get("should_refuse"))
    failed = ", ".join(d.get("candidate_failed_metrics") or []) or "—"
    evidence = "".join(f"<li>{_e(_clip(x, MAX_EVIDENCE_CHARS))}</li>" for x in (d.get("evidence") or []))
    goal = f"<p><strong>Attacker's goal:</strong> {_e(d['attack_goal'])}</p>" if d.get("attack_goal") else ""
    impact = f"<p class='impact'><strong>Business impact:</strong> {_e(d['impact'])}</p>" if d.get("impact") else ""
    inj = d.get("type") == "injection"
    limit = MAX_INJECTION_ANSWER_CHARS if inj and not include_full else MAX_ANSWER_CHARS
    verdict = ("regressed: passed before, fails now" if d["base_passed"] and not d["candidate_passed"]
               else "improved: failed before, passes now")
    return (f"<details class='case'>{_case_summary_line(d, verdict)}<div class='body'><div>{_tags(d)}</div>{goal}{impact}"
            f"<p class='muted'>Prompt</p>{_output(d.get('prompt'), harmful_failure=False, include_full=True)}"
            f"<p class='muted'>Before — {'passed' if d['base_passed'] else 'failed'} · decided by {_decided(d.get('base_decided_by'))}</p>"
            f"{_output(d.get('base_answer'), harmful_failure=harmful and not d['base_passed'], include_full=include_full, limit=limit)}"
            f"<p class='muted'>After — {'passed' if d['candidate_passed'] else 'failed'} · decided by {_decided(d.get('candidate_decided_by'))} · failed: {_e(failed)}</p>"
            f"{_output(d.get('candidate_answer'), harmful_failure=harmful and not d['candidate_passed'], include_full=include_full, limit=limit)}"
            f"{_tool_calls(d.get('agent_tool_calls') or []) if not d['candidate_passed'] else ''}"
            f"{'<p class=muted>Evidence</p><ul>' + evidence + '</ul>' if evidence else ''}</div></details>")


def _grouped(cases: list[dict], render, *, noun: str) -> str:
    """Cases grouped by category; groups with the most severe cases first, then by size."""
    if not cases:
        return "<p class='muted'>None.</p>"
    groups: dict[str, list[dict]] = {}
    for d in cases:
        groups.setdefault(d.get("category") or d.get("type") or "other", []).append(d)
    order = sorted(groups, key=lambda g: (-max((x.get("severity") or 0) for x in groups[g]), -len(groups[g]), g))
    out = []
    for g in order:
        items = sorted(groups[g], key=lambda x: (-(x.get("severity") or 0), x.get("name") or ""))
        sev5 = sum(1 for x in items if (x.get("severity") or 0) >= 5)
        n = len(items)
        out.append(f"<details class='group' open><summary><strong>{_e(g)}</strong> — {n} {noun}{'' if n == 1 else 's'}"
                   f"{f' · <span class=bad>{sev5} severity-5</span>' if sev5 else ''}</summary>"
                   + "".join(render(x) for x in items) + "</details>")
    return "".join(out)


def _exec_summary(rel: dict) -> str:
    ok = rel["decision"] == "PASS"
    risks = "".join(
        f"<li>{_e(r['risk'])} <span class='muted'>({r['cases']} case{'' if r['cases'] == 1 else 's'}, "
        f"severity {_e(r['severity'])})</span></li>" for r in rel.get("top_risks") or [])
    notes = "".join(f"<li>{_e(n)}</li>" for n in rel.get("notes") or [])
    checks = " · ".join(
        f"{'✓' if c['ok'] else '✗'} {_e('tier ' + str(c['required']) if c['name'] == 'tier' else 'no new severity-5 regressions')}"
        f" <span class='muted'>(actual: {_e(c['actual'])})</span>" for c in rel.get("checks") or [])
    return (f"<section class='exec {'pass' if ok else 'fail'}'><div class='decision'>"
            f"<span class='verdict'>Release decision: {_e(rel['decision'])}</span>"
            f"<span class='reason'>{_e(rel['reason'])}</span></div>"
            f"<p class='meta'>Gates: {checks}</p>"
            + (f"<h3>Top risks</h3><ol>{risks}</ol>" if risks else "")
            + f"<p class='action'><strong>Recommended action:</strong> {_e(rel['recommended_action'])}</p>"
            + (f"<ul class='meta'>{notes}</ul>" if notes else "")
            + "</section>")


def render_comparison_report(db: Session, base_run: Run, candidate_run: Run, *, now: str | None = None,
                             include_full_outputs: bool = False) -> str:
    # Raw answers here; this renderer redacts them itself (same rules, see _output).
    cmp = build_comparison(db, base_run, candidate_run, include_full_outputs=True)
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    b, c, tc = cmp["base"], cmp["candidate"], cmp["tier_change"]
    tier_cls = "bad" if tc["direction"] == "down" else "good" if tc["direction"] == "up" else "muted"
    warn = ""
    if not cmp["case_set"].get("identical", False):
        warn = f"<p class='warn'><strong>Warning:</strong> {_e(cmp['case_set'].get('warning') or 'runs did not use identical cases')}</p>"
    regs, imps = cmp["flipped"]["regressions"], cmp["flipped"]["improvements"]
    reasons = "".join(f"<li>{_e(r)}</li>" for r in c.get("reasons") or [])
    shared = cmp["common_total"]
    render = lambda d: _case_block(d, include_full_outputs)  # noqa: E731
    body = _banners([b, c], include_full_outputs) + _header("comparison report", [b, c], now) + warn + _exec_summary(cmp["release"]) + f"""
<div class='cards'>
<div class='card'><div class='muted'>Before · {_e(b['model'])}</div><div class='big'>{_pct(b.get('pass_rate'))}</div><div>{_tier_label(b)}</div></div>
<div class='card'><div class='muted'>After · {_e(c['model'])}</div><div class='big'>{_pct(c.get('pass_rate'))}</div><div>{_tier_label(c)}</div></div>
<div class='card'><div class='muted'>Overall change</div><div class='big'>{_delta(cmp.get('pass_rate_delta'))}</div><div class='{tier_cls}'>Tier {_e(tc['from'])} → {_e(tc['to'])}</div></div>
<div class='card'><div class='muted'>Flipped cases</div><div class='flips'><span class='bad'>{len(regs)} regression{'' if len(regs) == 1 else 's'}</span> · <span class='good'>{len(imps)} improvement{'' if len(imps) == 1 else 's'}</span></div><div class='muted'>of {shared} shared case{'' if shared == 1 else 's'}</div></div>
</div>
<h2>Summary</h2>
<p>On the same {shared} cases, the pass rate moved from <strong>{_pct(cmp.get('base_pass_rate'))}</strong> to <strong>{_pct(cmp.get('candidate_pass_rate'))}</strong> ({_delta(cmp.get('pass_rate_delta'))}); the tier moved from <strong>{_e(tc['from'])}</strong> to <strong>{_e(tc['to'])}</strong>. {len(regs)} case(s) regressed and {len(imps)} improved.</p>
{f"<p class='muted'>Why the after-run got its tier:</p><ul>{reasons}</ul>" if reasons else ""}
{_decided_by_line(c.get('decided_by') or {})}
{_delta_table("Per category", cmp['categories'])}
{_delta_table("Per pack", cmp['packs'])}
<h2>Regressions (pass → fail), by category</h2>
<p class='meta'>Most severe first. Answers to harmful requests are redacted{' — full outputs are included in this copy' if include_full_outputs else ' (generate with full outputs to see them)'}; injection tool calls are always shown.</p>
{_grouped(regs, render, noun='regression')}
<h2>Improvements (fail → pass)</h2>
{_grouped(imps, render, noun='improvement')}
{_methodology([b, c])}"""
    return _page(f"Redline comparison — {b['model']} vs {c['model']}", body)


def render_run_report(db: Session, run: Run, *, now: str | None = None, include_full_outputs: bool = False) -> str:
    brief = run_brief(run)
    summary = run.summary if isinstance(run.summary, dict) else {}
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = db.query(RunResult).filter(RunResult.run_id == run.id).all()
    tcs = {str(t.id): t for t in db.query(Testcase).filter(Testcase.id.in_([r.testcase_id for r in rows])).all()} if rows else {}
    cfg = load_tier_config()
    failures = []
    for r in rows:
        if r.passed:
            continue
        tc = tcs.get(str(r.testcase_id))
        jr = r.judge_reasoning or {}
        evidence = jr.get("evidence") or [x for x in (jr.get("refusal_reasoning"), jr.get("hallucination_reasoning"), jr.get("reasoning")) if x]
        exp = (tc.expected_behavior or {}) if tc else {}
        d = {
            "name": tc.name if tc else str(r.testcase_id), "type": tc.type if tc else None, "pack": tc.pack if tc else None,
            "severity": tc.severity if tc else None, "prompt": tc.prompt if tc else "", "tags": list(tc.tags or []) if tc else [],
            "category": tier_category(tc.type, tc.pack, cfg) if tc else None, "should_refuse": bool(exp.get("should_refuse")),
            "answer": r.raw_output, "decided_by": jr.get("decided_by"), "attack_goal": jr.get("attack_goal"),
            "agent_tool_calls": jr.get("agent_tool_calls") or [], "candidate_answer": r.raw_output, "candidate_passed": False,
            "evidence": evidence, "data_sources": [o.get("name") for o in ((exp.get("injection") or {}).get("tool_outputs") or [])],
            "data_text": " ".join(str(o.get("result", "")) for o in ((exp.get("injection") or {}).get("tool_outputs") or [])),
            "failed": sorted(k for k, v in (r.scores or {}).items() if v is False),
        }
        d["impact"] = injection_impact(d) if d["type"] == "injection" else None
        failures.append(d)

    def render(d: dict) -> str:
        inj = d["type"] == "injection"
        evidence = "".join(f"<li>{_e(_clip(x, MAX_EVIDENCE_CHARS))}</li>" for x in d["evidence"])
        return (f"<details class='case'>{_case_summary_line(d, 'failed')}<div class='body'><div>{_tags(d)}</div>"
                + (f"<p><strong>Attacker's goal:</strong> {_e(d['attack_goal'])}</p>" if d.get("attack_goal") else "")
                + (f"<p class='impact'><strong>Business impact:</strong> {_e(d['impact'])}</p>" if d.get("impact") else "")
                + f"<p class='muted'>Prompt</p>{_output(d['prompt'], harmful_failure=False, include_full=True)}"
                f"<p class='muted'>Answer · decided by {_decided(d['decided_by'])} · failed: {_e(', '.join(d['failed']) or '—')}</p>"
                f"{_output(d['answer'], harmful_failure=d['should_refuse'], include_full=include_full_outputs, limit=MAX_INJECTION_ANSWER_CHARS if inj and not include_full_outputs else MAX_ANSWER_CHARS)}"
                f"{_tool_calls(d['agent_tool_calls'])}"
                + (f"<p class='muted'>Evidence</p><ul>{evidence}</ul>" if evidence else "")
                + "</div></details>")

    reasons = "".join(f"<li>{_e(x)}</li>" for x in brief.get("reasons") or [])
    ci = summary.get("confidence_interval") or {}
    body = _banners([brief], include_full_outputs) + _header("run report", [brief], now) + f"""
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
<h2>Failed cases, by category</h2>
<p class='meta'>Most severe first. Answers to harmful requests are redacted{' — full outputs are included in this copy' if include_full_outputs else ''}; injection tool calls are always shown.</p>
{_grouped(failures, render, noun='failure')}
{_methodology([brief])}"""
    return _page(f"Redline run report — {brief['model']}", body)
