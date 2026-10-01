"""Unit tests for CodePilot structured schemas and Pydantic models."""

import pytest
from codepilot.models.schemas import (
    AgentResult,
    AgentRole,
    AgentTask,
    EvaluationCriteria,
    EvaluationResult,
    ExecutionPlan,
    FinalResult,
    PlanStep,
    TaskStatus,
    ToolCall,
    ValidationResult,
)


def test_plan_step_and_execution_plan():
    step1 = PlanStep(
        step_id=1,
        agent=AgentRole.CODE_ANALYSIS,
        objective="Analyze the repository architecture.",
        expected_output="Architectural findings.",
        dependencies=[],
        allowed_tools=["read_file", "search_code"],
    )
    step2 = PlanStep(
        step_id=2,
        agent=AgentRole.DEBUGGING,
        objective="Fix the defective login route.",
        expected_output="Patched file.",
        dependencies=[1],
        allowed_tools=["read_file", "write_file"],
    )

    plan = ExecutionPlan(
        user_intent="Fix broken login",
        steps=[step1, step2],
        estimated_complexity="low",
        rationale="Step-by-step fix",
    )

    assert len(plan.steps) == 2
    assert plan.steps[0].agent == AgentRole.CODE_ANALYSIS
    assert plan.steps[1].dependencies == [1]

    # Verify serialization
    data = plan.model_dump()
    assert data["estimated_complexity"] == "low"
    assert len(data["steps"]) == 2


def test_validation_result_categorization():
    val = ValidationResult(
        passed=False,
        test_framework="pytest",
        total_tests=5,
        passed_tests=4,
        failed_tests=1,
        failure_category="fix_failure",
        test_command="pytest -v",
        raw_output="FAILED test_login.py::test_auth - AssertionError",
    )
    assert not val.passed
    assert val.failed_tests == 1
    assert val.failure_category == "fix_failure"


def test_agent_result_structure():
    res = AgentResult(
        status=TaskStatus.SUCCESS,
        agent=AgentRole.DEBUGGING,
        summary="Repaired syntax error in calculate_discount",
        evidence="Colon added to function definition.",
        files_inspected=["main.py"],
        changes_made=[{"file_path": "main.py", "summary": "Added missing colon"}],
        confidence=0.98,
        recommended_next_action="Run tests",
        tool_calls_made=[
            ToolCall(call_id="c1", tool_name="write_file", arguments={"file_path": "main.py"})
        ],
    )
    assert res.status == TaskStatus.SUCCESS
    assert len(res.changes_made) == 1
    assert res.tool_calls_made[0].tool_name == "write_file"


def test_evaluation_result():
    crit = EvaluationCriteria(
        relevant_code_inspected=True,
        proposed_modification_addresses_problem=True,
        tests_executed=True,
        tests_passed=True,
        no_unresolved_errors=True,
        claims_supported_by_evidence=True,
    )
    eval_res = EvaluationResult(
        is_objective_completed=True,
        quality_score=0.95,
        criteria=crit,
        reasoning="All checks passed.",
        requires_retry=False,
    )
    assert eval_res.is_objective_completed
    assert not eval_res.requires_retry
    assert eval_res.quality_score == 0.95
