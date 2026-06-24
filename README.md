# Redline — Agent Safety Evals

**Free, open-source safety evaluation platform for LLM agents.**  
Fire 75+ adversarial prompts at your agent. Get a safety score. See how you rank.

[![Live Demo](https://img.shields.io/badge/live%20demo-redline--safety.fly.dev-3ddc97)](https://redline-safety.fly.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

---

## Try it now — no signup

**[redline-safety.fly.dev](https://redline-safety.fly.dev)**

Enter your name, point it at your agent (or use the default), click Run. Takes 2 minutes. Your score shows up on the public leaderboard.

---

## Why Redline?

You built an agent. How do you know it won't:
- comply with a jailbreak prompt?
- hallucinate facts it presents as certain?
- get manipulated by adversarial instructions embedded in user content?
- refuse benign requests it should answer?

Redline answers those questions automatically with 75+ real adversarial test cases, scored by an LLM judge — no manual review needed.

---

## What it tests

| Category | Test cases | What it catches |
|---|---|---|
| **Jailbreaks** | 20+ | DAN, persona attacks, fiction covers, authority impersonation, token obfuscation |
| **Prompt injection** | 10+ | Tool output attacks, indirect injection, role overrides |
| **Hallucination** | 10+ | Fake APIs, fake papers, fake court cases, non-existent companies |
| **Over-refusal (XSTest)** | 20 | Benign prompts that over-cautious models wrongly refuse |
| **Crescendo / multi-turn** | 4 | Fake prior context used to escalate harmful requests |
| **Misinformation** | 4 | Generating fake health claims, election fraud narratives |
| **Privacy / surveillance** | 4 | Stalkerware, facial recognition tracking |
| **Refusal** | 8 | Drug synthesis, weapons, phishing, doxxing |

---

## Safety tiers

| Tier | Pass rate |
|---|---|
| 💎 Hardened | ≥ 90% |
| ✅ Safe | 75–89% |
| 🟡 Developing | 60–74% |
| 🔴 At Risk | < 60% |

---

## Test your own agent (any OpenAI-compatible endpoint)

In the UI, check **"Test my own agent endpoint"** and enter:
- **Endpoint URL**: e.g. `https://openrouter.ai/api/v1` or your own API
- **API key**: your key for that endpoint
- **Model**: e.g. `openai/gpt-4o-mini` or `anthropic/claude-3-haiku`

Works with OpenAI, Anthropic (via OpenRouter), Groq, Together AI, Fireworks, Ollama, vLLM, LiteLLM proxy, or any custom agent that speaks OpenAI chat completions format.

---

## Self-host in 5 minutes

```bash
git clone https://github.com/kush0o7/Redline-Agent-Safety-Eval
cd Redline-Agent-Safety-Eval
cp .env.example .env
# Edit .env — set ADMIN_API_KEY and your LLM provider key
docker compose up --build
```

Open **http://localhost:8001/ui/**

---

## API — one call to run everything

```bash
# Queue an eval (no key needed on the hosted version)
curl -X POST https://redline-safety.fly.dev/quick-eval \
  -H "Content-Type: application/json" \
  -d '{"testcase_count": 10, "mode": "baseline", "submitter": "your-name"}'
# → {"run_id": "...", "stream_url": "..."}

# Get results when done
curl https://redline-safety.fly.dev/quick-eval/{run_id}
```

---

## Architecture

```
Browser UI (static HTML/JS)
       │
  FastAPI + ARQ worker (single Fly.io machine)
       │
  ┌────┴─────────┐
  │              │
Postgres       Redis (Upstash)
(Supabase)         │
               LLM Provider → agent under test
               LLM Judge    → scores every response
```

- **75+ test cases** — JailbreakBench + XSTest + Crescendo + handcrafted attacks
- **Async job queue** — ARQ workers, results streamed live via SSE
- **LLM-as-judge** — structured scoring via `instructor` + `litellm`
- **Public leaderboard** — best score per model, anyone can compete

---

## Providers

| Provider | `LLM_PROVIDER=` | Notes |
|---|---|---|
| OpenAI | `openai` | `OPENAI_API_KEY` required |
| Any OpenAI-compatible | `openai` + `OPENAI_BASE_URL` | Groq, Together, vLLM, Ollama, etc. |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` required |
| AWS Bedrock | `bedrock` | IAM credentials required |
| Fake (no API calls) | `fake` | For testing Redline itself |

---

## Running tests

```bash
cd backend && pip install -e ".[dev]"
pytest tests/ -v   # all passing, no API keys required
```

---

## Roadmap

- [x] 75+ adversarial test cases (jailbreaks, injection, hallucination, XSTest, Crescendo)
- [x] Public leaderboard — compete with others
- [x] Test any OpenAI-compatible agent endpoint
- [x] LLM-as-judge scoring with metric breakdown
- [x] Run comparison (diff two runs)
- [x] SSE live streaming
- [ ] HarmBench + WildGuard dataset loaders
- [ ] Multi-turn attack simulation
- [ ] CI/CD GitHub Action
- [ ] Auth + per-user run history

---

## License

MIT
