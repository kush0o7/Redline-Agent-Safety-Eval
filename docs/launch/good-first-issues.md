# 3 new good first issues

Open these with the `good first issue` label. They don't repeat the 8 in [../starter-issues.md](../starter-issues.md).

1. **`redline try`: add Gemini as a third free-key option**
   `try_cmd.py` supports Groq and OpenRouter. Add Google AI Studio (`GEMINI_API_KEY`, sign-up link, list the models the key can use, pick before/after/grader). Mocked-HTTP test like `test_try_picks_models_the_key_can_use`.

2. **Plain-English wording for `redline scan`'s "By area" lines when an area has fewer than 5 tests**
   Small areas get a "Provisional" grade but the terminal doesn't say why in plain words. Add one line such as "Only 3 tests in Making things up: too few to grade this area." in `local.format_scan`, plus a test.

3. **Add `--json` to `redline compare` that prints only `summary.json`'s `plain` block**
   For people piping Redline into scripts or bots: `{"headline": ..., "notes": [...], "broken": [...]}` on stdout, nothing else. The data already exists (`evals/plain.plain_block`); this is CLI plumbing and one test.
