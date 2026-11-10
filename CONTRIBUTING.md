# Contributing to Redline

Redline is independent, self-hosted safety testing for the AI you own. Contributions are welcome: new test cases and domain packs, provider integrations, scoring and judge-accuracy improvements, and bug fixes.

## Getting started

```bash
git clone https://github.com/kush0o7/Redline-Agent-Safety-Eval
cd Redline-Agent-Safety-Eval/backend
pip install -e ".[dev]"
pytest tests/ -q   # 202 tests, no API keys required
```

Tests use `DEV_FAKE_JUDGE=true`, `DEV_FAKE_PROVIDER=true` and `REDLINE_ENV=development`, all set automatically in `conftest.py`.

## High-value contributions

### New test cases

Add core cases to `backend/app/evals/testcases.py`. Industry cases belong in a domain pack: a module under `backend/app/evals/packs/` (see `financial_services.py`), registered in `packs/__init__.py`. Each pack is reported as its own tier category. Each testcase needs:

```python
TestcaseSeed(
    type="jailbreak",           # category string — stratified sampling uses this
    name="Short descriptive name",
    prompt="The adversarial prompt text",
    expected_behavior={
        "should_refuse": True,
        # Optional: fail if these appear in the response (skipped when model refused)
        "must_not_include": ["keyword1", "keyword2"],
    },
    severity=4,                 # 1 (benign probe) to 5 (severe harm)
    tags=["persona", "jailbreak"],
    pack="core",                # or a domain pack name, e.g. "financial_services"
),
```

The most needed additions:
- **Domain packs**: insurance, healthcare and other regulated industries, with benign look-alike questions so over-refusal is measured too
- **Tool-use misuse** — prompts designed to get agents to call dangerous tools
- **Overconfidence probes** — questions with no knowable answer where the model should say "I don't know"
- **More HarmBench categories** — especially contextual behaviors (background doc + request)

### New LLM providers

1. Add a class to `backend/app/llm/provider.py` implementing `BaseProvider.complete(messages, model, temperature, seed)`
2. Wire it in `get_provider()`
3. Add env vars to `backend/app/core/config.py` (Settings class)
4. Document in `.env.example`
5. Add a test in `backend/tests/`

### Scoring improvements

`backend/app/evals/scoring.py` and `backend/app/llm/judge.py`. The StrongREJECT formula is already implemented. Useful directions:
- Better judge prompts with more calibrated rubrics
- Domain-specific scoring (e.g. technical accuracy for code-generation agents)
- Human-labelled judge validation data (planned format: JSONL of testcase, answer, human verdict)

### UI improvements

`ui/` is plain HTML + JS — no build step, no npm, no bundler. Edit and refresh. The design system is in `ui/styles.css`.

## Pull request guidelines

- **One change per PR** — easier to review and revert if needed.
- **Add a test** if you add a new provider or test category.
- **Run `pytest tests/ -q`** before opening. All tests must stay green.
- **Write a clear PR description**: what changed, why, and how to test it manually.

## Key files to know

| File | Purpose |
|------|---------|
| `backend/app/evals/testcases.py` | All adversarial test cases |
| `backend/app/evals/scoring.py` | Pass/fail logic and StrongREJECT scoring |
| `backend/app/llm/judge.py` | Judge prompt and structured output parsing |
| `backend/app/evals/metrics.py` | Wilson CI and category breakdown |
| `backend/app/evals/runner.py` | Core eval loop (per-testcase execution + DB writes) |
| `backend/app/llm/provider.py` | All LLM provider implementations |
| `backend/app/core/security.py` | SSRF validation, encryption, rate limiting |
| `backend/app/utils/tiers.py`, `tiers.default.toml` | Tier criteria and grading |
| `backend/app/evals/packs/` | Domain test packs |
| `ui/app.js` | Frontend logic (eval form, result rendering, demo banner) |

## Architecture notes

- `POST /quick-eval` creates project + testcases + run + enqueues job atomically — the common case in one API call
- `/runs/compare` must be registered **before** `/runs/{run_id}` in FastAPI — otherwise `compare` gets parsed as a UUID
- `DEV_FAKE_JUDGE=true` in `conftest.py` ensures tests never hit a real judge LLM
- `must_not_include` is intentionally skipped when the judge says the model refused — prevents false positives from refusals that name the refused topic

## Reporting bugs

Use [GitHub Issues](https://github.com/kush0o7/Redline-Agent-Safety-Eval/issues). Include:
- Provider, model, and testcase type that triggered the bug
- What you expected vs. what happened
- Error message or unexpected output
- OS, Docker version (if using Docker), Python version

## Questions

Open a [GitHub Discussion](https://github.com/kush0o7/Redline-Agent-Safety-Eval/discussions) — not an issue — for questions about the design or what to build next.
