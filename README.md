# Redline — Agent Safety Evals + Debate Mitigation

Redline is a production‑grade, security‑focused evaluation harness for LLM agents. It generates adversarial test cases, runs baseline vs debate mitigation modes, scores safety/reliability metrics, and stores full runs + traces in Postgres behind a FastAPI API and a minimal UI.

---

## TL;DR
- **What it is:** An evaluation platform to measure LLM safety and reliability.
- **What it does:** Runs adversarial testcases against an agent, scores metrics, stores runs/traces.
- **How it helps:** Shows where a model follows safety policy, avoids hallucinations, and behaves responsibly.

---

## Features
- Deterministic, reproducible evaluation harness
- Baseline and debate modes (Proposer → Critic → Revision)
- Safety metrics: policy compliance, hallucination, overconfidence, refusal correctness
- Secure‑by‑default (no unsafe tools, prompt‑injection detection)
- Job queue via Redis + RQ
- Postgres persistence for runs, results, and traces
- Minimal web UI for fast usage

---

## Threat model & security decisions
- **No unsafe tools**: the agent cannot access filesystem, shell, or network.
- **Safe tools only**: `safe_notes_write`, `safe_notes_read` (validated JSON schema).
- **Prompt‑injection defense**: tool outputs are scanned for common injection patterns and redacted in traces if found.
- **API auth**: all endpoints require `X-Admin-Key` with `ADMIN_API_KEY` env var.
- **Rate limiting**: simple per‑IP in‑memory limiter.
- **Secrets**: loaded from environment only; logs redact common key patterns.

---

## Architecture (high level)
```
UI (static) → FastAPI → Postgres
                 ↓
              Redis (RQ)
                 ↓
             Worker
                 ↓
            LLM Provider
```

---

## Quickstart (local)
1) Copy `.env.example` to `.env` and set:
   - `ADMIN_API_KEY`
   - `LLM_PROVIDER`
   - `DEFAULT_MODEL`
2) Start services:

```bash
docker-compose up --build
```

**UI:** `http://localhost:8001/ui/`

---

## Providers

### Fake (free, for quick testing)
```
LLM_PROVIDER=fake
DEV_FAKE_PROVIDER=true
DEFAULT_MODEL=fake
```

### OpenAI
```
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key
DEFAULT_MODEL=gpt-4o-mini
```

### Anthropic
```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key
DEFAULT_MODEL=claude-3-5-sonnet-20240620
```

### Local model (Ollama)
1) Install and run Ollama locally.
2) Set:
```
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
DEFAULT_MODEL=llama3.1
```

---

## Using the UI (simple steps)
1) Paste **Admin Key** (from `.env`)
2) Create a project
3) Seed testcases
4) List testcases
5) Select 3–5 testcase IDs
6) Create run
7) Get summary / results / trace

**One‑click demo** is available in the UI.

---

## API usage (curl)

### Create project
```bash
curl -X POST http://localhost:8001/projects \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"demo"}'
```

### Seed testcases
```bash
curl -X POST http://localhost:8001/projects/{project_id}/seed-testcases \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

### List testcases
```bash
curl http://localhost:8001/projects/{project_id}/testcases \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

### Create run
```bash
curl -X POST http://localhost:8001/projects/{project_id}/runs \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"testcase_ids":["..."],"mode":"baseline","llm_model":"gpt-4o-mini","seed":7}'
```

### Run summary
```bash
curl http://localhost:8001/projects/{project_id}/runs/{run_id} \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

### Results
```bash
curl http://localhost:8001/projects/{project_id}/runs/{run_id}/results \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

### Trace (per testcase)
```bash
curl http://localhost:8001/projects/{project_id}/runs/{run_id}/traces/{testcase_id} \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

---

## Metrics explained (plain language)
- **Policy compliance**: Did the model refuse unsafe requests when it should?
- **Hallucination control**: Did it avoid making up facts and say “I don’t know” when needed?
- **Overconfidence**: Did it avoid high confidence when uncertain?
- **Refusal correctness**: Was refusal behavior appropriate and consistent?

---

## Add new testcases
- Add entries in `backend/app/evals/testcases.py`
- Or generate cases in `backend/app/evals/generators.py`
- Then call `/projects/{id}/seed-testcases`

---

## Run tests
```bash
cd backend
pytest
```

---

## Troubleshooting
- **Docker daemon not running**: start Docker Desktop, then re‑run compose.
- **OpenAI 429**: reduce testcase count, wait 1–2 minutes, or use fake provider.
- **UI shows 404**: ensure you are on `http://localhost:8001/ui/`.

---


