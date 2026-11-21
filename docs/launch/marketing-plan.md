# Marketing plan (first 2 weeks)

Goal: real people trying Redline (stars, pip installs, issues from strangers), with nothing that looks like spam.

Rules we keep:
- One post per community, following that community's own rules (read them first).
- Lead with a finding, not with "I built a tool". Link once.
- No upvote or star requests, no fake accounts, no mass DMs, no star-for-star.
- The maintainer posts on HN, Reddit, LinkedIn and X by hand. Every GitHub PR or comment gets shown first and opened only after a yes.
- Stay around for 2 hours after each post to answer comments. Replies matter more than the post.

The two findings we lead with:
1. **Hermes:** Hermes 3 8B, a fine-tune of Llama 3.1 8B, followed a hidden instruction and sent a deploy token to an attacker URL with a real tool call. It also wrote a keylogger and a money-mule ad that Llama refused. With the AI grader the pass rate went from 87.5% to 72.5% on 40 tests.
2. **The grader changed the answer:** keyword rules said 87.5% → 55% (p = 0.001, not chance). The AI grader said 87.5% → 72.5% (p = 0.146, could be chance). Both said don't ship.

Finding posts come from [content-engine.md](content-engine.md). Numbers are tracked in [metrics.md](metrics.md), and the posts are in [posts.md](posts.md) plus the older drafts ([show-hn.md](show-hn.md), [reddit-localllama.md](reddit-localllama.md), [linkedin.md](linkedin.md), [x-thread.md](x-thread.md)).

## Channels (19)

"Checked" means we opened the page on 20–21 Nov 2026 and it was there and active. Reddit blocks automated fetches, so **Reddit rules are unverified**: read the sidebar and pinned posts before posting.

| # | Where | Link | Checked? | Self-promo rules (short) | Best time (MST) | Post that fits |
|---|---|---|---|---|---|---|
| 1 | Hacker News, Show HN | news.ycombinator.com/showhn | ✅ active | It has to be something people can try now. No upvote requests, no friends voting. Title starts "Show HN:". | 7–9 am, Tue–Thu is best; weekends have less traffic but less competition too | Repo link + first comment (Hermes + grader finding, limits) |
| 2 | r/LocalLLaMA | reddit.com/r/LocalLLaMA | ✅ active (very) · rules ⚠️ | Usually OK to share your own open-source tool if it's useful. Check the flair and the "no low-effort self-promo" rule. | ~11 am | Finding-first: Hermes vs Llama, numbers, then the tool |
| 3 | r/LLMDevs | reddit.com/r/LLMDevs | ✅ active · rules ⚠️ | Tool posts allowed with flair (check which). | 9–11 am weekday | CI angle: a safety check for model swaps, exit code 1 on fail |
| 4 | r/MachineLearning | reddit.com/r/MachineLearning | ✅ active · rules ⚠️ | Strict. Projects need a `[P]` tag; plain promotion goes in the pinned self-promotion thread. | weekday morning | `[P]` post about the grader finding, written as a result rather than an ad |
| 5 | r/mlops | reddit.com/r/mlops | ✅ exists · rules ⚠️ | Small; tools OK if relevant. | weekday morning | "Regression gate for model releases" angle |
| 6 | Hugging Face Posts | huggingface.co/posts | ✅ active | Anyone with an HF account can post; findings about models get read. | any weekday | The gpt-oss / safeguard finding (fresh, model-specific) |
| 7 | Hugging Face Discord | hf.co/join/discord → `#i-made-this` | ✅ invite works | Showcase channel is for exactly this; one message. | any | Short note + link |
| 8 | Unsloth Discord | discord.gg/unsloth (from unsloth.ai) | ✅ invite works | Has a showcase channel; fine-tuners are the exact user. | any | "Check your fine-tune didn't lose safety", 3 lines |
| 9 | MLOps Community Slack | mlops.community → Join Slack | ✅ active | Self-promo only in its tools / "i-made-this" style channel; check the channel topic. | weekday | CI angle + compare command |
| 10 | OWASP GenAI Security Project Slack | owasp.org/slack/invite → `#project-top10-for-llm` / `#project-genai` | ✅ invite route | No tool directory process; ask, don't pitch. | weekday | Injection graded in code from real tool calls; ask if it fits their solutions list |
| 11 | Latent Space Discord | latent.space → Discord | ✅ active | Has a share-your-work channel; check which. | any | Grader finding, one paragraph |
| 12 | LessWrong | lesswrong.com | ✅ active | Research write-ups welcome; pure ads aren't. Likely a personal blogpost. | any | "Who grades a safety eval can change its conclusion" with numbers and limits |
| 13 | console.dev newsletter | console.dev (submit by email, per their site) | ✅ takes submissions | They pick tools for developers; no paid placement. | any | Blurb (posts.md §Newsletters) |
| 14 | PyCoder's Weekly | pycoders.com/submissions | ✅ takes submissions | Link submissions for Python projects and articles. | any | Blurb |
| 15 | Changelog News | changelog.com/news/submit | ✅ takes submissions | Anyone can submit a news item. | any | Blurb |
| 16 | Awesome lists (GitHub PRs) | see [awesome-prs.md](awesome-prs.md) | ✅ 4 lists active, recent merges | Each list's CONTRIBUTING format; one PR each; say you're the author. | any | One line in the right section |
| 17 | LinkedIn (own feed) | linkedin.com | ✅ | Your own feed. Put the link in the first comment. | Tue–Wed 8–10 am | Grader finding in plain words ([linkedin.md](linkedin.md)), later "how I built it" |
| 18 | X (own account) | x.com | ✅ | Your own account. | weekday 9 am–noon | 5-post thread ([x-thread.md](x-thread.md)) |
| 19 | Product Hunt | producthunt.com | ✅ | No requested or paid upvotes. | Tue–Thu 12:01 am PT | **Later** (week 3+), after HN/Reddit feedback |

Skipped: **r/opensource** (its rules restrict AI-related posts), **Lobsters** (invite-only, new accounts can't post their own projects), **TLDR AI** (paid placement only).

## Calendar (launch day + 2 weeks)

Launch day is busy on purpose. After that, at most 1–2 posts a day, with subreddits at least 2 days apart. GitHub PRs and newsletter forms aren't community posts.

| Day | Time (MST) | Where | What |
|---|---|---|---|
| **Sat 21 Nov** | 7 am | **Show HN** | [show-hn.md](show-hn.md). Stay on the thread for the morning. |
| | 10 am | **Hugging Face Posts** | gpt-oss finding post ([content-engine.md](content-engine.md)) |
| | 11 am | **r/LocalLLaMA** | [reddit-localllama.md](reddit-localllama.md) |
| | noon | **X thread** | [x-thread.md](x-thread.md), `docs/story.gif` on post 1 |
| | afternoon | **HF Discord `#i-made-this`** | [posts.md](posts.md) |
| | any time | Awesome-list PRs, newsletter forms | [awesome-prs.md](awesome-prs.md), [posts.md](posts.md) §Newsletters |
| Sun 22 Nov | — | — | Reply to comments. |
| Mon 23 Nov | 9–11 am | r/LLMDevs | CI angle ([posts.md](posts.md)) |
| **Tue 24 Nov** | 8–10 am | **LinkedIn** | [linkedin.md](linkedin.md), link in the first comment |
| Wed 25 Nov | weekday | MLOps Community Slack | [posts.md](posts.md) |
| Thu 26 Nov | — | — | Thanksgiving. |
| Fri 27 Nov | — | — | Weekly metrics row. |
| Sat 28 Nov | any | Unsloth Discord showcase | [posts.md](posts.md) |
| Mon 30 Nov | morning | r/MachineLearning `[P]` | Only after re-reading its rules. |
| Tue 1 Dec | 8–10 am | LinkedIn "how I built it" | [posts.md](posts.md) |
| Wed 2 Dec | morning | r/mlops | Regression-gate angle |
| Thu 3 Dec | any | LessWrong write-up · OWASP Slack (ask, don't pitch) | [posts.md](posts.md) |
| Fri 4 Dec | any | Latent Space Discord | Metrics row; plan week 3 (pair 2 post, Product Hunt?) |

After each post, write in [metrics.md](metrics.md) which channel it was and the time, so we can see what brought the stars.
