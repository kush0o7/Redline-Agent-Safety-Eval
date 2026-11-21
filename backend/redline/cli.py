"""``redline``: before/after safety checks for the models you own, from the terminal.

    redline compare ollama/llama3.1 ollama/hermes3     # did the new version get less safe?
    redline scan ollama/llama3.1                       # one model against the tier criteria
    redline report ./redline-out                       # print the summary and rewrite the files again

Exit codes (CI-ready): 0 = pass, 1 = the release fails, 2 = error or interrupted.
Results, cached answers and progress live in --out (default ./redline-out); run the same
command again to resume an interrupted run.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from redline.models import (FREE_TIER_LINE, KEYWORD, ModelError, ModelSpec, check_models, choose_judge, is_free_tier,
                            ollama_url, parse_model)

EXIT_PASS, EXIT_FAIL, EXIT_ERROR = 0, 1, 2
DEFAULT_PACKS = "core,financial_services"
FREE_TIER_FLOOR = {"groq": 10.0, "gemini": 30.0}  # seconds between calls (runner.FREE_TIER_PACING_FLOOR)


def _eprint(*args) -> None:
    print(*args, file=sys.stderr, flush=True)


# ── Progress ──

class Progress:
    """A one-line progress bar on stderr (plain lines every ~10% when not a terminal)."""

    def __init__(self, label: str, total: int) -> None:
        self.label, self.total = label, total
        self.start = time.monotonic()
        self.tty = sys.stderr.isatty()
        self.last_step = -1

    def __call__(self, done: int, total: int, passed) -> None:
        total = total or self.total
        frac = done / max(total, 1)
        elapsed = time.monotonic() - self.start
        eta = f" · ~{(elapsed / frac - elapsed) / 60:.0f} min left" if 0 < frac < 1 and elapsed > 20 else ""
        extra = f" · {passed} passed" if passed is not None else ""
        if self.tty:
            bar = "█" * int(frac * 24) + "░" * (24 - int(frac * 24))
            sys.stderr.write(f"\r  {self.label:<34} [{bar}] {done}/{total}{extra}{eta}   ")
            if done >= total:
                sys.stderr.write("\n")
            sys.stderr.flush()
        else:
            step = int(frac * 10)
            if step != self.last_step:
                self.last_step = step
                _eprint(f"  {self.label}: {done}/{total}{extra}")


# ── Setup shared by the commands ──

def _job_key(**parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def _load_state(out: Path) -> dict:
    try:
        return json.loads((out / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(out: Path, state: dict) -> None:
    (out / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def _auto_concurrency(specs: list[ModelSpec]) -> int:
    if all(s.is_fake for s in specs):
        return 8
    if any(s.provider in ("ollama", "endpoint") for s in specs):
        return 2  # a local server answers one or two requests at a time; more just queue and time out
    return 4


def _grader_banner(judge: str, note: str | None, specs: list[ModelSpec]) -> None:
    if judge == KEYWORD:
        if all(s.is_fake for s in specs):
            print("  Grader: keyword rules (simulated models; fine for a demo).")
            return
        print("\n  ⚠ ⚠  GRADER: KEYWORD RULES — LESS RELIABLE  ⚠ ⚠")
        print(f"  Why: {note or 'requested with --judge keyword'}.")
        print("  Keyword rules only look for refusal phrases. In our own runs, keyword rules and an LLM judge")
        print("  reached different conclusions about the same pair of models. Treat this result as rough.")
        print("  Better: pull a local judge (ollama pull qwen2.5:7b), or pass --judge provider/model.\n")
    else:
        print(f"  Grader: {judge}" + (f"  (⚠ {note})" if note else ""))
    if is_free_tier(judge) or any(is_free_tier(s.raw) for s in specs):
        print(f"  ⚠ {FREE_TIER_LINE}")


def _prepare(args, specs: list[ModelSpec]):
    """Bootstrap settings, check the models and the judge. Returns (store, judge, fingerprints, settings values)."""
    from redline import local

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    local.bootstrap(out / "redline.db")
    fingerprints = check_models(specs)
    if args.judge is None and all(s.is_fake for s in specs):
        judge, note = KEYWORD, None
    else:
        judge, note = choose_judge(args.judge, specs)
    return out, local.Store(out / "redline.db"), judge, note, fingerprints


def _settings_for(judge: str, specs: list[ModelSpec]) -> dict:
    values = {
        "dev_fake_judge": judge == KEYWORD,
        "dev_fake_provider": False,
        "eval_pacing_seconds": 0.0,
        "ollama_base_url": ollama_url(),
    }
    if judge != KEYWORD:
        values["judge_model"] = judge
    if any(s.provider in ("ollama", "endpoint") for s in specs) or judge.startswith("ollama/"):
        values["llm_timeout_seconds"] = 300.0  # first request loads the weights; slow laptops need time
    return values


async def _run_models(store, specs, runs, judge, fingerprints, concurrency, use_cache, current, opts) -> None:
    from redline import local
    from redline.evals.run_info import build_run_info
    from redline.models import provider_for

    cache = local.SqliteAnswerCache(store, fingerprints) if use_cache else None
    # `redline try` (opts["fast"]) skips the fixed free-tier pauses and relies on rate-limit-aware retries.
    judge_floor = 0.0 if opts.get("fast") or judge == KEYWORD else FREE_TIER_FLOOR.get(judge.split("/", 1)[0], 0.0)
    for spec, run_id in zip(specs, runs):
        with store.Session() as db:
            from redline.db.models import Run

            run = db.get(Run, run_id)
            if run.status == "completed":
                print(f"  {spec.raw}: already done ({run.summary.get('passed')}/{run.summary.get('total')} passed), reusing.")
                continue
            already = local.stored_results(db, run)
            if already:
                print(f"  {spec.raw}: resuming ({already} cases already graded).")
            current["run_id"] = run.id
            answer_floor = 0.0 if opts.get("fast") else FREE_TIER_FLOOR.get(spec.provider, 0.0)
            conc = 1 if (answer_floor or judge_floor) else concurrency

            def on_phase(run, phase, total, _spec=spec):
                return Progress(f"{phase} · {_spec.raw}", total)

            hooks = local.RunHooks(
                provider=provider_for(spec, max_tokens=opts.get("max_tokens")),
                run_info=await build_run_info(run, provider=spec.provider, fingerprint=fingerprints.get(spec.raw)),
                cache=cache, concurrency=conc, answer_pacing=answer_floor, judge_pacing=judge_floor,
                on_phase=on_phase)
            summary = await local.execute(db, run, hooks)
            print(f"  {spec.raw}: passed {summary['passed']} of {summary['total']} ({summary['pass_rate'] * 100:.0f}%)")
    current["run_id"] = None


def _scrub(text: str) -> str:
    """Never echo a key back, even inside a provider's error message."""
    import os

    for name in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "HF_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
        value = os.environ.get(name)
        if value and len(value) > 8:
            text = text.replace(value, "***")
    return text


def _execute(store, specs, runs, judge, fingerprints, concurrency, use_cache, opts=None) -> int | None:
    """Run (or resume) the runs. Returns an exit code on Ctrl-C / failure, None on success."""
    from redline import local

    current: dict = {"run_id": None}
    try:
        asyncio.run(_run_models(store, specs, runs, judge, fingerprints, concurrency, use_cache, current, opts or {}))
    except KeyboardInterrupt:
        if current["run_id"]:
            local.mark_unfinished(store, current["run_id"], "interrupted")
        _eprint("\n\n  Stopped. Everything graded so far is saved (and every answer generated is cached).")
        _eprint("  Run the same command again to resume where it stopped.")
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 — report it plainly, keep what's done
        if current["run_id"]:
            local.mark_unfinished(store, current["run_id"], "failed", _scrub(f"{type(exc).__name__}: {str(exc)[:500]}"))
        _eprint(_scrub(f"\n\n  ✗ The run stopped: {type(exc).__name__}: {str(exc)[:600]}"))
        _eprint("  What finished is saved. Fix the cause, then run the same command again to resume.")
        if "rate limit" in str(exc).lower() or "ratelimit" in type(exc).__name__.lower():
            _eprint("  This is a rate limit: wait for the provider's quota to reset, or use a local judge.")
        return EXIT_ERROR
    return None


# ── Writing results ──

def _write_compare(out: Path, store, base_id, cand_id, specs, details: bool = False) -> int:
    from redline import local
    from redline.db.models import Run
    from redline.evals.comparison import build_comparison
    from redline.reports.html_report import render_comparison_report

    with store.Session() as db:
        base, cand = db.get(Run, base_id), db.get(Run, cand_id)
        for r in (base, cand):
            if r is None or r.status != "completed":
                _eprint(f"  ✗ Run {getattr(r, 'llm_model', '?')} isn't finished. Run the compare command again to resume it.")
                return EXIT_ERROR
        cmp = build_comparison(db, base, cand)
        print(local.format_comparison(cmp, base.llm_model, cand.llm_model, details=details))
        (out / "report.html").write_text(render_comparison_report(db, base, cand), encoding="utf-8")
        local.write_jsonl(out / "results.jsonl", local.results_rows(db, base) + local.results_rows(db, cand))
        (out / "summary.json").write_text(json.dumps(cmp, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    _print_files(out)
    return EXIT_PASS if cmp["release"]["decision"] == "PASS" else EXIT_FAIL


def _write_scan(out: Path, store, run_id, details: bool = False) -> int:
    from redline import local
    from redline.db.models import Run
    from redline.evals.comparison import run_brief
    from redline.reports.html_report import render_run_report

    with store.Session() as db:
        run = db.get(Run, run_id)
        if run is None or run.status != "completed":
            _eprint("  ✗ The scan isn't finished. Run the scan command again to resume it.")
            return EXIT_ERROR
        text, passed = local.format_scan(db, run, details=details)
        print(text)
        (out / "report.html").write_text(render_run_report(db, run), encoding="utf-8")
        local.write_jsonl(out / "results.jsonl", local.results_rows(db, run))
        brief = run_brief(run)
        ok, tier, min_tier = local.scan_verdict(run.summary or {})
        (out / "summary.json").write_text(json.dumps({"run": brief, "summary": run.summary, "result": {
            "decision": "PASS" if ok else "FAIL", "tier": tier, "min_tier": min_tier}}, indent=2, default=str), encoding="utf-8")
    _print_files(out)
    return EXIT_PASS if passed else EXIT_FAIL


def _print_files(out: Path) -> None:
    print("\n" + "─" * 78)
    print(f" Report:  {out / 'report.html'}")
    print(f" Results: {out / 'results.jsonl'}   Summary: {out / 'summary.json'}")
    print("─" * 78)


# ── Commands ──

def _start(args, specs: list[ModelSpec], command: str) -> tuple[int | None, Path | None, object, list]:
    from redline import local

    out, store, judge, note, fingerprints = _prepare(args, specs)
    from redline.evals.sampling import SamplingError  # after _prepare: settings must see the bootstrap env

    packs = [p.strip() for p in args.packs.split(",") if p.strip()]
    key = _job_key(command=command, models=[s.raw for s in specs], cases=args.cases, packs=packs, seed=args.seed,
                   judge=judge, fingerprints=[fingerprints.get(s.raw) for s in specs],
                   max_tokens=getattr(args, "max_tokens", None))
    print(f"\nRedline {command}: {'  →  '.join(s.raw for s in specs)}")
    print(f"  Cases: {args.cases} from {', '.join(packs)} (seed {args.seed}) · output: {out}")
    _grader_banner(judge, note, specs)

    with local.configured(**_settings_for(judge, specs)):
        state = _load_state(out)
        if state.get("key") == key and state.get("runs"):
            runs = state["runs"]
        else:
            if args.cases < 1:
                raise ModelError("--cases must be at least 1.")
            with store.Session() as db:
                try:
                    first = local.new_case_set_run(db, specs[0].raw, cases=args.cases, packs=packs, seed=args.seed)
                except SamplingError as exc:
                    raise ModelError(str(exc)) from exc
                runs = [str(first.id)] + [str(local.rerun(db, first, s.raw).id) for s in specs[1:]]
            _save_state(out, {"key": key, "command": command, "models": [s.raw for s in specs], "runs": runs,
                              "judge": judge, "created_at": datetime.now(timezone.utc).isoformat()})
        import uuid

        run_ids = [uuid.UUID(r) for r in runs]
        concurrency = args.concurrency or _auto_concurrency(specs)
        opts = {"fast": getattr(args, "fast", False), "max_tokens": getattr(args, "max_tokens", None)}
        code = _execute(store, specs, run_ids, judge, fingerprints, concurrency, not args.no_cache, opts)
    return code, out, store, run_ids


def cmd_compare(args) -> int:
    specs = [parse_model(args.before), parse_model(args.after)]
    code, out, store, runs = _start(args, specs, "compare")
    if code is not None:
        return code
    return _write_compare(out, store, runs[0], runs[1], specs, details=args.details)


def cmd_scan(args) -> int:
    specs = [parse_model(args.model)]
    code, out, store, runs = _start(args, specs, "scan")
    if code is not None:
        return code
    return _write_scan(out, store, runs[0], details=args.details)


def cmd_report(args) -> int:
    import uuid

    from redline import local

    out = Path(args.dir)
    state = _load_state(out)
    if not state.get("runs") or not (out / "redline.db").exists():
        raise ModelError(f"No Redline results in {out}. Run `redline compare A B --out {out}` first.")
    local.bootstrap(out / "redline.db")
    store = local.Store(out / "redline.db")
    runs = [uuid.UUID(r) for r in state["runs"]]
    if state.get("command") == "compare" and len(runs) == 2:
        return _write_compare(out, store, runs[0], runs[1], [parse_model(m) for m in state["models"]], details=args.details)
    return _write_scan(out, store, runs[0], details=args.details)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redline", description="Did your model get less safe? Before/after safety checks for models you own.",
        epilog="Start here: redline try (free key, 2-3 minutes). Models: ollama/x, openai/x, anthropic/x, groq/x, "
               "gemini/x, openrouter/x, hf/x, http://host:port/v1#model, fake-safe, fake-degraded. "
               "Exit codes: 0 pass, 1 release fails, 2 error.")
    parser.add_argument("--version", action="version", version=f"redline-evals {_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--cases", type=int, default=40, help="number of test cases (default 40; 30+ for a rated tier)")
        p.add_argument("--packs", default=DEFAULT_PACKS, help=f"test packs, comma-separated (default {DEFAULT_PACKS})")
        p.add_argument("--seed", type=int, default=7, help="sampling seed (default 7)")
        p.add_argument("--judge", default=None,
                       help="grader: 'keyword', or provider/model such as ollama/qwen2.5:7b or groq/openai/gpt-oss-120b "
                            "(default: a local Ollama judge if one is pulled, else keyword rules)")
        p.add_argument("--out", default="./redline-out", help="output folder (default ./redline-out)")
        p.add_argument("--concurrency", type=int, default=None, help="cases in flight at once (default: auto)")
        p.add_argument("--no-cache", action="store_true", help="re-generate answers instead of reusing cached ones")
        p.add_argument("--details", action="store_true", help="show technical details (test names, p-values, graders)")

    p = sub.add_parser("compare", help="compare two model versions on the exact same cases")
    p.add_argument("before", help="the current model, e.g. ollama/llama3.1")
    p.add_argument("after", help="the new version, e.g. ollama/hermes3")
    common(p)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("scan", help="test one model against the tier criteria")
    p.add_argument("model", help="e.g. ollama/llama3.1")
    common(p)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("report", help="print the summary again and rewrite report.html / results.jsonl")
    p.add_argument("dir", nargs="?", default="./redline-out", help="output folder of an earlier run (default ./redline-out)")
    p.add_argument("--details", action="store_true", help="show technical details (test names, p-values, graders)")
    p.set_defaults(func=cmd_report)

    from redline.try_cmd import add_try_parser

    add_try_parser(sub)
    return parser


def _version() -> str:
    try:
        from importlib.metadata import version

        return version("redline-evals")
    except Exception:  # noqa: BLE001
        return "dev"


def main(argv: list[str] | None = None) -> int:
    import warnings

    warnings.filterwarnings("ignore", message="pkg_resources is deprecated")  # LiteLLM import noise
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # Windows consoles without UTF-8: no crash on ✓ / █
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ModelError as exc:
        _eprint(f"\n  ✗ {exc}")
        return EXIT_ERROR
    except KeyboardInterrupt:
        _eprint("\n  Stopped.")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
