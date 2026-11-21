# LinkedIn draft

Put the link in the **first comment**, not the post (LinkedIn shows posts with links to fewer people). Attach `docs/demo.gif` or `docs/report-screenshot.png` to the post.

## Post

```
A thing I learned building an AI safety tool: who grades the test can change the answer.

I compared two open AI models: Llama 3.1, and Hermes 3, which is a fine-tuned version of it. Same 40 safety tests on both.

Hermes did some things Llama didn't:
→ It read a document with a hidden instruction in it, and sent a secret access key to a stranger's website.
→ It wrote a keylogger and a fake job ad for money laundering that Llama refused.

Then the surprise. Graded with simple keyword rules, Hermes dropped from 87.5% to 55%, clearly not luck. Graded by another AI, it dropped to 72.5%, and the change could have been luck.

Both said "don't ship it". But how bad, and how sure, depended on the grader.

So I built Redline to always say who graded and how far to trust it. It runs the same tests on two versions of a model and starts with one plain sentence, like: "Don't ship B. It's less safe than A: 9 tests that A passed, B failed."

It's free and open source. If you fine-tune or swap AI models at work, I'd love to hear what you'd want it to test.

Link in the first comment.
```

## First comment

```
Try it in about 2 minutes, no downloads: pip install redline-evals && redline try
https://github.com/kush0o7/Redline-Agent-Safety-Eval
```
