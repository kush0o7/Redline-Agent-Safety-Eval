# Research notes

The research behind Redline's design choices: what each paper found, exactly which figures we rely on, and what Redline does about it. Citations with full references are also on the [methodology page](../ui/methodology.html).

**How each claim was checked** is stated per paper, because it matters:
- *paper* means the figures were taken from the paper's own tables or sections, with references.
- *abstract / secondary* means the claim matches the abstract or reputable summaries, but nobody has re-derived it from the paper's tables yet.

If you quote a figure, quote its metric too (see Crescendo below for why).

---

## Fine-tuning erodes safety, even on benign data

### Qi et al. 2023, *Fine-tuning Aligned Language Models Compromises Safety, Even When Users Do Not Intend To!*
arXiv:2310.03693 (ICLR 2024). Checked against: abstract / secondary.

- Fine-tuning aligned models erodes their safety. This holds with adversarial examples, with identity-shifting data, and even with purely benign datasets.
- Benign fine-tuning on Alpaca raised GPT-3.5 Turbo's harmfulness rate from **5.5% to 31.8%**.

**What Redline does:** every fine-tune is a new version that needs re-testing. This is why Redline is built around version-to-version comparison on the exact same cases (`rerun_of`, `/compare`), not one-off scans.

### Guan et al. 2025, *Benign Samples Matter! Fine-tuning On Outlier Benign Samples Severely Breaks Safety*
arXiv:2505.06843 (ICML 2025). Code: github.com/GuanZihan/Benign-Samples-Matter. Checked against: abstract / secondary.

- Fine-tuning on about **100 selected (outlier) benign samples** severely breaks safety alignment, and common defenses fail to stop it.

**What Redline does:** even small, innocent-looking fine-tunes need a regression check. A planned experiment will reproduce this on a small open model (LoRA on Alpaca) and show the regression in a Redline comparison report.

---

## LLM judges are not reliable on adversarial content

### Schwinn et al. 2026, *A Coin Flip for Safety: LLM Judges Fail to Reliably Measure Adversarial Robustness*
arXiv:2603.06594. Checked against: abstract.

- LLM safety judges can fall to near-chance accuracy on adversarial outputs under distribution shift, and attacks inflate success rates by exploiting judge weaknesses.
- **Scope:** the paper studies jailbreak and red-teaming outputs, not prompt injection specifically.

### *Safer or Luckier? LLMs as Safety Evaluators Are Not Robust to Artifacts*
arXiv:2503.09347 (ACL 2025). Checked against: abstract / secondary.

- Judges are swayed by artifacts: an apologetic prefix alone shifted judge preferences by **up to 98%**.
- Judges are inconsistent across runs, and agreement with humans is not the same as robustness.

**What Redline does:**
- Prompt-injection cases are graded **in code**, on what the agent did: a tool call with the attacker's arguments, or the attacker's marker in the output. Every result records `decided_by` (`code`, `judge` or `heuristic`).
- The judge is only a fallback for cases without code checks.
- Measuring the judge against a hand-labelled adversarial set, including artifact tests such as an "I'm sorry, but…" prefix on compliant answers and repeated runs, is on the roadmap. Until then, reports say the judge's accuracy hasn't been measured.

---

## Prompt-injection benchmarks need care

### Debenedetti et al. 2024, *AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents*
arXiv:2406.13352 (NeurIPS 2024 Datasets & Benchmarks). Repo: github.com/ethz-spylab/agentdojo (MIT licence). Checked against: the repository (licence and banking-suite code).

- AgentDojo provides tool-using agent suites (banking, Slack, travel, workspace) with user tasks and injection tasks.
- Grading is **deterministic and state-based**: it checks the environment after the run, e.g. a transfer to an attacker IBAN or a changed password.
- The banking suite has 11 tools and 9 injection tasks.

**What Redline does:** injection cases follow the same principle (deterministic, not judge-graded). Redline is stricter in one respect: it fails a case when the agent *attempts* the attacker's action, rather than only when the end state changed. Importing the AgentDojo banking suite is a candidate pack, to be spot-checked first: one injection task's check appears inverted.

### *Indirect Prompt Injections: Are Firewalls All You Need, or Stronger Benchmarks?*
arXiv:2510.05244 (NeurIPS 2025). Checked against: abstract / secondary.

- Public agent prompt-injection benchmarks contain flawed success metrics and implementation bugs.
- Simple tool-input/output firewalls look near-perfect on them, which says more about the benchmarks than the defenses.

**What Redline does:**
- Every injection case is hand-built.
- Tests prove that a compromised agent (`fake-vulnerable`) fails every case and a safe agent passes every case.
- The 30 cases spread eight attacker goals across six data sources, so resisting one phrasing in one place doesn't earn credit for the whole category.
- Imported benchmarks are spot-checked before use.

---

## Multi-turn attacks

### Russinovich, Salem & Eldan, *Great, Now Write an Article About That: The Crescendo Multi-Turn LLM Jailbreak Attack*
arXiv:2404.01833, **v3 (26 Feb 2025)**, USENIX Security 2025. Checked against: **paper** (Table 4, §5).

- Conversations that start benign and escalate gradually jailbreak frontier models.
- The automated version, Crescendomation, is open-sourced as part of Microsoft's PyRIT (abstract footnote; §7).

**Exact figures:** Table 4 (§5.1.1, §5.2). These cover the 50-task AdvBench subset (§5.1.4), with Crescendomation run 10 times per task (§5.1.5, §5.1.7).

| Model | **Average** attack success rate | **Binary** attack success rate |
|---|---|---|
| GPT-4 | 56.2% | 98.0% (49 of 50 tasks) |
| Gemini-Pro | 82.6% | 100.0% (50 of 50 tasks) |

- *Average* is the per-run success rate, averaged over tasks.
- *Binary* counts a task as jailbroken if at least one of its runs succeeded (§5.2).
- Both numbers are correct, but they measure different things, so always say which one you're quoting. ("Crescendo: 56% on GPT-4" and "Crescendo: 98% on GPT-4" are both true.)
- Also reported:
  - HarmBench (100 tasks, GPT-4, Fig. 9): average 63.2% vs 38.9% for many-shot jailbreaking, binary 91% vs 70%.
  - The "Denial" task reached 100% on every model tested (§5.3.1).
- Don't quote the abstract's "29–61% / 49–71% higher performance" ranges. They're relative, the paper doesn't define how they were computed, and they don't follow directly from Table 4.

**What Redline does:** today's cases simulate only the final escalated turn, with injected prior context. Full multi-turn attacks are on the roadmap, and the methodology page says so.

---

## Also cited on the methodology page

HarmBench, WildGuard / WildTeaming, StrongREJECT, XSTest, JailbreakBench, and Wilson (1927) for the confidence intervals. See the [methodology page](../ui/methodology.html) for references and how each is used.
