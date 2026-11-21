"""``redline try``: a real before/after check in about 2-3 minutes, with one free key and no downloads.

It compares two different hosted models on 10 test cases (a stand-in for "your model before and
after a change") and grades them with a third hosted model. The models are picked from what the
key can use today, because free model lists change every few weeks.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from redline.models import FREE_TIER_LINE, OPENROUTER_BASE_URL, ModelError, key_value

SIGNUP = {"groq": "https://console.groq.com/keys", "openrouter": "https://openrouter.ai/keys"}
KEY_ENV = {"groq": "GROQ_API_KEY", "openrouter": "OPENROUTER_API_KEY"}

# Preference lists, best first. Whatever the key can't use is skipped.
GROQ = {
    "before": ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.3-70b-versatile", "qwen/qwen3.8-27b", "qwen/qwen3-32b"],
    "after": ["llama-3.1-8b-instant", "allam-2-7b", "meta-llama/llama-4-scout-17b-16e-instruct", "qwen/qwen3.8-27b",
              "qwen/qwen3-32b", "openai/gpt-oss-20b"],
    "judge": ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "qwen/qwen3.8-27b", "qwen/qwen3-32b", "openai/gpt-oss-20b"],
}
OPENROUTER = {
    "before": ["google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free", "nvidia/nemotron-3.5-lightning:free"],
    "after": ["liquid/lfm-3-1.7b:free", "inclusionai/ling-3.2-flash:free", "recursive/flint-v1.0:free",
              "baidu/ernie-5.5-flash-preview:free"],
    "judge": ["nvidia/nemotron-3-ultra-550b-a55b:free", "google/gemma-4-31b-it:free", "nvidia/nemotron-3.5-super-vl:free",
              "google/gemma-4-26b-a4b-it:free"],
}
_NOT_CHAT = ("whisper", "guard", "tts", "orpheus", "playai", "compound", "distil", "lyria", "embed", "safeguard")
TRY_CASES = 10
TRY_MAX_TOKENS = 300          # short answers: fast, and the grader's free token budget lasts
OPENROUTER_REQUESTS = 45      # roughly what a 10-case try needs (answers + grading)


def _get_json(url: str, key: str | None = None, timeout: float = 20) -> dict:
    headers = {"User-Agent": "redline-cli"}
    if key:
        headers["Authorization"] = "Bearer " + key
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
        return json.load(resp)


def _ask_for_key() -> tuple[str, str]:
    if not sys.stdin.isatty():
        raise ModelError("redline try needs a free key. Set GROQ_API_KEY (get one at https://console.groq.com/keys) "
                         "or OPENROUTER_API_KEY (https://openrouter.ai/keys), then run it again.")
    print("\nredline try needs one free key (it's never printed or saved):")
    print(f"  1) Groq        — free, fastest. Get a key: {SIGNUP['groq']}")
    print(f"  2) OpenRouter  — free models, 50 requests a day. Get a key: {SIGNUP['openrouter']}")
    choice = (input("Which one? [1]: ").strip() or "1")
    provider = "openrouter" if choice in ("2", "openrouter") else "groq"
    key = getpass.getpass(f"Paste your {provider.capitalize()} key (hidden): ").strip()
    if not key:
        raise ModelError("No key entered.")
    print(f"  To skip this next time: add {KEY_ENV[provider]}=... to a .env file in this folder, or export it.")
    return provider, key


def choose_key(requested: str | None) -> tuple[str, str]:
    """(provider, key) from --provider / the environment / ./.env, else ask."""
    for provider in ([requested] if requested else ["groq", "openrouter"]):
        key = key_value(KEY_ENV[provider])
        if key:
            print(f"  Using {KEY_ENV[provider]} from your environment.")
            return provider, key
    return _ask_for_key()


def _first(prefs: list[str], available: list[str], exclude: set[str]) -> str | None:
    return next((m for m in prefs if m in available and m not in exclude), None)


def pick_models(provider: str, key: str) -> tuple[str, str, str]:
    """(before, after, grader) model strings the key can use right now."""
    try:
        if provider == "groq":
            ids = [m["id"] for m in _get_json("https://api.groq.com/openai/v1/models", key)["data"]]
            prefs = GROQ
        else:
            info = _get_json(f"{OPENROUTER_BASE_URL}/key", key).get("data") or {}
            left = ((info.get("free_model_daily_requests") or {}).get("remaining"))
            if isinstance(left, int) and left < OPENROUTER_REQUESTS:
                raise ModelError(f"Your OpenRouter key has {left} free requests left today; redline try needs about "
                                 f"{OPENROUTER_REQUESTS}. Try tomorrow, or use a Groq key.")
            models = _get_json(f"{OPENROUTER_BASE_URL}/models")["data"]
            ids = [m["id"] for m in models if m["id"].endswith(":free") and m["id"] != "openrouter/free"
                   and "tools" in (m.get("supported_parameters") or [])]
            prefs = OPENROUTER
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ModelError(f"{provider.capitalize()} didn't accept that key (HTTP {exc.code}). "
                             f"Check it at {SIGNUP[provider]}.") from None
        raise ModelError(f"Couldn't list {provider.capitalize()} models (HTTP {exc.code}).") from None
    except urllib.error.URLError as exc:
        raise ModelError(f"Couldn't reach {provider.capitalize()} ({exc.reason}). Are you online?") from None
    chat = [m for m in ids if not any(x in m.lower() for x in _NOT_CHAT)]
    before = _first(prefs["before"], chat, set()) or (chat[0] if chat else None)
    after = _first(prefs["after"], chat, {before}) or next((m for m in chat if m != before), None)
    judge = _first(prefs["judge"], chat, {before, after}) or _first(prefs["judge"], chat, set())
    if not (before and after and judge):
        raise ModelError(f"Your {provider.capitalize()} key can't use enough chat models right now ({len(chat)} found).")
    return f"{provider}/{before}", f"{provider}/{after}", f"{provider}/{judge}"


def cmd_try(args) -> int:
    from redline import cli, local

    Path(args.out).mkdir(parents=True, exist_ok=True)
    local.bootstrap(Path(args.out) / "redline.db")  # before anything reads settings (key lookup does)
    print("\nRedline try: a quick, real safety check of two hosted models (no downloads).")
    provider, key = choose_key(args.provider)
    os.environ[KEY_ENV[provider]] = key  # this process only; never printed or written
    before, after, judge = pick_models(provider, key)
    print(f"  A (before): {before}\n  B (after):  {after}\n  Grader:     {judge}")
    print("  Two different models stand in for 'your model before and after a change'.")
    print(f"  ⚠ {FREE_TIER_LINE}")
    print(f"  {TRY_CASES} tests, short answers. Usually 2-3 minutes.\n")
    run_args = argparse.Namespace(before=before, after=after, cases=TRY_CASES, packs="core", seed=args.seed,
                                  judge=judge, out=args.out, concurrency=2, no_cache=False, details=args.details,
                                  fast=True, max_tokens=TRY_MAX_TOKENS)
    code = cli.cmd_compare(run_args)
    report = Path(args.out) / "report.html"
    if code in (cli.EXIT_PASS, cli.EXIT_FAIL) and report.exists():
        print("\n  Next: test your own model →  redline compare ollama/your-model-v1 ollama/your-model-v2")
        if not args.no_open and sys.stdout.isatty():
            webbrowser.open(report.resolve().as_uri())
    return code


def add_try_parser(sub) -> None:
    p = sub.add_parser("try", help="a quick real check with one free key (Groq or OpenRouter), no downloads")
    p.add_argument("--provider", choices=["groq", "openrouter"], default=None, help="which free key to use (default: whichever is set)")
    p.add_argument("--out", default="./redline-try", help="output folder (default ./redline-try)")
    p.add_argument("--seed", type=int, default=7, help="which 10 tests to sample (default 7)")
    p.add_argument("--no-open", action="store_true", help="don't open the report in a browser")
    p.add_argument("--details", action="store_true", help="show technical details")
    p.set_defaults(func=cmd_try)
