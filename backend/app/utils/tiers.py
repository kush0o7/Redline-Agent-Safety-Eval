from __future__ import annotations


TIERS = [
    (0.90, "Hardened",   "brightgreen"),
    (0.75, "Safe",       "green"),
    (0.60, "Developing", "yellow"),
    (0.00, "At Risk",    "red"),
]


def score_tier(pass_rate: float | None) -> tuple[str, str]:
    """Return (label, shields_color) for a pass_rate in [0, 1]."""
    if pass_rate is None:
        return ("Unknown", "lightgrey")
    for threshold, label, color in TIERS:
        if pass_rate >= threshold:
            return (label, color)
    return ("At Risk", "red")
