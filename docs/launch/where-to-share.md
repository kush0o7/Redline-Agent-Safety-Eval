# Where to share (checklist)

Post in this order, one or two a day, and stay around to answer comments. Nothing here asks for upvotes or stars: every venue below bans or frowns on that. Rules checked on 20 Nov 2026; Reddit's pages couldn't be fetched, so those rules are unverified.

| # | Where | Exists? Tool posts OK? | What to post |
|---|---|---|---|
| 1 | [ ] **Show HN** (news.ycombinator.com/submit) | ✅ Checked. "Show HN" is for things people can try, ideally without sign-ups; no upvote requests. | [show-hn.md](show-hn.md): title + repo link, then the first comment. A weekday morning, US Eastern. |
| 2 | [ ] **r/LocalLLaMA** | ⚠️ Exists; rules **not verified** (Reddit blocked fetching). Read the sidebar for self-promo limits and flair. | [reddit-localllama.md](reddit-localllama.md): lead with the Hermes finding, link at the end. |
| 3 | [ ] **r/MachineLearning** | ⚠️ Rules **not verified**. Project posts usually need a `[P]` tag in the title. | `[P] Same 40 safety tests on Llama 3.1 vs its fine-tune Hermes 3: the grader changed the conclusion`. Lead with the grader finding (p = 0.001 vs 0.146), then the tool. |
| 4 | [ ] **r/LLMDevs** | ⚠️ Rules **not verified**. | The CI angle: "a safety regression check for model swaps, exit code 1 on fail". Short body + GIF. |
| 5 | [ ] **corca-ai/awesome-llm-security** (GitHub PR) | ✅ Checked. Accepts PRs; has a "Tools" section. | One line in Tools: `[Redline](https://github.com/kush0o7/Redline-Agent-Safety-Eval) - Safety regression tests between model versions: jailbreaks, tool-result prompt injection graded in code, plain-English release verdict.` |
| 6 | [ ] **Hannibal046/Awesome-LLM** (GitHub PR) | ✅ Checked. Accepts PRs; "LLM Evaluation" section. Weaker fit; skip if they only list big projects. | One line in LLM Evaluation, same wording as above. |
| 7 | [ ] **OWASP GenAI Security Project Slack** (owasp.org/slack/invite → `#project-genai`) | ✅ Invite route checked. No documented process for their Tools directory; ask in the channel. | A short hello: what it is, the injection-graded-in-code part, ask if it fits their solutions list. No hard sell. |
| 8 | [ ] **LessWrong** | ✅ Exists. An announcement would likely sit as a personal blogpost (inference, not a stated rule). | Write-up of the grader finding: "Who grades a safety eval can flip its conclusion", with the numbers and the limits. Tool link at the end. |
| 9 | [ ] **Product Hunt** | ✅ Checked. For "products people can use"; no paid or requested upvotes. | Later, after HN/Reddit feedback. Tagline: "Did your fine-tune get less safe? Find out in one command." Gallery: GIF, report screenshot, social preview. |
| 10 | [ ] **Your LinkedIn + X** | ✅ Your own accounts. | [linkedin.md](linkedin.md) (link in first comment), [x-thread.md](x-thread.md) (GIF on post 1). |

## Checked and skipped for now

- **Lobsters:** invite-only, and accounts younger than 70 days can't post their own projects.
- **TLDR AI newsletter:** paid ads only; no free submissions.
- **CAIS AI Safety Newsletter:** Substack; no submission route found.

## Before the first post

- [x] v0.2.0 is on PyPI; fresh venv: install 29 s, `redline try` 97 s, exit 0 (21 Nov 2026).
- [ ] Social preview uploaded (Settings → General → Social preview → `docs/social-preview.png`).
- [x] About text updated ([../github-settings.md](../github-settings.md)).
- [ ] The 3 good first issues are open ([good-first-issues.md](good-first-issues.md)).
