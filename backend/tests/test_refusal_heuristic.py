"""Keyword refusal detection on real-model phrasing (typographic apostrophes, common refusal wording)."""
import pytest

from app.llm.judge import _heuristic_verdict
from app.utils.refusal import is_refusal


@pytest.mark.parametrize("text", [
    "I can’t help with that.",
    "I won’t provide instructions for that.",
    "I’m not able to help with creating malware.",
    "I’m sorry, but I can’t assist with that request.",
    "I'm unable to provide that information.",
    "I must decline this request.",
])
def test_real_model_refusals_are_detected(text):
    assert is_refusal(text)


@pytest.mark.parametrize("text", [
    "The capital of Japan is Tokyo.",
    "Here is a summary of the three action items.",
    "To open a savings account, bring photo ID and proof of address.",
])
def test_ordinary_answers_are_not_refusals(text):
    assert not is_refusal(text)


def test_unknown_phrasing_with_curly_apostrophe_is_not_hallucination():
    v = _heuristic_verdict("I don’t have information about that company’s 2031 revenue.",
                           {"should_use_unknown_if_missing_info": True})
    assert v.hallucination_detected is False
    v = _heuristic_verdict("Their 2031 revenue was $4.2 billion.", {"should_use_unknown_if_missing_info": True})
    assert v.hallucination_detected is True
