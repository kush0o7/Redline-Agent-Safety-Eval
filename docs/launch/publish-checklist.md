# Publish checklist: v0.2.0

**Done 21 Nov 2026:** PR #18 merged (`e13f754`), light-mode-cli merged (`7937cc3`), CI green on Ubuntu + Windows, v0.2.0 published by trusted publishing, fresh-venv install 29 s + `redline try` 97 s. Kept as the recipe for the next release. Stop at any step that fails.

## 0. Before you start

- [ ] Working tree clean on `light-mode-cli`, all tests pass: `cd backend && pytest tests/ -q` (382 tests).
- [ ] You have a PyPI account with 2FA and an API token scoped to `redline-evals` (or "entire account" for the very first upload, then re-scope it). Keep it in `~/.pypirc` or paste it when twine asks; never in the repo.

## 1. Merge PR #18 (Windows tests, from a first-time contributor)

1. On the PR page, click **Approve and run workflows** (first-time contributors' CI waits for you). Right now it shows no checks.
2. Wait for **Tests** to pass on ubuntu and windows, Python 3.11 and 3.12.
3. **Squash and merge** on GitHub. Thank them in a comment (the drafted reply from last round).
4. Locally: `git checkout main && git pull`

## 2. Merge `light-mode-cli` into main

A dry run shows no conflicts with PR #18. Watch one thing: after this merge, the new CLI tests run on **Windows** for the first time.

```bash
git checkout main
git merge --no-ff light-mode-cli -m "Light Mode CLI, redline try, plain-English results, launch kit"
cd backend && pytest tests/ -q && cd ..
git push origin main
```

- [ ] Wait for **Tests** on main to pass (including Windows and the cli-smoke job). If Windows fails, fix on a branch before publishing.

## 3. Publish with trusted publishing (no tokens)

`.github/workflows/publish.yml` builds from `backend/`, smoke-tests the wheel and publishes when a `v*` tag is pushed. One-time setup on pypi.org → Your account → Publishing → "Add a new pending publisher": PyPI project name `redline-evals`, owner `kush0o7`, repository `Redline-Agent-Safety-Eval`, workflow `publish.yml`, environment `pypi`.

## 4. Tag the release

```bash
git tag -a v0.2.0 -m "redline-evals 0.2.0: redline compare / scan / report / try"
git push origin v0.2.0      # starts the Publish to PyPI workflow
```

## 5. Check it like a stranger would

```bash
python3 -m venv /tmp/redline-fresh && source /tmp/redline-fresh/bin/activate
cd /tmp && pip install redline-evals
redline --help
redline compare fake-safe fake-degraded --out /tmp/rl-check   # offline; should exit 1 with "❌ Don't ship fake-degraded."
redline try                                                    # needs your GROQ_API_KEY; time it, should be under ~3 min
deactivate
```

- [ ] `redline try` finished, printed the plain first line, opened the report. Note the time.

## 6. Then

- Upload the social preview and update the About text ([../github-settings.md](../github-settings.md)).
- Open the 3 good first issues.
- Start [where-to-share.md](where-to-share.md).
