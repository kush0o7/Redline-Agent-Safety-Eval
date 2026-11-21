import hashlib
import json
from collections.abc import Iterable


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def testcase_content_hash(
    *,
    type: str,
    name: str,
    prompt: str,
    expected_behavior: dict | None,
    severity: int,
    pack: str | None,
) -> str:
    """SHA-256 over everything that determines how a case is run and scored.

    Canonical JSON (sorted keys, no whitespace) so the hash is stable across
    processes and databases. Tags are excluded: they are labels, not behaviour.
    """
    payload = {
        "type": type,
        "name": name,
        "prompt": prompt,
        "expected_behavior": expected_behavior or {},
        "severity": int(severity),
        "pack": pack or "core",
    }
    return stable_hash(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def case_set_hash(content_hashes: Iterable[str]) -> str:
    """Order-independent hash of a set of testcase content hashes.

    Two runs have the same hash iff they ran the same multiset of case contents.
    """
    return stable_hash("\n".join(sorted(content_hashes)))
