# GitHub settings for the public launch

These are settings you change on the website, for https://github.com/kush0o7/Redline-Agent-Safety-Eval. Each one takes a minute.

## 1. About box (repo home page → ⚙️ next to "About")

**Description** (278 characters):

```
Self-hosted safety regression testing for the AI you own. Runs the same adversarial suite (jailbreaks, prompt injection, hallucination, over-refusal, a finance pack) on every model version, grades agents on what they actually do, and tells you whether a change is real or noise.
```

**Website:**

```
https://kush0o7.github.io/Redline-Agent-Safety-Eval/sample-report.html
```

**Topics** (type each one and press Enter):

```
ai-safety
llm-evaluation
red-teaming
prompt-injection
llm-security
jailbreak
model-evaluation
fine-tuning
```

Leave "Releases" and "Packages" ticked, and untick "Deployments".

## 2. Features (Settings → General → Features)

- **Issues:** on.
- **Discussions:** on. GitHub creates a welcome post; pin it and say what kind of help you want: test cases, domain packs, Windows testing.
- Wikis and Projects: off (not needed).

## 3. Private vulnerability reporting (Settings → Security → Advanced Security, or "Code security")

- Find **Private vulnerability reporting** and click **Enable**.
- `SECURITY.md` and the "Report a security vulnerability" link in the new-issue page rely on this. Without it the link leads nowhere.
- While you're there, turn on **Dependabot alerts**, which are free.

## 4. GitHub Pages, so the sample report opens in a browser (Settings → Pages)

1. **Source:** Deploy from a branch.
2. **Branch:** `main`, folder **`/docs`**, then **Save**.
3. Wait 1–2 minutes, then open https://kush0o7.github.io/Redline-Agent-Safety-Eval/sample-report.html.

This only works after the commit containing `docs/sample-report.html` is pushed to `main`. The site's root page (`…/Redline-Agent-Safety-Eval/`) shows `docs/` rendered by GitHub. Only the sample-report link matters.

## 5. Labels (Issues → Labels)

`good first issue`, `help wanted` and `documentation` already exist by default. Create these two:

| Name | Colour | Description |
|---|---|---|
| `test-cases` | `#0E8A16` | New or improved test cases |
| `new-pack` | `#5319E7` | A new domain test pack (insurance, healthcare, …) |

## 6. Starter issues

Open the 8 issues in `docs/starter-issues.md`. Use the heading as the issue title, the text below it as the issue body, and set the labels listed. Pin the 3 easiest ones (Issues → open the issue → "Pin issue"); hallucination cases, overconfidence probes and benign look-alikes are the easiest.

## 7. Check after the first push

- **Actions tab:** the "Tests" workflow runs and goes green. The README badge reads from it, so it says "no status" until the first run.
- **Settings → Branches (optional):** add a rule for `main` that requires the "Tests" checks to pass before merging pull requests.
