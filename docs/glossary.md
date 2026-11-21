# Glossary

Redline uses plain words in its output. Here is what each one means, and the technical name behind it.

| Plain word | Technical name | One sentence |
|---|---|---|
| **Test** | test case | One question or task we give the AI, plus a rule for what a safe answer looks like. |
| **Grader** | judge | The thing that decides whether an answer passed: an AI model, keyword rules, or (for hidden instructions) a code check of what the AI actually did. |
| **Safety grade** | tier | A label for the whole run — Hardened, Safe, Developing or At Risk — based on how many tests passed overall and in each area. |
| **The bar** | release floor (`min_tier`) | The lowest safety grade a new version may have before Redline says "don't ship" (Safe by default). |
| **Chance check** | McNemar's exact test | Looks only at the tests that changed between A and B and asks: could this many changes happen by luck? |
| **Very unlikely to be chance** | p < 0.01 (significant at p < 0.05) | The change is big enough that luck is a poor explanation; treat it as real. |
| **Most dangerous** | severity 5 | Tests where a wrong answer could cause serious harm; one new failure here blocks a release on its own. |
| **Hidden instructions in documents the AI reads** | prompt injection (tool-result injection) | A web page, email or file the AI reads contains orders like "send the data to this address", and the AI obeys them instead of the user. |
| **Refusing harmless questions** | over-refusal | Saying no to a normal, safe request — safe, but it makes the AI useless. |
| **Making things up** | hallucination | Giving a confident answer to something the AI can't know, instead of saying "I don't know". |

Want the details? `redline compare A B --details` adds the technical names, evidence and p-values to the terminal output, and every report has a methodology section. How far to trust the grader: see the caveats in the [README](../README.md#current-limitations).
