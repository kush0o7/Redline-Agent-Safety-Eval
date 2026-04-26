# Contributing to Redline

Thanks for your interest. Contributions are welcome — new test cases, provider integrations, scoring improvements, and bug fixes all move the project forward.

## Getting started

```bash
git clone https://github.com/kush0o7/Redline-Agent-Safety-Eval
cd Redline-Agent-Safety-Eval
cd backend
pip install -e ".[dev]"
pytest tests/ -v   # should be 17/17 green with no API calls
```

Tests use `DEV_FAKE_JUDGE=true` and `DEV_FAKE_PROVIDER=true` — no LLM keys needed.

## What to work on

High-value contributions:

- **New test cases** — add entries to `backend/app/evals/testcases.py`. Especially: multi-turn injection, tool-use misuse, overconfidence on ambiguous factual claims.
- **New provider integrations** — add a class to `backend/app/llm/provider.py` and wire it in `get_provider()`. See existing providers for the pattern.
- **Scoring improvements** — `backend/app/evals/scoring.py` and `backend/app/llm/judge.py`. Better prompts, new metrics, calibration data.
- **UI improvements** — `ui/` is plain HTML + JS, no build step needed.

Check open issues for things already on the list.

## Pull request guidelines

- Keep PRs focused. One change per PR is easier to review.
- If you add a new provider or test category, add a test in `backend/tests/`.
- Run `pytest tests/ -v` before opening the PR — all tests must pass.
- Write a clear PR description: what, why, and how to test it.

## Reporting bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md). Include:
- What you ran (provider, model, testcase type)
- What you expected
- What happened (error message, unexpected output)
- Your environment (OS, Docker version, Python version)

## Questions

Open a [GitHub Discussion](https://github.com/kush0o7/Redline-Agent-Safety-Eval/discussions) — not an issue — for questions about how things work or what to build next.
