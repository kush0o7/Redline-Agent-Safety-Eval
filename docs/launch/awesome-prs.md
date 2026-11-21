# Awesome-list PRs (drafts, nothing opened yet)

Open each one only after a yes. One PR per list, following its CONTRIBUTING file. Every PR says the author is submitting their own project. Checked 21 Nov 2026: all four lists have merged outside PRs recently.

## 1. Vvkmnn/awesome-ai-eval

- Section: **Tools → Adversarial**, alphabetical, so it goes after PyRIT (last line).
- Rules: one line, 20 words or fewer, a capital letter at the start and a period at the end, no badges or hype words, one entry per PR, title `Add Name`, run `pnpm install && pnpm lint`.

Line (17 words):
```
- [Redline](https://github.com/kush0o7/Redline-Agent-Safety-Eval) - CLI that runs the same safety tests on two model versions and reports regressions, including code-graded tool injection.
```

Title: `Add Redline`

Body:
```
Adds Redline to Tools → Adversarial (alphabetical, after PyRIT).

Redline runs the same adversarial test set (jailbreaks, harmful requests, prompt injection planted in tool results, hallucination, over-refusal) on two versions of a model and reports which tests regressed, with McNemar's test for whether the change is noise. Injection cases are graded in code from the tool calls the model made.

- MIT licensed, on PyPI as `redline-evals`, actively maintained.
- Disclosure: I'm the author.
- Ran `pnpm lint` locally.
```

## 2. AbdelStark/awesome-ai-safety

- Section: **Evaluation and red teaming → Red teaming**, after promptfoo (tools come before the **Research.** entries).
- Rules: cite the source for the description, give the license and a reproduction example, declare authorship, state limits, no "best/production-ready" claims, run `scripts/check.py` and `mkdocs build --strict`.

Line:
```
- [Redline](https://github.com/kush0o7/Redline-Agent-Safety-Eval) - Runs one adversarial test set on two model versions and reports safety regressions with a significance test; single-turn only, grader accuracy not yet measured.
```

Title: `Add Redline to Red teaming`

Body:
```
Adds Redline under Evaluation and red teaming → Red teaming, after promptfoo.

Gap it fills: the listed tools scan one model. Redline compares two versions of the same model (for example a base and its fine-tune) on the exact same cases, and reports per-test regressions plus McNemar's exact test for whether the change could be noise.

- Source for the description: README "How it works" and "Current limitations" sections.
- License: MIT (LICENSE in the repo). Bundled JailbreakBench behaviors are MIT.
- Reproduction, offline with no keys: `pip install redline-evals && redline compare fake-safe fake-degraded` (exits 1 with "Don't ship fake-degraded").
- Limits stated in the entry: single-turn attacks only; the grader has not been validated against human labels yet.
- Disclosure: I'm the author, with no employer or funding behind it.
- Ran the local checks (unittest, scripts/check.py, mkdocs build --strict). [run these before opening]
```

## 3. ottosulin/awesome-ai-security

- Section: **Attack Techniques & Red Teaming → LLM & GenAI Red Teaming**, added at the end (the list isn't alphabetical).
- Format: `* [name](url) - _description_`. No CONTRIBUTING rules beyond the README.

Line:
```
* [Redline](https://github.com/kush0o7/Redline-Agent-Safety-Eval) - _Safety regression tests between two model versions: jailbreaks, harmful requests and tool-result prompt injection graded from real tool calls, with a plain-English release verdict._
```

Title: `Add Redline (safety regression tests between model versions)`

Body:
```
Adds Redline to LLM & GenAI Red Teaming.

It runs the same adversarial cases on two versions of a model or agent, for example a base and its fine-tune, and reports which tests regressed. Injection cases plant instructions in tool results and are graded from the tool calls the model actually makes. MIT, on PyPI as redline-evals.

Disclosure: I'm the author.
```

## 4. tensorchord/Awesome-LLMOps

- Section: **Security → Frameworks for LLM security** table, in its alphabetical slot (between PrivAiTe and sayfirst).
- Format: a three-column table row with a stars badge, like the rows around it.

Row:
```
| [Redline](https://github.com/kush0o7/Redline-Agent-Safety-Eval) | Safety regression tests for model releases: runs the same adversarial cases on two versions, grades each answer, exits 1 in CI when the new version is less safe. | ![GitHub Badge](https://img.shields.io/github/stars/kush0o7/Redline-Agent-Safety-Eval.svg?style=flat-square) |
```

Title: `Add Redline to Frameworks for LLM security`

Body:
```
Adds Redline to Security → Frameworks for LLM security, in alphabetical order.

It's a CLI plus an optional self-hosted server that compares two versions of a model on the same adversarial cases (jailbreaks, harmful requests, prompt injection in tool results) and gives a release verdict with a CI exit code. MIT, on PyPI as redline-evals.

Disclosure: I'm the author.
```

## Optional 5th: wearetyomsmnv/Awesome-LLMSecOps

It's a weaker fit (mostly security-by-design and ops resources). Skip it unless the first four go well.
