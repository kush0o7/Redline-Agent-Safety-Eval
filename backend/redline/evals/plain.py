"""Plain-English wording for results: one sentence anyone understands, then the details.

Used by the terminal summary, the HTML report and summary.json, so every place says the
same thing. Technical names stay available in brackets or behind ``--details``:

    chance check  = McNemar's exact test on the tests that changed
    safety grade  = tier (Hardened / Safe / Developing / At Risk)
    most dangerous = severity 5
    grader        = judge (LLM judge, keyword rules, or a code check)
"""
from __future__ import annotations

from redline.evals.release import _impact_pair, risk_sentence
from redline.evals.redaction import is_sim_placeholder

# Scoring categories, in words.
AREA_NAMES = {
    "harmful_compliance": "Harmful requests",
    "injection": "Hidden instructions in documents the AI reads",
    "hallucination": "Making things up",
    "over_refusal": "Refusing harmless questions",
    "financial_services": "Finance pack",
}
AREA_SHORT = {"harmful_compliance": "harmful request", "injection": "hidden instructions",
              "hallucination": "making things up", "over_refusal": "refusing harmless questions",
              "financial_services": "finance"}
DANGER = {5: "most dangerous", 4: "very dangerous", 3: "dangerous", 2: "minor", 1: "minor"}
GRADER_NAMES = {"code": "code check (what the AI actually did)", "judge": "AI grader", "heuristic": "keyword rules"}


def area(cat: str | None) -> str:
    return AREA_NAMES.get(cat or "", (cat or "other").replace("_", " ").capitalize())


def danger(sev) -> str:
    return DANGER.get(int(sev or 0), "unrated")


def _tests(n: int) -> str:
    return f"{n} test{'' if n == 1 else 's'}"


def chance_words(sig: dict | None) -> str:
    """'very unlikely to be chance' / 'unlikely to be chance' / 'could easily be chance' / ''."""
    if not sig or not sig.get("discordant"):
        return ""
    p = sig.get("p_value")
    if p is None:
        return ""
    if p < 0.01:
        return "very unlikely to be chance"
    if p < 0.05:
        return "unlikely to be chance"
    return "could easily be chance"


def headline(cmp: dict) -> str:
    """The first line of every comparison result."""
    a = (cmp.get("base") or {}).get("model") or "A"
    b = (cmp.get("candidate") or {}).get("model") or "B"
    rel = cmp.get("release") or {}
    regs = len((cmp.get("flipped") or {}).get("regressions") or [])
    imps = len((cmp.get("flipped") or {}).get("improvements") or [])
    sig = (cmp.get("significance") or {}).get("overall") or {}
    chance = chance_words(sig)
    sev5 = rel.get("new_severity5_regressions") or 0
    broke = f"{_tests(regs)} that {a} passed, {b} failed"
    if rel.get("decision") == "FAIL":
        if sig.get("significant") and sig.get("direction") == "worse":
            return f"❌ Don't ship {b}. It's less safe than {a}: {broke}. This is {chance}."
        if sev5:
            return (f"❌ Don't ship {b}. {broke[0].upper() + broke[1:]}, {sev5} of them among the most dangerous. "
                    "That could be chance, but the most dangerous failures block a release on their own.")
        tier = (cmp.get("candidate") or {}).get("indicative_tier")
        floor = rel.get("min_tier") or "Safe"
        tail = f": {broke}." if regs else "."
        return f"❌ Don't ship {b}. Its safety grade ({tier}) is below the bar ({floor}){tail}"
    if not regs and not imps:
        return f"✅ {b} is as safe as {a}. No test changed."
    if sig.get("significant") and sig.get("direction") == "better":
        return f"✅ {b} is safer than {a}: {_tests(imps)} that {a} failed, {b} passed. This is {chance}."
    changed = regs + imps
    return f"✅ {b} is as safe as {a}. {_tests(changed)} changed, which is normal noise."


def notes(cmp: dict) -> list[str]:
    """Short caveats that belong right under the headline."""
    out = []
    shared = cmp.get("common_total") or 0
    if shared and shared < 30:
        out.append(f"Only {_tests(shared)}: a quick look, not a full check. Use --cases 40 or more before a real release.")
    rel = cmp.get("release") or {}
    tier_check = next((c for c in rel.get("checks") or [] if c.get("name") == "tier"), {})
    if tier_check.get("waived"):
        out.append(f"Its safety grade ({tier_check.get('actual')}) is below the bar ({rel.get('min_tier')}), "
                   "but the drop could be chance: check again on more tests.")
    if not (cmp.get("case_set") or {}).get("identical", True):
        out.append("The two runs didn't use exactly the same tests, so this isn't a like-for-like comparison.")
    judge = cmp.get("judge") or {}
    if judge.get("base") and judge.get("candidate") and not judge.get("identical"):
        out.append("The two runs were graded by different graders, so part of the change may come from the grader.")
    return out


def _did(d: dict, *, passed: bool, answer: str | None) -> str:
    """What one model did on a test, in a few words."""
    t, cat = d.get("type"), d.get("category")
    if t == "injection":
        if passed:
            return "ignored the hidden instructions"
        _, present = _impact_pair(d)
        return f"followed them: it {present}" if present else "followed the hidden instructions"
    if d.get("should_refuse"):
        if passed:
            return "refused"
        if is_sim_placeholder(answer):
            return "complied (simulated)"
        return "complied (the answer is hidden in this report)"
    if cat == "hallucination":
        return "said it doesn't know" if passed else "made up an answer"
    if cat == "over_refusal" or t in ("benign", "fin_benign"):
        return "answered" if passed else "refused a harmless question"
    return "passed" if passed else "failed"


def case_story(d: dict) -> dict:
    """One broken test, four short lines: what we asked, what A did, what B did, why it matters."""
    matters = d.get("impact") if d.get("type") == "injection" and d.get("impact") else risk_sentence(d)
    return {
        "name": d.get("name"),
        "danger": danger(d.get("severity")),
        "area": area(d.get("category")),
        "area_short": AREA_SHORT.get(d.get("category") or "", area(d.get("category")).lower()),
        "asked": " ".join(str(d.get("prompt") or "").split()),
        "a_did": _did(d, passed=bool(d.get("base_passed")), answer=d.get("base_answer")),
        "b_did": _did(d, passed=bool(d.get("candidate_passed")), answer=d.get("candidate_answer")),
        "why": matters,
    }


def scan_verdict(summary: dict) -> tuple[bool, str, str]:
    """(passed, tier, min_tier) for a single run: its tier must meet the release floor."""
    from redline.evals.release import release_min_tier, tier_rank

    tier_eval = summary.get("tier_evaluation") or {}
    tier = tier_eval.get("indicative_tier") or summary.get("tier")
    min_tier = release_min_tier()
    rank = tier_rank()
    return rank.get(tier, -1) >= rank.get(min_tier, 0), tier, min_tier


def scan_headline(model: str, passed: bool, tier: str | None, min_tier: str, summary: dict) -> str:
    total, ok = summary.get("total") or 0, summary.get("passed") or 0
    failed = total - ok
    if passed:
        return f"✅ {model} passed the bar: safety grade {tier}, {ok} of {total} tests passed."
    sev5 = summary.get("severity5_failures") or 0
    extra = f", {sev5} of the failures among the most dangerous" if sev5 else ""
    return f"❌ Don't ship {model} yet. Its safety grade ({tier}) is below the bar ({min_tier}): {failed} of {total} tests failed{extra}."


def plain_block(cmp: dict) -> dict:
    """Everything plain, for summary.json and the report."""
    return {
        "headline": headline(cmp),
        "notes": notes(cmp),
        "broken": [case_story(d) for d in (cmp.get("flipped") or {}).get("regressions") or []],
    }


_LABEL_WORDS = {"harmful-content": "harmful-request", "prompt-injection": "hidden-instruction",
                "financial-services": "finance-pack", "over-refusal": "refused-harmless-question",
                "hallucination": "made-up-answer"}


def plain_text(text: str) -> str:
    """Swap the remaining technical words in a generated sentence for plain ones."""
    for k, v in _LABEL_WORDS.items():
        text = text.replace(f"{k} failure", f"{v} failure")
    return (text.replace("severity-5 regressions", "most dangerous failures")
                .replace("severity-5 regression", "most dangerous failure")
                .replace("the tier", "the safety grade").replace(" tier ", " safety grade ")
                .replace("Tier ", "Safety grade ", 1 if text.startswith("Tier ") else 0)
                .replace("release floor", "bar"))
