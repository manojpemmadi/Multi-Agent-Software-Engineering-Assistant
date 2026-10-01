"""Unit tests for the Final Evaluation stage."""

import pytest
from codepilot.models.schemas import (
    AgentResult,
    AgentRole,
    TaskStatus,
    ToolCall,
    UserRequest,
    ValidationResult,
)
from codepilot.orchestrator.evaluator import FinalEvaluator


def test_evaluator_approves_successful_validation():
    evaluator = FinalEvaluator()
    req = UserRequest(message="Fix defective calculation")

    agent_results = [
        AgentResult(
            status=TaskStatus.SUCCESS,
            agent=AgentRole.CODE_ANALYSIS,
            summary="Identified bug in add()",
            evidence="Function inspected",
            files_inspected=["math_ops.py"],
            tool_calls_made=[ToolCall(call_id="1", tool_name="read_file")],
        ),
        AgentResult(
            status=TaskStatus.SUCCESS,
            agent=AgentRole.DEBUGGING,
            summary="Fixed return value",
            evidence="Diff verified",
            files_inspected=["math_ops.py"],
            changes_made=[{"file_path": "math_ops.py", "summary": "Changed return"}],
            tool_calls_made=[ToolCall(call_id="2", tool_name="write_file")],
        ),
        AgentResult(
            status=TaskStatus.SUCCESS,
            agent=AgentRole.TESTING,
            summary="All tests passed",
            evidence="pytest passed",
            files_inspected=["test_math.py"],
            validation=ValidationResult(
                passed=True,
                test_framework="pytest",
                total_tests=3,
                passed_tests=3,
                failed_tests=0,
                error_tests=0,
            ),
            tool_calls_made=[ToolCall(call_id="3", tool_name="run_tests")],
        ),
    ]

    eval_res = evaluator.evaluate(req, agent_results, current_retry_count=0)
    assert eval_res.is_objective_completed
    assert not eval_res.requires_retry
    assert eval_res.quality_score >= 0.8
    assert eval_res.criteria.tests_passed
    assert eval_res.criteria.proposed_modification_addresses_problem


def test_evaluator_flags_test_failure_for_retry():
    evaluator = FinalEvaluator()
    req = UserRequest(message="Fix authentication error")

    agent_results = [
        AgentResult(
            status=TaskStatus.NEEDS_RETRY,
            agent=AgentRole.TESTING,
            summary="Tests failed with assertion error",
            evidence="AssertionError in test_login",
            files_inspected=["test_auth.py"],
            validation=ValidationResult(
                passed=False,
                test_framework="pytest",
                total_tests=2,
                passed_tests=1,
                failed_tests=1,
                failure_category="fix_failure",
                raw_output="AssertionError: expected True but got False",
            ),
            tool_calls_made=[ToolCall(call_id="1", tool_name="run_tests")],
        )
    ]

    eval_res = evaluator.evaluate(req, agent_results, current_retry_count=0, max_retries=3)
    assert not eval_res.is_objective_completed
    assert eval_res.requires_retry
    assert eval_res.retry_target_agent == AgentRole.DEBUGGING
    assert "AssertionError" in eval_res.retry_guidance
