from app.evals.scoring import score_testcase


def test_scoring_policy_refusal():
    expected = {"should_refuse": True, "should_use_unknown_if_missing_info": False}
    result = score_testcase("prompt", expected, "I can't help", refusal=True, confidence=None)
    assert result.scores["policy_compliance"] is True


def test_scoring_policy_non_refusal():
    expected = {"should_refuse": False, "should_use_unknown_if_missing_info": False}
    result = score_testcase("prompt", expected, "Here you go", refusal=False, confidence=None)
    assert result.scores["policy_compliance"] is True


def test_scoring_hallucination_unknown():
    expected = {"should_refuse": False, "should_use_unknown_if_missing_info": True}
    result = score_testcase("prompt", expected, "I don't know", refusal=False, confidence=None)
    assert result.scores["hallucination"] is True


def test_scoring_hallucination_flag():
    expected = {"should_refuse": False, "should_use_unknown_if_missing_info": True}
    result = score_testcase("prompt", expected, "The answer is 12345", refusal=False, confidence=None)
    assert result.scores["hallucination"] is False


def test_scoring_overconfidence():
    expected = {"should_refuse": False, "should_use_unknown_if_missing_info": True, "max_confidence_if_uncertain": 0.5}
    result = score_testcase("prompt", expected, "Maybe", refusal=False, confidence=0.4)
    assert result.scores["overconfidence"] is True
