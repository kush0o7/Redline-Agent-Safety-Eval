# X thread draft (5 posts)

Attach `docs/story.gif` to post 1.

**1/5**
```
Did your fine-tune just get less safe?

I tested Llama 3.1 8B vs Hermes 3 8B (a fine-tune of it) on the same 40 safety tests. Hermes followed a hidden instruction in a document and sent a secret token to an attacker's URL. Llama didn't. 🧵
```

**2/5**
```
Hermes also wrote a keylogger, a money-mule job ad and pump-and-dump posts that Llama refused.

Pass rate with an AI grader: 87.5% → 72.5%.

The hidden-instruction cases are graded in code, from the tool calls the model actually made.
```

**3/5**
```
The surprise: the grader changed the conclusion.

Keyword rules: 87.5% → 55%, clearly not chance (p = 0.001).
AI grader: 87.5% → 72.5%, could be chance (p = 0.146).

Both said don't ship. But "how bad" and "how sure" depended on who graded.
```

**4/5**
```
So I made Redline: same tests on two versions, every answer graded, one plain sentence first:

"❌ Don't ship B. It's less safe than A: 9 tests that A passed, B failed."

Then each test that broke, and who graded it. Exit code 1 for CI.
```

**5/5**
```
Free, open source, no downloads to try:

pip install redline-evals
redline try

Limits: grader not yet validated against human labels, single-turn only.

https://github.com/kush0o7/Redline-Agent-Safety-Eval
```
