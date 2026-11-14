#!/usr/bin/env python3
"""Build a self-contained Kaggle/Colab notebook with this checkout's code embedded.

    python3 scripts/build_kaggle_notebook.py [OUT.ipynb] [GIT_REF]

The notebook carries the committed code of GIT_REF (default: HEAD) as a base64 zip,
so it needs no dataset upload and no GitHub access to Redline: upload the one file,
turn on GPU + internet, Run All. Only committed files are included (git archive),
so .env and other untracked files never end up in it.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(True)}


def build(out: Path, ref: str) -> None:
    blob = subprocess.run(["git", "archive", "--format=zip", ref], cwd=ROOT, check=True, capture_output=True).stdout
    sha = subprocess.run(["git", "rev-parse", "--short", ref], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    b64 = base64.b64encode(blob).decode()
    chunks = "\n".join(f'"{b64[i:i + 100]}"' for i in range(0, len(b64), 100))

    cells = [
        md(f"""
# Redline: real before → after safety check on a free GPU

Self-contained: Redline's code (commit `{sha}`) is **inside this notebook**. No dataset upload, nothing on your laptop.

**Before you click Run All** (right-hand panel → *Session options*):
1. **Accelerator → GPU T4 x2**
2. **Internet → On** (requires a phone-verified Kaggle account)

Then **Run All**. It takes about 15–30 minutes. Cell 3 should show both models on the GPU (`ollama ps` → `100% GPU`). Cell 5 prints nothing until it finishes, which is normal.
At the end, download **`redline-report.html`** from the Output panel (`/kaggle/working`).

Optional, for a better judge: *Add-ons → Secrets* → add `GROQ_API_KEY` (free at console.groq.com), then set `USE_GROQ_JUDGE = True` in cell 1.
"""),
        code("""
# ── 1. Settings ──────────────────────────────────────────────────────────
BEFORE_MODEL = "llama3.1:8b"   # base model: Meta Llama 3.1 8B Instruct
AFTER_MODEL  = "hermes3:8b"    # fine-tune of Llama 3.1 8B (Nous Hermes 3)
CASES        = 40              # 30+ for a rated (non-Provisional) tier
PACKS        = "core,financial_services"
USE_GROQ_JUDGE   = False       # False = free keyword judge (rough); True = LLM judge (needs GROQ_API_KEY secret)
GROQ_JUDGE_MODEL = "auto"      # "auto" = best model your key can use right now; or e.g. "groq/openai/gpt-oss-120b"
"""),
        code(f"""
# ── 2. Unpack Redline (embedded, commit {sha}) ───────────────────────────
import base64, io, os, shutil, zipfile
WORK = "/kaggle/working" if os.path.isdir("/kaggle/working") else "/content"
os.chdir(WORK)
REDLINE = os.path.join(WORK, "redline")
shutil.rmtree(REDLINE, ignore_errors=True)
_CODE = (
{chunks}
)
zipfile.ZipFile(io.BytesIO(base64.b64decode(_CODE))).extractall(REDLINE)
del _CODE
ok = os.path.exists(f"{{REDLINE}}/backend/app/evals/data/jbb_behaviors.json")
print("Redline commit {sha} unpacked to", REDLINE, "| code version:", "NEW (fixed)" if ok else "UNEXPECTED")
"""),
        code("""
# ── 3. Ollama on the GPU + the two models ────────────────────────────────
import json, os, shutil, subprocess, time, urllib.request
if not shutil.which("nvidia-smi"):
    raise SystemExit(
        "NO GPU: this session is CPU-only, so the run would take many hours.\\n"
        "Fix: right-hand panel → Session options → Accelerator → GPU T4 x2 "
        "(if it's greyed out: verify your phone in Kaggle Settings, or you've used this week's GPU hours).\\n"
        "The session restarts when you change it; then Run All again.")
def ollama_up():
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2); return True
    except Exception:
        return False
if not shutil.which("ollama"):
    subprocess.run("apt-get -qq update && apt-get -qq install -y zstd pciutils lshw > /dev/null", shell=True)
    subprocess.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True, check=True)
if not ollama_up():
    subprocess.Popen(["ollama", "serve"], stdout=open("ollama.log", "w"), stderr=subprocess.STDOUT,
                     env=dict(os.environ, OLLAMA_KEEP_ALIVE="-1"))  # keep models loaded between cases
    for _ in range(60):
        if ollama_up(): break
        time.sleep(1)
print("Ollama up:", ollama_up())
for m in (BEFORE_MODEL, AFTER_MODEL):
    print("pulling", m)
    subprocess.run(["ollama", "pull", m], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
# Warm-up: load each model onto the GPU now (the first load can take minutes) and keep it there.
for m in (BEFORE_MODEL, AFTER_MODEL):
    t = time.time()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", method="POST",
        data=json.dumps({"model": m, "prompt": "Say OK.", "stream": False, "keep_alive": -1}).encode(),
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=900).read()
    print(f"{m} loaded and answering ({time.time() - t:.0f}s)")
print(subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout)
print(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv"], capture_output=True, text=True).stdout)
"""),
        code("""
# ── 4. Python dependencies ───────────────────────────────────────────────
import subprocess, sys, tomllib
deps = tomllib.load(open(f"{REDLINE}/backend/pyproject.toml", "rb"))["project"]["dependencies"]
r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", *deps], capture_output=True, text=True)
if r.returncode:
    print(r.stdout[-4000:]); print(r.stderr[-4000:]); raise SystemExit("pip failed: paste the output above")
print("installed", len(deps), "packages")
"""),
        code("""
# ── 5. Run the before → after check (prints when done) ───────────────────
import os, subprocess, sys
env = dict(os.environ,
    DEMO_BEFORE_MODEL=BEFORE_MODEL, DEMO_AFTER_MODEL=AFTER_MODEL,
    DEMO_CASES=str(CASES), DEMO_PACKS=PACKS, DEMO_NO_OPEN="1",
    DEMO_OUT_DIR=os.path.join(WORK, "reports"),
    LLM_PROVIDER="ollama", OLLAMA_BASE_URL="http://127.0.0.1:11434",
    LLM_TIMEOUT_SECONDS="300")   # per request; slow answers are retried too
if USE_GROQ_JUDGE:
    try:
        from kaggle_secrets import UserSecretsClient
        env["GROQ_API_KEY"] = UserSecretsClient().get_secret("GROQ_API_KEY")
    except Exception:
        from google.colab import userdata
        env["GROQ_API_KEY"] = userdata.get("GROQ_API_KEY")
    # Check the key and the judge model BEFORE the 30-minute run (Groq retires models often).
    import json as _json, urllib.request as _ur
    try:
        _req = _ur.Request("https://api.groq.com/openai/v1/models",
                           headers={"Authorization": "Bearer " + env["GROQ_API_KEY"], "User-Agent": "redline-notebook"})
        available = sorted(m["id"] for m in _json.load(_ur.urlopen(_req, timeout=30))["data"])
    except Exception as e:
        raise SystemExit(f"Groq key check failed ({type(e).__name__}: {e}). Is the GROQ_API_KEY secret added AND switched on for this notebook?")
    chat = [m for m in available if not any(x in m for x in ("whisper", "guard", "tts", "playai", "compound", "orpheus", "distil"))]
    prefer = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "qwen/qwen3-32b",
              "meta-llama/llama-4-maverick-17b-128e-instruct", "openai/gpt-oss-20b",
              "meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.1-8b-instant"]
    if GROQ_JUDGE_MODEL != "auto":
        pick = GROQ_JUDGE_MODEL.removeprefix("groq/")
        if pick not in available:
            raise SystemExit(f"Judge model {pick!r} isn't available to your key. Available: {chat}")
    else:
        pick = next((m for m in prefer if m in available), chat[0] if chat else None)
        if not pick:
            raise SystemExit(f"No chat model available on your Groq key. Models: {available}")
    print("Judge model:", pick, "| other chat models on your key:", ", ".join(m for m in chat if m != pick))
    env["JUDGE_MODEL"] = "groq/" + pick
else:
    env["DEMO_FAKE_JUDGE"] = "1"
    env["EVAL_PACING_SECONDS"] = "0"
print("Running… nothing prints until it finishes (20–40 min). Don't stop it.")
proc = subprocess.run([sys.executable, f"{REDLINE}/scripts/demo.py"], env=env, cwd=REDLINE, capture_output=True, text=True)
print(proc.stdout[-15000:])
if proc.returncode:
    print("STDERR:", proc.stderr[-5000:])
"""),
        code("""
# ── 6. The report ────────────────────────────────────────────────────────
import glob, shutil
reports = sorted(glob.glob(f"{WORK}/reports/redline-demo-comparison-*.html"))
if reports:
    shutil.copy(reports[-1], f"{WORK}/redline-report.html")
    print("Report ready: download redline-report.html from the Output panel.")
else:
    print("No report: check cell 5's output.")
"""),
        md("""
## Reading the result
- **Release decision** and **Significance** (*significant (p<0.05)* = unlikely to be noise; McNemar exact test on the flipped cases).
- **decided by code** = injection cases graded from the model's actual tool calls: solid even with the free judge.
- With the free keyword judge, harmful-content verdicts are rough: read a few failed cases in the report yourself.
- **Only public test cases** go to free hosted judges, never real data.
"""),
    ]
    nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                        "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    out.write_text(json.dumps(nb, indent=1))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, code commit {sha})")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "redline_kaggle.ipynb"
    build(out, sys.argv[2] if len(sys.argv) > 2 else "HEAD")
