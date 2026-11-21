"""Paired significance for version-to-version compares: McNemar's exact test.

A compare runs both versions on the identical cases, so each case is a pair
(before pass/fail, after pass/fail). Only the discordant pairs carry information:
``b`` = regressions (pass → fail) and ``c`` = improvements (fail → pass). Under
"no real change", each discordant case is equally likely to go either way, so
``b ~ Binomial(b + c, 0.5)`` and the exact two-sided p-value is

    p = min(1, 2 · Σ_{k=0}^{min(b, c)} C(n, k) · 0.5^n),   n = b + c.

(McNemar 1947; the exact binomial form is the usual choice for small n.)
A change is labelled "significant (p<0.05)" or "within noise"; no flipped
cases at all is "no change".
"""
from __future__ import annotations

from math import comb

ALPHA = 0.05
TEST_NAME = "McNemar exact test (two-sided, paired pass/fail on identical cases)"
SIGNIFICANT = "significant (p<0.05)"
WITHIN_NOISE = "within noise"
NO_CHANGE = "no change"


def mcnemar_exact_p(regressions: int, improvements: int) -> float:
    b, c = int(regressions), int(improvements)
    if b < 0 or c < 0:
        raise ValueError("counts must be non-negative")
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired_change(regressions: int, improvements: int, alpha: float = ALPHA) -> dict:
    b, c = int(regressions), int(improvements)
    p = mcnemar_exact_p(b, c)
    significant = (b + c) > 0 and p < alpha
    direction = "worse" if b > c else "better" if c > b else "same"
    label = NO_CHANGE if b + c == 0 else SIGNIFICANT if significant else WITHIN_NOISE
    return {"regressions": b, "improvements": c, "discordant": b + c, "p_value": round(p, 4),
            "significant": significant, "direction": direction, "label": label}


def format_p(p: float | None) -> str:
    if p is None:
        return "n/a"
    return "p<0.001" if p < 0.001 else f"p={p:.3f}"
