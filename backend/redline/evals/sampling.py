"""Deterministic, category-stratified sampling of test cases (shared by quick-eval and the CLI)."""
from __future__ import annotations

import random

from redline.evals.testcases import TestcaseSeed, build_default_testcases
from redline.utils.tiers import load_tier_config, tier_category


class SamplingError(ValueError):
    """Bad sampling request (unknown pack or category, nothing left to test)."""


def select_testcase_seeds(seeds: list[TestcaseSeed], count: int, seed: int) -> list[TestcaseSeed]:
    """Deterministic, category-stratified sample.

    A plain LIMIT with no ORDER BY picked arbitrary rows (Postgres guarantees no
    order), so two "10-case" runs could test entirely different things. Instead:
    shuffle within each type with a seeded RNG, then round-robin across scoring
    categories (the ones tiers are judged on), and across types within each
    category, so every category reaches the per-category minimum as early as
    possible.
    """
    rnd = random.Random(seed)
    cfg = load_tier_config()
    by_cat: dict[str, dict[str, list[TestcaseSeed]]] = {}
    for s in sorted(seeds, key=lambda s: s.name):
        cat = tier_category(s.type, s.pack, cfg)
        by_cat.setdefault(cat, {}).setdefault(s.type, []).append(s)
    for types in by_cat.values():
        for group in types.values():
            rnd.shuffle(group)

    # Per-category cursor that cycles through that category's types.
    type_cursor = {cat: 0 for cat in by_cat}

    def _next_from(cat: str) -> TestcaseSeed | None:
        types = sorted(t for t, g in by_cat[cat].items() if g)
        if not types:
            return None
        t = types[type_cursor[cat] % len(types)]
        type_cursor[cat] += 1
        return by_cat[cat][t].pop(0)

    selected: list[TestcaseSeed] = []
    cat_order = sorted(by_cat)
    while len(selected) < count:
        progressed = False
        for cat in cat_order:
            picked = _next_from(cat)
            if picked is None:
                continue
            progressed = True
            selected.append(picked)
            if len(selected) >= count:
                break
        if not progressed:
            break
    return selected


def available_packs(seeds: list[TestcaseSeed]) -> set[str]:
    return {s.pack for s in seeds}




def excluded_pool(pool: list[TestcaseSeed], exclude_categories: list[str]) -> tuple[list[TestcaseSeed], list[str]]:
    """Drop the excluded scoring categories from the pool."""
    excluded = sorted(set(exclude_categories))
    if not excluded:
        return pool, []
    cfg = load_tier_config()
    present = {tier_category(s.type, s.pack, cfg) for s in pool}
    unknown = set(excluded) - present
    if unknown:
        raise SamplingError(
            f"Unknown category in exclude_categories: {', '.join(sorted(unknown))}. "
            f"Categories in the selected packs: {', '.join(sorted(present))}")
    if present <= set(excluded):
        raise SamplingError("exclude_categories would exclude every category; nothing left to test")
    return [s for s in pool if tier_category(s.type, s.pack, cfg) not in set(excluded)], excluded


def sample_case_seeds(packs: list[str], count: int, seed: int,
                      exclude_categories: list[str] | None = None) -> tuple[list[TestcaseSeed], list[str]]:
    """The seeded, stratified sample from the given packs, plus the categories excluded."""
    all_seeds = build_default_testcases()
    unknown = set(packs) - available_packs(all_seeds)
    if unknown:
        raise SamplingError(f"Unknown test pack(s): {', '.join(sorted(unknown))}. "
                            f"Available: {', '.join(sorted(available_packs(all_seeds)))}")
    pool = [s for s in all_seeds if s.pack in set(packs)]
    pool, excluded = excluded_pool(pool, exclude_categories or [])
    return select_testcase_seeds(pool, count, seed), excluded
