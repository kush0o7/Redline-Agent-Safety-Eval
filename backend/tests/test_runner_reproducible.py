import asyncio
import uuid

from app.db.models import Run, Testcase, RunResult
from app.evals.generators import create_prompt_injection_cases
from app.evals.runner import execute_run


def test_generators_deterministic():
    cases_a = create_prompt_injection_cases(3, seed=42)
    cases_b = create_prompt_injection_cases(3, seed=42)
    assert cases_a == cases_b


def test_runner_reproducible(db):
    project_id = uuid.uuid4()
    tc1 = Testcase(
        id=uuid.uuid4(),
        project_id=project_id,
        type="hallucination",
        name="t1",
        prompt="Prompt A",
        expected_behavior={"should_refuse": False, "should_use_unknown_if_missing_info": True},
        severity=1,
        tags=[],
    )
    tc2 = Testcase(
        id=uuid.uuid4(),
        project_id=project_id,
        type="hallucination",
        name="t2",
        prompt="Prompt B",
        expected_behavior={"should_refuse": False, "should_use_unknown_if_missing_info": True},
        severity=1,
        tags=[],
    )
    db.add_all([tc1, tc2])
    db.commit()

    run1 = Run(project_id=project_id, mode="baseline", llm_model="fake", seed=7, status="running")
    run2 = Run(project_id=project_id, mode="baseline", llm_model="fake", seed=7, status="running")
    db.add_all([run1, run2])
    db.commit()

    asyncio.run(execute_run(db, run1, [tc1, tc2]))
    results1 = db.query(RunResult).filter(RunResult.run_id == run1.id).order_by(RunResult.testcase_id).all()

    asyncio.run(execute_run(db, run2, [tc1, tc2]))
    results2 = db.query(RunResult).filter(RunResult.run_id == run2.id).order_by(RunResult.testcase_id).all()

    assert [r.raw_output for r in results1] == [r.raw_output for r in results2]
