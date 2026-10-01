"""Unit tests for Agent Registry and LLM Planner."""

import pytest
from codepilot.llm.mock_provider import MockLLMService
from codepilot.models.schemas import AgentRole, ExecutionPlan, PlanStep, UserRequest
from codepilot.orchestrator.agent_registry import AgentRegistry
from codepilot.orchestrator.planner import LLMPlanner


def test_registry_plan_validation_success():
    registry = AgentRegistry()

    valid_plan = ExecutionPlan(
        user_intent="Investigate defect",
        steps=[
            PlanStep(
                step_id=1,
                agent=AgentRole.CODE_ANALYSIS,
                objective="Analyze file",
                expected_output="Analysis",
                dependencies=[],
                allowed_tools=["read_file", "search_code"],
            ),
            PlanStep(
                step_id=2,
                agent=AgentRole.DEBUGGING,
                objective="Patch code",
                expected_output="Patch",
                dependencies=[1],
                allowed_tools=["write_file", "read_file"],
            ),
        ],
        estimated_complexity="low",
        rationale="Standard 2-step flow",
    )

    is_valid, errors = registry.validate_plan(valid_plan)
    assert is_valid
    assert len(errors) == 0


def test_registry_plan_validation_unauthorized_tool():
    registry = AgentRegistry()

    # Step assigns write_file to code_analysis role (not allowed)
    invalid_plan = ExecutionPlan(
        user_intent="Inspect file",
        steps=[
            PlanStep(
                step_id=1,
                agent=AgentRole.CODE_ANALYSIS,
                objective="Analyze file",
                expected_output="Analysis",
                dependencies=[],
                allowed_tools=["write_file"],
            )
        ],
        estimated_complexity="low",
        rationale="Invalid tool assignment",
    )

    is_valid, errors = registry.validate_plan(invalid_plan)
    assert not is_valid
    assert any("exceeds the agent's declared permissions" in err for err in errors)


def test_registry_plan_validation_invalid_dependency():
    registry = AgentRegistry()

    # Step 1 depends on Step 2 (impossible forward dependency)
    invalid_plan = ExecutionPlan(
        user_intent="Flow",
        steps=[
            PlanStep(
                step_id=1,
                agent=AgentRole.CODE_ANALYSIS,
                objective="Step 1",
                expected_output="Out",
                dependencies=[2],
                allowed_tools=["read_file"],
            ),
            PlanStep(
                step_id=2,
                agent=AgentRole.DEBUGGING,
                objective="Step 2",
                expected_output="Out",
                dependencies=[],
                allowed_tools=["write_file"],
            ),
        ],
        estimated_complexity="low",
        rationale="Invalid ordering",
    )

    is_valid, errors = registry.validate_plan(invalid_plan)
    assert not is_valid
    assert any("invalid dependency" in err for err in errors)


def test_planner_creates_validated_plan():
    mock_llm = MockLLMService()
    planner = LLMPlanner(llm_service=mock_llm)

    req = UserRequest(message="Fix my syntax error in app.py")
    context = {"language": "python", "files_count": 2, "has_tests": True}

    plan = planner.create_plan(req, context)
    assert isinstance(plan, ExecutionPlan)
    assert len(plan.steps) >= 2

    # Verify every step has valid agent and allowed tools
    registry = AgentRegistry()
    is_valid, errors = registry.validate_plan(plan)
    assert is_valid, f"Plan validation errors: {errors}"
