# Redline — Claude Code context

Redline is a self-hosted safety evaluation platform for LLM agents. It runs adversarial test cases (jailbreaks, prompt injection, hallucination) against an LLM agent, scores each response with an LLM-as-judge, and stores full runs + traces in Postgres.

## Quick orientation

```
backend/app/
  agents/      baseline_agent.py, debate_agent.py — orchestration modes
  api/         routes_evals.py, routes_runs.py, routes_testcases.py, routes_public.py
  core/        config.py (Settings via pydantic-settings), security.py, logging.py
  db/          models.py (Project, Testcase, Run, RunResult, Trace), session.py
  evals/       runner.py (core eval loop), scoring.py, testcases.py, metrics.py
  llm/         provider.py (OpenAI/Anthropic/Bedrock/Ollama/Fake), judge.py
  queue/       tasks.py (ARQ task), worker.py
  utils/       tiers.py (safety tier logic), time.py, ids.py
mcp-server/    Claude Code MCP integration (redline_mcp/server.py)
ui/            Static HTML + JS frontend (no build step)
```

## Key env vars

| Var | Purpose |
|---|---|
| `ADMIN_API_KEY` | Required for all API calls (`X-Admin-Key` header) |
| `LLM_PROVIDER` | `openai` / `anthropic` / `bedrock` / `ollama` / `fake` |
| `OPENAI_BASE_URL` | Override to point OpenAI provider at any compatible endpoint |
| `JUDGE_MODEL` | Model used for LLM-as-judge scoring (default: gpt-4o-mini) |
| `DEV_FAKE_JUDGE` | `true` = skip LLM judge, use keyword heuristics (tests only) |
| `DEV_FAKE_PROVIDER` | `true` = FakeProvider, no API calls (tests only) |

## Running tests (no Docker needed)

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v   # 17/17, no API keys required
```

Tests use `DEV_FAKE_JUDGE=true` and `DEV_FAKE_PROVIDER=true` (set in conftest.py).

## Adding a new LLM provider

1. Add a class to `backend/app/llm/provider.py` implementing `BaseProvider.complete()`
2. Wire it in `get_provider()`
3. Add env vars to `backend/app/core/config.py` (Settings class)
4. Document in `.env.example`
5. Add a test in `backend/tests/`

## Adding new test cases

Edit `backend/app/evals/testcases.py` → `load_default_testcases()`. Each testcase needs:
- `type`: category string (e.g. `"jailbreak"`, `"hallucination"`)
- `prompt`: the adversarial input
- `expected_behavior`: dict with scoring rules (e.g. `{"policy_compliance": true, "must_not_include": ["..."]}`)
- `severity`: 1–3

## Safety tiers (gamification)

| Tier | Pass rate | Color |
|---|---|---|
| 💎 Hardened | ≥ 90% | bright green |
| ✅ Safe | 75–89% | green |
| 🟡 Developing | 60–74% | yellow |
| 🔴 At Risk | < 60% | red |

Tiers are defined in `backend/app/utils/tiers.py` and used in the badge endpoint and quick-eval response.

## MCP server (Claude Code integration)

See `mcp-server/README.md`. Add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "redline": {
      "command": "redline-mcp",
      "env": { "REDLINE_URL": "http://localhost:8001", "REDLINE_API_KEY": "your-key" }
    }
  }
}
```

Then in Claude Code: *"Run 15 safety evals on my agent"* or *"Compare runs abc vs def"*.

## Architecture notes

- `POST /quick-eval` — all-in-one: creates project, seeds testcases, queues run, returns run_id
- `GET /projects/{id}/badge` — **public** (no auth), shields.io-compatible badge endpoint
- ARQ pool is stored on `app.state.arq_pool` (mocked with `AsyncMock` in tests)
- `/runs/compare` route must be registered BEFORE `/runs/{run_id}` in FastAPI or `compare` is parsed as a UUID
- `DEV_FAKE_JUDGE=true` in `conftest.py` ensures tests never call the real judge LLM
