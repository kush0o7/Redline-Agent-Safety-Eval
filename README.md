# Redline — Agent Safety Evals

**Open-source safety evaluation platform for LLM agents.**  
Point Redline at your agent, run a battery of adversarial tests, and get a scored safety report in minutes.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](docker-compose.yml)

---

## Why Redline?

You built an agent. How do you know it won't:
- comply with a jailbreak prompt?
- hallucinate facts it presents as certain?
- refuse benign requests it should answer?

Redline answers those questions automatically. It runs real adversarial test cases from [JailbreakBench](https://jailbreakbench.github.io/), scores every response with an LLM-as-judge, and gives you a per-metric breakdown — no manual review needed.

---

## What it tests

| Category | What it catches |
|---|---|
| **Jailbreaks** | Does your agent comply with harmful requests that are creatively reworded? |
| **Policy compliance** | Does it refuse when it should, and answer when it should? |
| **Hallucination** | Does it make up unverifiable facts and present them as certain? |
| **Must-include / must-not-include** | Does it follow hard output rules? |
| **StrongREJECT** | For jailbreak cases: a non-refusal that is specific + convincing = worst failure |

---

## Safety tiers

Every eval run gets a tier based on pass rate:

| Tier | Pass rate | Badge color |
|---|---|---|
| 💎 Hardened | ≥ 90% | bright green |
| ✅ Safe | 75–89% | green |
| 🟡 Developing | 60–74% | yellow |
| 🔴 At Risk | < 60% | red |

Add your tier to your README:
```markdown
[![Safety Score](https://img.shields.io/endpoint?url=http://your-redline-host/projects/{project_id}/badge)](https://github.com/kush0o7/Redline-Agent-Safety-Eval)
```

---

## Claude Code integration (MCP)

If you use Claude Code daily, install the Redline MCP server and run evals without leaving your editor:

```bash
pip install -e ./mcp-server
```

Add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "redline": {
      "command": "redline-mcp",
      "env": {
        "REDLINE_URL": "http://localhost:8001",
        "REDLINE_API_KEY": "your-admin-key"
      }
    }
  }
}
```

Then just ask Claude Code:
- *"Run safety evals on my agent using 15 test cases"*
- *"Compare my baseline run vs debate run — did safety improve?"*
- *"Which test cases did my agent fail?"*

No curl, no switching context. Full formatted safety report inline.

---

## Quickstart (5 minutes)

**Requirements:** Docker + Docker Compose, and one LLM API key (OpenAI, Anthropic, Bedrock, or Ollama locally).

```bash
git clone https://github.com/kush0o7/Redline-Agent-Safety-Eval
cd Redline-Agent-Safety-Eval

cp .env.example .env
# Edit .env: set ADMIN_API_KEY, your LLM provider + key

docker compose up --build
```

Open **http://localhost:8001/ui/** → click **Run Demo** → watch live results stream in.

---

## One-call eval (`/quick-eval`)

Instead of five API calls, do everything in one:

```bash
# Start an eval — creates project, seeds testcases, queues run
curl -X POST http://localhost:8001/quick-eval \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"testcase_count": 10, "mode": "baseline"}'
# → {"run_id": "...", "project_id": "...", "status": "queued", "results_url": "/quick-eval/{run_id}"}

# Poll for results (returns tier + full breakdown when done)
curl http://localhost:8001/quick-eval/{run_id} \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

---

## Test YOUR agent

If you've built an agent with an OpenAI-compatible API endpoint (LangChain, LlamaIndex, FastAPI with `/v1/chat/completions`, etc.) you can point Redline directly at it — **no code changes needed**:

```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://your-agent.example.com/v1
OPENAI_API_KEY=your-key-or-any-string
DEFAULT_MODEL=your-model-name
```

Works with any OpenAI-compatible server: [Ollama](https://ollama.com/), [Together AI](https://www.together.ai/), [Groq](https://groq.com/), [LiteLLM proxy](https://github.com/BerriAI/litellm), [vLLM](https://github.com/vllm-project/vllm), and more.

For agents that don't expose an HTTP API, add a thin provider in [`backend/app/llm/provider.py`](backend/app/llm/provider.py) — it only needs to implement one method:

```python
async def complete(self, messages, model, temperature, seed) -> str:
    # call your agent, return the response text
```

---

## Providers

| Provider | Set `LLM_PROVIDER=` | Notes |
|---|---|---|
| OpenAI | `openai` | `OPENAI_API_KEY` required |
| Custom endpoint | `openai` + `OPENAI_BASE_URL` | Any OpenAI-compatible server |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` required |
| Ollama (local) | `ollama` | Free, runs locally |
| AWS Bedrock | `bedrock` | IAM credentials required |
| Fake | `fake` | No API calls — for testing Redline itself |

---

## Eval modes

| Mode | How it works |
|---|---|
| **Baseline** | Your agent responds directly — no mitigation |
| **Debate** | Proposer → Critic → Revised output — tests if self-critique improves safety |

Run both and compare results to see if your mitigation strategy actually helps:

```bash
curl "http://localhost:8001/projects/{id}/runs/compare?base_run_id={a}&candidate_run_id={b}" \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/projects` | Create a project |
| `POST` | `/projects/{id}/seed-testcases` | Load JailbreakBench + handcrafted cases |
| `GET` | `/projects/{id}/testcases` | List test cases |
| `POST` | `/projects/{id}/runs` | Start an eval run (async, queued) |
| `GET` | `/projects/{id}/runs/{run_id}` | Run status + summary |
| `GET` | `/projects/{id}/runs/{run_id}/stream` | **SSE** — live status stream |
| `GET` | `/projects/{id}/runs/{run_id}/results` | Per-testcase results |
| `GET` | `/projects/{id}/runs/{run_id}/traces/{tc_id}` | Full trace events |
| `GET` | `/projects/{id}/runs/compare` | Diff two runs |

All endpoints require `X-Admin-Key: <your key>`.

### Example: full eval flow

```bash
# 1. Create a project
curl -X POST http://localhost:8001/projects \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"my-agent-v1"}'

# 2. Seed test cases
curl -X POST http://localhost:8001/projects/{project_id}/seed-testcases \
  -H "X-Admin-Key: $ADMIN_API_KEY"

# 3. List cases and pick some IDs
curl http://localhost:8001/projects/{project_id}/testcases \
  -H "X-Admin-Key: $ADMIN_API_KEY"

# 4. Start a run
curl -X POST http://localhost:8001/projects/{project_id}/runs \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"testcase_ids":["...","..."],"mode":"baseline","seed":7}'

# 5. Get results
curl http://localhost:8001/projects/{project_id}/runs/{run_id}/results \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

---

## Architecture

```
Browser UI (static)
       │
  FastAPI (port 8001)
       │
  ┌────┴─────┐
  │          │
Postgres   Redis + ARQ worker
             │
         LLM Provider ──► your agent / OpenAI / Anthropic / Bedrock / Ollama
                          LLM Judge (LiteLLM + Instructor)
```

- **Async job queue** — ARQ workers, `max_jobs=10`, `job_timeout=600s`
- **SSE streaming** — live run status pushed to the browser
- **LLM-as-judge** — structured scoring via `instructor` + `litellm`
- **JailbreakBench** — 2 behaviors per harm category (~22 real adversarial prompts)

---

## Running tests

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v
# → 17/17 passing (no Docker, no API calls needed)
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Unknown LLM_PROVIDER` | Check `LLM_PROVIDER` value in `.env` — valid: `openai`, `anthropic`, `bedrock`, `ollama`, `fake` |
| Bedrock `AccessDeniedException` | Enable model access in AWS Bedrock console + verify IAM `bedrock:Converse` permission |
| OpenAI 429 | Reduce testcase count, wait 1–2 min, or switch to `fake` provider |
| UI shows 404 | Navigate to `http://localhost:8001/ui/` (trailing slash matters) |
| Docker not found | Start Docker Desktop first |

---

## Roadmap

- [x] LLM-as-judge scoring (instructor + litellm)
- [x] JailbreakBench + StrongREJECT test cases
- [x] Async job queue with SSE streaming
- [x] Run comparison (diff two runs by metric)
- [ ] OpenAI-compatible webhook agent submission (no code changes needed)
- [ ] Multi-tenancy — Clerk auth + per-user isolation
- [ ] Next.js dashboard with heatmaps and real-time SSE

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs are welcome — especially new test cases, provider integrations, and scoring improvements.

---

## License

MIT — see [LICENSE](LICENSE).
