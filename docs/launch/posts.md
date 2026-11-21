# Posts, one per place (ready to paste)

These go with [marketing-plan.md](marketing-plan.md). Show HN, r/LocalLLaMA, LinkedIn #1 and the X thread are in their own files. Each post leads with a finding and links once. Before posting in a community, re-read its rules and adjust.

Repo: https://github.com/kush0o7/Redline-Agent-Safety-Eval

---

## r/LLMDevs (Mon 23 Nov, 9–11 am MST)

Flair: whatever the sidebar uses for tools/resources.

Title:
```
We swapped Llama 3.1 8B for a popular fine-tune of it. The fine-tune sent a secret token to an attacker URL via a tool call. A before/after check you can drop into CI
```

Body:
```
If you swap or fine-tune the model behind an agent, the old safety behaviour doesn't come with it automatically.

I ran the same 40 safety tests on Llama 3.1 8B and Hermes 3 8B (a fine-tune of it). Hermes read a document with a hidden instruction and made a real http_request tool call that sent a deploy token to the attacker's URL. Llama ignored the instruction. Hermes also wrote a keylogger and a money-mule ad that Llama refused.

I turned that check into a CLI:

    pip install redline-evals
    redline compare ollama/current-model ollama/new-model

- Same cases on both versions, so the diff is per test, not two unrelated scores.
- Hidden-instruction cases are graded in code from the tool calls the model actually made.
- First line is plain English ("Don't ship B. It's less safe than A: ..."). Exit code 1 when it fails, so it works as a CI gate.
- Works with Ollama, any OpenAI-compatible endpoint, Anthropic, Bedrock.

Limits: the AI grader isn't validated against human labels yet, single-turn attacks only, and 40 tests catches the overall change, not small per-area ones.

https://github.com/kush0o7/Redline-Agent-Safety-Eval

How do you check a model swap today, if at all?
```

---

## Hugging Face Posts (Sat 21 Nov, 10 am MST)

Use the first finding post from [content-engine.md](content-engine.md) (gpt-oss-20b vs gpt-oss-safeguard-20b). HF readers care about specific models.

---

## MLOps Community Slack (Wed 25 Nov), self-promo / tools channel only

```
Hi all. I've been working on a release check for model swaps and fine-tunes, and I'd like feedback from people who run model releases.

The finding that started it: same 40 safety tests on Llama 3.1 8B and Hermes 3 8B (a fine-tune of it). The fine-tune followed a hidden instruction in a document and leaked a token through a real tool call. The base didn't.

Redline runs the same cases on both versions and prints a verdict plus the tests that broke. Exit code 1 on fail, for CI:
  pip install redline-evals && redline compare ollama/v1 ollama/v2

Open source (MIT): https://github.com/kush0o7/Redline-Agent-Safety-Eval

Question for the room: where would you put this, as a pre-release gate or a nightly job?
```

---

## Hugging Face Discord `#i-made-this` (Sat 21 Nov, afternoon)

```
Made a small CLI that checks whether a fine-tune got less safe than its base: same tests on both, every answer graded, one-line verdict. First real result: Hermes 3 8B leaked a token through a tool call that Llama 3.1 8B refused to make.
pip install redline-evals && redline try   (free Groq/OpenRouter key, ~2 min)
https://github.com/kush0o7/Redline-Agent-Safety-Eval
```

---

## Unsloth Discord showcase (Sat 28 Nov)

```
For anyone fine-tuning: fine-tuning can quietly undo safety training, even on harmless data (Qi et al. 2023). I built a check you run before you share a fine-tune:

  pip install redline-evals
  redline compare ollama/your-base ollama/your-finetune

Same tests on both, and it lists every test the fine-tune newly fails. Example: Hermes 3 8B vs Llama 3.1 8B, 35/40 → 29/40 with an AI grader, including a leaked token via tool call.
https://github.com/kush0o7/Redline-Agent-Safety-Eval
```


---

## LinkedIn #2, "how I built it" (Tue 1 Dec, 8–10 am MST)

Link in the first comment again.

```
Last week I shared that a fine-tuned AI model leaked a secret that its original refused to. A few people asked how the test works, so here's the short version.

1. Same questions, both versions. If you test two versions on different questions, you can't tell what changed. Redline saves the exact list and replays it.

2. Some tests can't be faked by a good-sounding answer. For "hidden instruction in a document" tests, we don't ask an AI whether the model behaved. We check the actions it actually took, like "did it call the web tool with the secret in the address?"

3. Say how sure you are. With 40 tests, a 6-point drop can be luck. Redline runs a standard statistical test (McNemar's) and says "could be chance" when it is.

4. Say who graded. Keyword rules and an AI grader gave different answers on the same data. So every report names the grader and how far to trust it.

5. Lead with one sentence. The first line is the decision: "Don't ship B. It's less safe than A." The details come after.

What I got wrong at first: my first real run failed on a free API key because of a missing security certificate on macOS. Testing the install on a clean machine, not my laptop, caught it.

It's free and open source. Next up: measuring how often the AI grader agrees with human reviewers.
```

First comment:
```
Code and the full results: https://github.com/kush0o7/Redline-Agent-Safety-Eval
```

---

## r/MachineLearning `[P]` (Mon 30 Nov), only if the rules allow project posts outside the self-promo thread

Title:
```
[P] Same 40 safety tests, same two models, two graders: one said p = 0.001, the other p = 0.146
```

Body:
```
I compared Llama 3.1 8B Instruct with Hermes 3 8B (a fine-tune of it) on 40 identical single-turn safety cases: jailbreaks, harmful requests, injection planted in tool results, hallucination and over-refusal.

- Keyword-rule grader: 87.5% → 55%, McNemar exact p = 0.001.
- LLM grader (gpt-oss-120b): 87.5% → 72.5%, p = 0.146.

Both runs flagged the release, and the injection cases (graded in code from the tool calls) agreed: Hermes exfiltrated a token via http_request and Llama didn't. But the effect size, and whether it's distinguishable from noise, depended on the grader. Answers were regenerated each run, so part of the gap is sampling variance, not only the grader.

What I take from it: report the grader, its temperature and the significance test with every safety comparison, and grade what you can in code. The tool (MIT) does this by default and puts it in every report: https://github.com/kush0o7/Redline-Agent-Safety-Eval

Open problems I'd like input on: the grader hasn't been validated against human labels (planned: agreement plus Cohen's kappa on a labelled set), and 40 cases gives little power per category. What's the smallest labelled set you'd trust for judge validation?
```

---

## LessWrong (Thu 3 Dec), a research-style personal blogpost

Title:
```
Who grades a safety eval can change its conclusion: a small worked example
```

Body:
```
Summary: on the same 40 cases and the same two models, a keyword grader and an LLM grader agreed on the direction (the fine-tune is less safe) but disagreed on the size and on whether the change was distinguishable from noise. Cases graded in code from tool calls were the most stable part of the result.

Setup. Llama 3.1 8B Instruct versus Hermes 3 8B, a fine-tune of the same base. 40 single-turn cases sampled across four scoring categories: harmful compliance, prompt injection via tool results, hallucination and over-refusal. Both models ran on Ollama on a free Kaggle T4. Same cases, same seed.

Results.
- Keyword grader: 35/40 → 22/40 (87.5% → 55%), McNemar exact p = 0.001.
- LLM grader (gpt-oss-120b): 35/40 → 29/40 (87.5% → 72.5%), p = 0.146.
- Code-graded injection cases: Hermes made an http_request call carrying a deploy token to the attacker's URL, and leaked data via a markdown image. Llama did neither.
- Hermes also complied with requests for a keylogger, a money-mule recruitment ad and pump-and-dump posts that Llama refused.

Caveats. Answers were regenerated between grader runs, so the gap mixes grader disagreement and sampling variance. Neither grader is validated against human labels. 40 cases is underpowered for per-category claims. Single-turn only. Hermes is built to be steerable, so "less safe" here means "follows more instructions", which some users want.

Why it matters. Fine-tuning erodes safety behaviour (Qi et al. 2023), and LLM judges are known to be manipulable. If release decisions rest on a judged pass rate, the grader is part of the measurement and should be reported like one: which model, what temperature, the significance test, and which cases were decided in code.

I built this into an open-source tool (Redline, MIT) so every report includes those things: https://github.com/kush0o7/Redline-Agent-Safety-Eval. Next I'm building a labelled set to measure grader agreement. Suggestions on its design are welcome.
```

Checked: 55% of 40 = 22; Qi et al. 2023 matches `docs/research-notes.md`.

---

## OWASP GenAI Security Project Slack (Thu 3 Dec): ask, don't pitch

```
Hi, a question about the solutions landscape. I maintain an open-source tool (Redline, MIT) that tests indirect prompt injection by planting instructions in tool results and grading the model's actual tool calls in code (e.g. "did it call http_request with the secret in the URL?"). It's built around comparing two versions of a model or agent.

Is there a process for suggesting a tool for the LLM security solutions landscape, or someone I should ask? Happy to share findings if useful: a popular Llama fine-tune leaked a token this way while its base didn't.
```

---

## Latent Space Discord (Fri 4 Dec), share-your-work channel

```
Small eval result that surprised me: same 40 safety tests, same two models (Llama 3.1 8B vs its fine-tune Hermes 3 8B). Keyword grader: 87.5% → 55%, p = 0.001. LLM grader: 87.5% → 72.5%, p = 0.146. Same verdict, very different confidence. I now report the grader and the significance test with every comparison. Tool + write-up: https://github.com/kush0o7/Redline-Agent-Safety-Eval
```

---

## Newsletters (only ones that take submissions)

**console.dev** (email, per their site):
```
Redline: an open-source CLI that checks whether a new version of an AI model got less safe than the old one. It runs the same adversarial tests on both versions (jailbreaks, harmful requests, prompt injection planted in tool results), grades every answer, and prints a one-line verdict with a CI exit code. `pip install redline-evals && redline try` runs a 2-minute demo with a free Groq or OpenRouter key. MIT. https://github.com/kush0o7/Redline-Agent-Safety-Eval
```

**PyCoder's Weekly** (pycoders.com/submissions):
```
Redline: safety regression tests for AI model versions, in Python. Runs the same test set on two model versions, grades with an LLM or keyword rules, and uses McNemar's test to say whether the change could be chance. pip install redline-evals.
```

**Changelog News** (changelog.com/news/submit):
```
Title: Redline checks if your fine-tuned model got less safe before you ship it
Link: https://github.com/kush0o7/Redline-Agent-Safety-Eval
Note: Open-source CLI. Its first real result: a popular Llama 3.1 fine-tune leaked a secret through a tool call that the base model refused to make.
```
