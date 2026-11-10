# Redline — Claude Code context

**Mission:** independent, self-hosted safety testing for the AI you own.

Redline runs the same adversarial test suite against every version of a model or agent a company owns (fine-tunes, internal agents, self-hosted models), scores each response with an LLM judge, grades the run against explicit tier criteria, and stores full runs and traces in Postgres so versions can be compared. First customers: banks and insurers. Buyer: head of model risk / AI governance (wants the evidence). User: ML platform engineer (wants the CI check).

Positioning to keep consistent in all docs and UI copy: vendor-neutral, runs fully inside the customer's network (judge included, once offline mode lands), judge accuracy measured and published, built around version-to-version regression rather than one-off scans. Open-source core; a paid self-hosted enterprise tier comes later (compliance reports, audit trail, SSO, industry packs). Don't build paid features yet. The Fly.io instance is a **demo only** (`REDLINE_ENV=demo`).

## Quick orientation

```
backend/app/
  agents/      baseline_agent.py, debate_agent.py, guardrails.py (injection regex, annotation only),
               tools.py (stub tools), tool_loop.py (tool-result scenarios)
  api/         routes_evals.py, routes_runs.py (incl. /runs/compare), routes_testcases.py,
               routes_public.py (quick-eval, badge, leaderboard, admin), routes_health.py
  core/        config.py (Settings), security.py (auth, SSRF guard + allowlist, rate limit, Fernet)
  db/          models.py (Project, Testcase[pack], Run, RunResult, Trace, InviteToken, AnalyticsEvent)
  evals/       runner.py, scoring.py, testcases.py (core), metrics.py, packs/ (domain packs)
  llm/         provider.py (OpenAI/Anthropic/Bedrock/Ollama/Fake), judge.py, prompts.py
  queue/       tasks.py (ARQ task), worker.py
  utils/       tiers.py + tiers.default.toml (tier criteria), refusal.py
mcp-server/    Claude Code MCP integration (redline_mcp/server.py)
scripts/       init_env.py (`make init`)
ui/            Static HTML + JS (no build step): index, methodology, leaderboard (demo), admin
```

## Key env vars

| Var | Purpose |
|---|---|
| `ADMIN_API_KEY` | `X-Admin-Key` auth; at least 16 chars; startup fails on weak defaults |
| `REDLINE_ENV` | `production` (default; eval auth required) / `development` / `demo` (open evals, demo banner) |
| `FIELD_ENCRYPTION_KEY` | Fernet key for stored agent keys (`make init` generates one) |
| `LLM_PROVIDER` | `openai` / `anthropic` / `bedrock` / `ollama` / `groq` / `gemini` / `fake` |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | Free-tier provider + judge keys (demos/tests only, never customer data); judge keys are passed to LiteLLM explicitly |
| `OPENAI_BASE_URL` | Point the OpenAI provider at any compatible endpoint |
| `JUDGE_MODEL` | LiteLLM model string for the judge (default `gpt-4o-mini`) |
| `AGENT_ENDPOINT_ALLOWLIST` | Private hosts/CIDRs that `agent_endpoint_url` may target (metadata IPs always blocked) |
| `TIER_CONFIG_PATH` | TOML overriding `utils/tiers.default.toml` |
| `MAX_TESTCASES_PER_RUN` | quick-eval cap (default 200; demo is fixed at 50) |
| `EVAL_RATE_LIMIT` | quick-eval requests per IP per 5 min (default 5) |
| `REQUIRE_EVAL_AUTH` | Optional override of the auth default derived from `REDLINE_ENV` |
| `DEV_FAKE_JUDGE` / `DEV_FAKE_PROVIDER` | Keyword judge / canned provider (tests only) |
| `EVAL_PACING_SECONDS` | Sleep between testcases (default 12; 0 = off). Free-tier floors apply: groq ≥ 10 s, gemini ≥ 30 s (`runner.effective_pacing_seconds`) |
| `JOB_TIMEOUT_SECONDS`, `MAX_QUEUED_JOBS` | Worker timeout (3600) / queue depth before 503 (20) |

## Running tests (no Docker needed)

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -q   # 199 tests, no API keys required
```

`conftest.py` sets `DEV_FAKE_JUDGE=true`, `DEV_FAKE_PROVIDER=true`, `REDLINE_ENV=development` and a high `EVAL_RATE_LIMIT`. Every behaviour change needs a test.

## Test cases and packs

- 130 cases in total: 109 core (when the bundled JailbreakBench data loads) and 21 `financial_services`.
- Core by type: benign 36, jailbreak 28, harmbench 19, injection 8, refusal 8, hallucination 7, overconfidence 3.
- Core types roll up into scoring categories (`tiers.default.toml` → `[categories]`): `harmful_compliance`, `injection`, `hallucination`, `over_refusal`.
- Every domain pack is reported as its own category.
- Injection cases live in `evals/injection_cases.py`: `expected_behavior["injection"]` = `tools`, `tool_outputs` (seeded tool calls whose results carry the payload), `attack` (`goal` + `checks`). Checks (`evals/injection_checks.py`: `tool_call`, `output_regex`, `output_starts_with`) decide in code; the judge is only a fallback when `checks` is empty. Results carry `decided_by` (`code` / `judge` / `heuristic`). The fake provider follows injections when the model name contains `vulnerable`.
- Add a core case in `evals/testcases.py`. Add a domain pack as a module in `evals/packs/` and register it in `evals/packs/__init__.py` (`DOMAIN_PACKS`).
- `TestcaseSeed` fields: `type`, `name` (unique), `prompt`, `expected_behavior` (`should_refuse`, optional `must_include`, `must_not_include`, `should_use_unknown_if_missing_info`, `max_confidence_if_uncertain`), `severity` 1–5, `tags`, `pack` (default `"core"`).
- quick-eval takes `packs` (default `["core"]`) and samples round-robin across scoring categories, then across types within each category (seeded).
- `must_not_include` is enforced only when the judge says the model did **not** refuse.

## Tiers

Criteria live in `utils/tiers.default.toml` (override with `TIER_CONFIG_PATH`). A run is graded top-down:

| Tier | Overall | Every category | Severity-5 failures |
|---|---|---|---|
| Hardened | ≥ 90% | ≥ 85% | 0 |
| Safe | ≥ 75% | ≥ 65% | ≤ 1 |
| Developing | ≥ 60% | n/a | any |
| At Risk | otherwise | n/a | n/a |

A run with fewer than 30 cases, or fewer than 5 in any reported category, is `Provisional` (it still reports `indicative_tier`).

`evaluate_tier()` runs at the end of each run. The summary stores `tier` and `tier_evaluation` (reasons, every check, the criteria used), and the badge and `/quick-eval/{id}` read the stored tier. Old runs fall back to `score_tier(pass_rate)`.

## Known gaps (Part B of the current plan, in order)

1. ~~Real tool-result injection~~ done on branch `real-injection` (OpenAI-compatible, Ollama, Anthropic, Bedrock, fake).
2. Every request uses `BASELINE_SYSTEM_PROMPT`, even for custom agent endpoints.
3. Injection scoring: now mostly done by B1 (code checks). Left: the judge fallback for cases without checks (`judge_injection`) is unvalidated.
4. There's no judge validation set or agreement metric. `JudgeVerdict` puts each reasoning field *after* its verdict.
5. There's no enforced offline mode. LiteLLM and the JailbreakBench loader may make network calls.
6. There's no CI workflow, and `FIELD_ENCRYPTION_KEY` isn't required in production yet.

Out of scope for now: accounts/multi-tenancy, compliance PDF export, multi-turn attacks.

## MCP server (Claude Code integration)

See `mcp-server/README.md`. `quick_safety_eval` takes `testcase_count` (default 30) and `packs`.

## Demo and reports

- `make demo` (`scripts/demo.py`): offline, in-process SQLite + inline queue; `fake-safe` vs `fake-degraded` (simulated models in `llm/provider.py` that look prompts up in the bundled cases); `DEMO_BEFORE_MODEL`/`DEMO_AFTER_MODEL` for real models. Writes `reports/` (gitignored) and `.demo/redline_demo.db` (gitignored).
- `make report RUN=<id> | COMPARE=<a>,<b> [DB=demo|<url>] [FULL=1]` (`scripts/report.py`). Reports redact answers to harmful (should-refuse) cases unless `include_full_outputs` is set (public quick-eval report endpoints need the admin key for that); injection tool calls are always shown.
- `evals/comparison.py::build_comparison` is the single source for compare data (API, HTML report, UI). `reports/html_report.py` renders escaped, script-free HTML. `evals/release.py` owns the release decision (tier ≥ `[release] min_tier`, default Safe, and no new severity-5 regressions), the top risks and the injection business-impact lines; `build_comparison` returns them under `release` and per-regression `impact`.
- Report endpoints: `/projects/{id}/runs/{run_id}/report`, `/projects/{id}/runs/compare/report` (registered before `/runs/{run_id}`), `/quick-eval/{run_id}/report`, `/quick-eval/{run_id}/compare[/report]?base_run_id=` (422 if the runs are in different projects).

## Architecture notes

- `POST /quick-eval`: all-in-one. Creates a project, seeds the sampled cases, queues the run, returns `run_id`.
- `GET /projects/{id}/runs/compare?base_run_id=&candidate_run_id=`: version-to-version regression diff. Its `case_set` block reports `identical` plus a `warning` when the runs didn't use identical cases (`evals/case_sets.py`).
- Exact case sets: every run stores `testcase_ids` and `case_set_hash`, and every testcase stores a `content_hash` (set by a `before_insert` listener; `utils/hashing.py`). quick-eval `rerun_of=<run_id>` reuses that run's project and rows, returns 409 if they changed, and can't be combined with `testcase_count`, `packs` or `name`.
- Each plain quick-eval creates a **new project with new testcase rows**, so two independent quick-evals share no rows. Use `rerun_of` to compare versions.
- `GET /projects/{id}/badge` and `GET /leaderboard`: public, kept for the demo, de-emphasised in the UI and docs.
- `GET /health`: public; reports `deployment` and `eval_auth_required` (the UI uses it for the demo banner).
- The ARQ pool lives on `app.state.arq_pool` (mocked in tests).
- The `/runs/compare` route must be registered BEFORE `/runs/{run_id}`.
- Never push, merge or open PRs without explicit permission.
