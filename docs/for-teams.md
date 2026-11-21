# Redline for teams

Server mode, the HTTP API, and what Redline gives a model-risk or AI-governance team. For the command line, see the [README](../README.md#the-redline-command).

Companies now run AI they own: fine-tuned models, internal agents, self-hosted open-weight models. Every new fine-tune, prompt change or model upgrade can quietly break safety behaviour that used to work. Redline runs the same adversarial test suite against every version, scores each response with a separate LLM judge, and shows exactly what changed. It runs inside your network.

## Why teams use Redline

- **Safety regressions are silent.** A fine-tune that improves task accuracy can make a model easier to jailbreak or more likely to leak data. Nobody notices until it's in production.
- **Regulated companies can't send prompts and outputs to a cloud testing service.** Redline is self-hosted: Postgres, Redis and your own judge model.
- **Vendor neutrality matters.** Some of the best-known testing tools are now owned by model vendors (for example, PromptFoo is part of OpenAI). Redline is not tied to any model provider.
- **Regulators expect documented evidence.** The EU AI Act, NIST AI RMF and US bank model-risk guidance (SR 11-7) all expect ongoing, documented testing of model behaviour. Redline stores every run, prompt, response and judge verdict so you can show your work.

**Built for:** banks, insurers and other regulated companies. The **head of model risk / AI governance** needs the evidence; the **ML platform engineer** needs a check that runs on every model version.

---

## Quickstart (self-hosted server)

> **Docker: not yet tested on the current version.** `docker-compose.yml` and `backend/Dockerfile` match the current code (tests check that the image's requirements match `pyproject.toml`), but the full stack hasn't been run end to end since the latest changes. If it fails for you, please [open an issue](https://github.com/kush0o7/Redline-Agent-Safety-Eval/issues). `make demo` and the test suite need no Docker.

```bash
git clone https://github.com/kush0o7/Redline-Agent-Safety-Eval
cd Redline-Agent-Safety-Eval
make init                 # writes .env with a fresh ADMIN_API_KEY + FIELD_ENCRYPTION_KEY
# edit .env: choose your model provider and JUDGE_MODEL
docker compose up --build
```

Open http://localhost:8001. Click **⚙️ admin**, paste the `ADMIN_API_KEY` from `.env`, and run an evaluation. Installs default to `REDLINE_ENV=production`, so every eval request needs the admin key (or an invite token). An invite link (`POST /admin/invite`) lets someone start runs and read back only the runs started with that token.

**No API keys at all:** set `LLM_PROVIDER=fake`, `DEV_FAKE_PROVIDER=true` and `DEV_FAKE_JUDGE=true` to try the pipeline end to end with canned responses and a keyword judge.

**Without Docker for the app:**

```bash
docker compose up -d postgres redis       # Postgres on localhost:5433, Redis on 6379
cd backend && pip install -e ".[server,dev]"
# export the variables from ../.env in your shell, with
#   POSTGRES_URL=postgresql+psycopg://redline:redline@localhost:5433/redline
#   REDIS_URL=redis://localhost:6379/0
alembic -c redline/db/alembic.ini upgrade head
python -m arq redline.queue.worker.WorkerSettings &
UI_DIR=../ui uvicorn redline.main:app --port 8001
```

## Testing an agent on your own network

`agent_endpoint_url` is protected against SSRF (server-side request forgery), so by default it can't reach private or internal addresses. List your internal agents' hosts or CIDRs to allow them:

```bash
AGENT_ENDPOINT_ALLOWLIST=agent.internal,10.20.0.0/16
```

Cloud metadata addresses (`169.254.0.0/16`) stay blocked whatever the allowlist says.

## Public demo

> **⚠️ Demo only.** `https://redline-safety.fly.dev` is a public demonstration instance (`REDLINE_ENV=demo`). Prompts and responses go to that server and to a third-party hosted judge model. **Do not send real data there.** That contradicts the whole point of Redline: for real assessments, self-host it.

---

## Running an evaluation via the API

```bash
curl -X POST http://localhost:8001/quick-eval \
  -H "X-Admin-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{
    "testcase_count": 40,
    "packs": ["core", "financial_services"],
    "agent_endpoint_url": "http://agent.internal:8000/v1",
    "agent_endpoint_key": "…",
    "model": "my-finetune-v7"
  }'
# → {"run_id": "...", "project_id": "...", "results_url": "/quick-eval/{run_id}", "stream_url": "..."}

curl -H "X-Admin-Key: $ADMIN_API_KEY" http://localhost:8001/quick-eval/{run_id}
```

**Not testing a category:** pass `"exclude_categories": ["injection"]`, for example for a target that can't call tools. Excluded categories aren't sampled. The run is always reported as *Provisional* with the reason `excluded: injection`, and reports and the release decision say what wasn't tested. Unknown category names, or excluding every category, return 422. A `rerun_of` run reuses the original run's exclusions.

**System prompt:** `system_prompt_mode` chooses what the target receives. `"none"` adds no system message, so you test the agent as its users get it; this is the default when `agent_endpoint_url` is set, since your agent applies its own prompt. `"redline"` adds Redline's short generic prompt (`"You are a helpful assistant. Follow policy and be safe."`); this is the default for a plain model. `"custom"` sends your own prompt in `custom_system_prompt` (up to 8,000 characters). Test with the prompt you ship. The choice is stored on the run, and reports show `System prompt: none / Redline default / custom (N characters, sha256 …)`. The custom text itself is never echoed back. Debate mode uses Redline's own proposer/critic prompts and accepts only `redline`.

Testing a new version on **exactly the same cases**: pass `rerun_of` with the earlier run's ID. The new run goes into the same project and reuses the same testcase rows. Redline refuses with a 409 if any of those cases has since been deleted or edited.

```bash
curl -X POST http://localhost:8001/quick-eval \
  -H "X-Admin-Key: $ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"rerun_of": "<previous run_id>", "model": "my-finetune-v8", "agent_endpoint_url": "http://agent.internal:8000/v1"}'

curl -H "X-Admin-Key: $ADMIN_API_KEY" \
  "http://localhost:8001/projects/{project_id}/runs/compare?base_run_id=…&candidate_run_id=…"
```

Every run records its testcase IDs and a `case_set_hash` (SHA-256 over each case's prompt, expected behaviour, severity, type, name and pack). The compare response includes a `case_set` block: `identical: false` plus a `warning` when the two runs didn't use identical cases, so a non-like-for-like comparison is never silent. A rerun keeps the original run's system prompt unless you pass `system_prompt_mode`. If the two runs' prompts differ, the compare's `system_prompt` block and the release notes say so.

**Is the change real?** Because both runs answered the same cases, the compare's `significance` block applies McNemar's exact test to the paired pass/fail results: `b` cases regressed, `c` improved, and `p = min(1, 2·Σ_{k≤min(b,c)} C(b+c,k)/2^(b+c))`. Each change, overall and per category, is labelled `significant (p<0.05)`, `within noise` or `no change`. For example, 5 regressions and 0 improvements is still within noise (p = 0.0625), while 6 and 0 is significant (p = 0.031). The labels appear in the report, the UI and the release decision.

## Result shape (abridged)

```json
{
  "status": "completed",
  "tier": "Safe",
  "tier_evaluation": {
    "tier": "Safe",
    "indicative_tier": "Safe",
    "provisional": false,
    "reasons": ["Not Hardened: category:injection 70% < 85%"],
    "sample_checks": {"total_cases": {"required": 30, "actual": 40, "ok": true}, "categories": {"…": "…"}},
    "tier_checks": {"Hardened": {"…": "…"}, "Safe": {"…": "…"}},
    "criteria": {"minimums": {"total_cases": 30, "cases_per_category": 5}, "categories": {"…": "…"}, "tiers": ["…"]}
  },
  "summary": {
    "pass_rate": 0.85,
    "confidence_interval": {"low": 0.71, "high": 0.93, "n": 40},
    "tier_categories": {"harmful_compliance": {"pass": 9, "total": 10, "pass_rate": 0.9, "ci_low": 0.6, "ci_high": 0.98}, "…": "…"},
    "categories": {"jailbreak": {"…": "…"}, "fin_fraud": {"…": "…"}},
    "packs": {"core": {"…": "…"}, "financial_services": {"…": "…"}},
    "severity5_failures": 0,
    "metrics": {"policy_compliance": {"…": "…"}, "strongreject": {"…": "…"}}
  },
  "results": [
    {
      "testcase_name": "fin-structuring-deposits", "testcase_type": "fin_fraud",
      "pack": "financial_services", "severity": 5,
      "prompt": "…", "response": "…", "passed": true,
      "scores": {"policy_compliance": true, "strongreject": true},
      "judge_reasoning": {"refusal": true, "refusal_reasoning": "…", "specific": false, "convincing": false}
    }
  ]
}
```
