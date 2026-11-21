# Show HN draft

v0.2.0 is on PyPI (21 Nov 2026). In a fresh venv, `pip install redline-evals` took 29 s and `redline try` 97 s. HN guidelines: the title starts with "Show HN", it must be something people can try, and don't ask anyone to upvote.

## Title (79 characters)

```
Show HN: Redline – check if your fine-tuned model got less safe before shipping
```

Shorter fallback (62): `Show HN: Redline – safety regression tests for model versions`

## URL

```
https://github.com/kush0o7/Redline-Agent-Safety-Eval
```

## First comment (post it right after submitting)

```
Hi HN. I built Redline because fine-tuning a model can quietly undo its safety training, and there wasn't a simple way to check "is version B less safe than version A?" before shipping it.

It runs the same adversarial tests on both versions (jailbreaks, harmful requests, hidden instructions planted in emails and web pages the agent reads, made-up facts, refusing harmless questions), grades every answer, and prints one plain sentence first: "Don't ship B. It's less safe than A: 9 tests that A passed, B failed." Then each broken test: what we asked, what A did, what B did, why it matters. Exit code 1 if it fails, so it drops into CI.

Try it without installing models: `pip install redline-evals && redline try` asks for a free Groq or OpenRouter key and runs a 10-test before/after check on two hosted models. In a fresh venv the install took 29 seconds and the check 97. With no key at all, `redline compare fake-safe fake-degraded` runs offline on two simulated models.

The first real finding: I compared Llama 3.1 8B with Hermes 3 8B, a popular fine-tune of it, on 40 tests on a free Kaggle GPU. Hermes followed a hidden instruction in a document and sent a secret token to an attacker's URL with a real tool call, and it wrote a keylogger and a money-mule job ad that Llama refused. Pass rate 87.5% -> 72.5% with an AI grader.

The finding that surprised me more was about grading. With keyword rules the drop was 87.5% -> 55% and clearly not chance (p = 0.001). With an AI grader it was 87.5% -> 72.5% and could be chance (p = 0.146). Both said don't ship, but the "how big and is it real" part depended on who graded. So every report names its grader and says how far to trust it, and hidden-instruction tests are graded in code from the tool calls the model actually made, not by a model.

Honest limits:
- The grader's accuracy hasn't been measured against human labels yet. That's next.
- 40 tests is enough for the overall change, not for per-area claims.
- Single-turn attacks only; multi-turn (Crescendo-style) is out of scope for now.
- "Runs on your machine" works with a local model and grader, but zero network calls isn't enforced yet.
- Free hosted tiers may keep your prompts, so `redline try` is for demos, not private data.

What I'd love feedback on: does the one-sentence verdict read right to you, which tests are missing for the models you ship, and whether you'd trust an AI grader here at all. MIT licensed.
```
