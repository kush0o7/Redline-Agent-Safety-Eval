# redline-evals

**Did your fine-tune just get less safe? Find out in one command.**

```bash
pip install redline-evals
redline compare ollama/llama3.1 ollama/hermes3
```

Redline runs the same adversarial test cases (jailbreaks, prompt injection through tool results, made-up facts, over-refusal and a finance pack) on two versions of a model. It grades each answer and tells you whether the new version is safe to release. A statistics test (McNemar) says whether the change is real or noise.

- **Exit codes for CI:** 0 = pass, 1 = the release fails, 2 = error.
- **Output** (in `./redline-out`): a terminal summary, `report.html`, `results.jsonl` and `summary.json`. Answers to harmful requests are redacted.
- **Grader:** a local Ollama judge if you have a suitable model pulled (`ollama pull qwen2.5:7b`), otherwise keyword rules with a warning. Every report names the grader. Judge accuracy hasn't been measured against human labels yet.
- **Resume:** run the same command again after Ctrl-C or an error. Answers are cached, so re-grading doesn't re-generate them.

Models: `ollama/x`, `openai/x`, `anthropic/x`, `groq/x`, `gemini/x`, any OpenAI-compatible server (`http://host:port/v1#model`), and `fake-safe` / `fake-degraded` (simulated, offline).

```bash
redline compare fake-safe fake-degraded     # offline demo, no models needed
redline scan ollama/llama3.1 --cases 60     # one model against the tier criteria
redline compare A B --judge groq/openai/gpt-oss-120b   # free-tier judge: public test cases only
redline report ./redline-out                # print the summary and rewrite the files
```

The self-hosted server (API, Postgres, worker, UI) is in the `server` extra: `pip install "redline-evals[server]"`.

Docs, methodology and limitations: https://github.com/kush0o7/Redline-Agent-Safety-Eval
