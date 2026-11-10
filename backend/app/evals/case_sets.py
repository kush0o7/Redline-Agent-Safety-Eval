"""A run's exact case set: which testcase rows it used and a hash of their content.

Runs are only comparable when they tested the same thing. Every run records its
testcase IDs and ``case_set_hash``; quick-eval ``rerun_of`` reuses another run's
rows exactly; and compare flags pairs whose case sets differ.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Run, Testcase, compute_testcase_hash
from app.utils.hashing import case_set_hash


@dataclass
class CaseSet:
    testcase_ids: list[str]
    content_hashes: dict[str, str]   # testcase_id -> content hash (current row content)
    hash: str                        # hash of the current row content
    stored_hash: str | None          # hash recorded on the run when it was created (None for legacy runs)
    missing_ids: list[str]           # IDs the run recorded whose rows no longer exist

    @property
    def intact(self) -> bool:
        """True if every recorded row still exists and its content matches what the run recorded."""
        return not self.missing_ids and (self.stored_hash is None or self.stored_hash == self.hash)


def hashes_for(testcases: list[Testcase]) -> dict[str, str]:
    return {str(tc.id): (tc.content_hash or compute_testcase_hash(tc)) for tc in testcases}


def build_case_set(testcases: list[Testcase]) -> tuple[list[str], str]:
    """IDs (in the given order) and the case-set hash, for recording on a new run."""
    hashes = hashes_for(testcases)
    return [str(tc.id) for tc in testcases], case_set_hash(hashes.values())


def run_testcase_ids(run: Run) -> list[str]:
    if run.testcase_ids:
        return [str(i) for i in run.testcase_ids]
    summary = run.summary if isinstance(run.summary, dict) else {}
    return [str(i) for i in summary.get("testcase_ids", []) or []]


def case_set_for_run(db: Session, run: Run) -> CaseSet:
    ids = run_testcase_ids(run)
    rows = db.query(Testcase).filter(Testcase.id.in_(ids)).all() if ids else []
    by_id = {str(tc.id): tc for tc in rows}
    present = [by_id[i] for i in ids if i in by_id]
    hashes = hashes_for(present)
    return CaseSet(
        testcase_ids=ids,
        content_hashes=hashes,
        hash=case_set_hash(hashes.values()),
        stored_hash=run.case_set_hash,
        missing_ids=[i for i in ids if i not in by_id],
    )


def compare_case_sets(base: CaseSet, candidate: CaseSet) -> dict:
    """Describe whether two runs used identical cases, for the compare endpoint."""
    base_ids, cand_ids = set(base.content_hashes), set(candidate.content_hashes)
    base_effective = base.stored_hash or base.hash
    cand_effective = candidate.stored_hash or candidate.hash
    identical = (
        base_effective == cand_effective
        and base.intact
        and candidate.intact
        and base_ids == cand_ids
    )

    problems: list[str] = []
    only_base, only_cand = sorted(base_ids - cand_ids), sorted(cand_ids - base_ids)
    if only_base or only_cand:
        problems.append(f"{len(only_base)} case(s) only in base, {len(only_cand)} only in candidate")
    if base_effective != cand_effective and not (only_base or only_cand):
        problems.append("case content differs between runs")
    for label, cs in (("base", base), ("candidate", candidate)):
        if cs.missing_ids:
            problems.append(f"{len(cs.missing_ids)} {label} case(s) no longer exist")
        elif cs.stored_hash and cs.stored_hash != cs.hash:
            problems.append(f"{label} cases changed since that run was recorded")

    return {
        "identical": identical,
        "base_case_set_hash": base_effective,
        "candidate_case_set_hash": cand_effective,
        "base_total": len(base.testcase_ids),
        "candidate_total": len(candidate.testcase_ids),
        "only_in_base": len(only_base),
        "only_in_candidate": len(only_cand),
        "warning": None if identical else (
            "These runs did not use identical test cases, so the comparison is not like-for-like: "
            + "; ".join(problems or ["case sets differ"])
            + ". Use quick-eval rerun_of to rerun the exact same cases."
        ),
    }
