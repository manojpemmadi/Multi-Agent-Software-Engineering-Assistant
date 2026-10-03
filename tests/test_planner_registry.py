"""Unit tests for Agent Registry and LLM Planner."""

import pytest
from unittest.mock import Mock

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


def test_planner_falls_back_when_llm_generation_fails(monkeypatch):
    mock_llm = MockLLMService()
    monkeypatch.setattr(
        mock_llm,
        "generate_structured",
        Mock(side_effect=RuntimeError("Gemini API unavailable")),
    )
    planner = LLMPlanner(llm_service=mock_llm)

    plan = planner.create_plan(
        UserRequest(message="Explain this repository"),
        {"language": "python", "files_count": 1},
    )

    assert plan.rationale == "Robust fallback plan spanning inspection, debugging, and automated test validation."


def test_planner_does_not_mask_unexpected_errors(monkeypatch):
    mock_llm = MockLLMService()
    monkeypatch.setattr(
        mock_llm,
        "generate_structured",
        Mock(side_effect=ValueError("Unexpected planner bug")),
    )
    planner = LLMPlanner(llm_service=mock_llm)

    with pytest.raises(ValueError, match="Unexpected planner bug"):
        planner.create_plan(
            UserRequest(message="Explain this repository"),
            {"language": "python", "files_count": 1},
        )


def test_registry_prompt_lists_debugging_capabilities_and_authorized_tools():
    prompt_description = AgentRegistry().get_prompt_description()

    assert "Debugging / Fixing Agent" in prompt_description
    assert "Discover and inspect relevant workspace files" in prompt_description
    assert "Authorized MCP tools (exact names)" in prompt_description
    for tool in ("list_files", "view_tree", "read_file", "search_code", "write_file", "git_diff"):
        assert tool in prompt_description


def test_planner_supplies_registered_tools_and_step_boundary_to_llm():
    mock_llm = MockLLMService()
    planner = LLMPlanner(llm_service=mock_llm)

    planner.create_plan(
        UserRequest(message="Fix the bug in this repository"),
        {"language": "python", "files_count": 3},
    )

    call = mock_llm.history[-1]
    assert "Authorized MCP tools (exact names)" in call["prompt"]
    assert "list_files" in call["prompt"]
    assert "allowed_tools is an enforced authorization boundary" in call["system_prompt"]
    assert "agent cannot request tools omitted from allowed_tools" in call["system_prompt"]
    assert "Every Debugging / Fixing step must include list_files" in call["system_prompt"]


def test_fallback_debugging_plan_includes_repository_inspection_tools():
    planner = LLMPlanner(llm_service=MockLLMService())
    request = UserRequest(message="Find and fix the defect")

    plan = planner._fallback_plan(request, {"language": "python", "files_count": 1})
    debug_step = next(step for step in plan.steps if step.agent == AgentRole.DEBUGGING)

    required_tools = {
        "list_files",
        "view_tree",
        "read_file",
        "search_code",
        "write_file",
        "replace_file_content",
        "run_command",
        "git_status",
        "git_diff",
    }
    assert required_tools.issubset(debug_step.allowed_tools)
    assert AgentRegistry().validate_plan(plan)[0]


def test_plan_sanitization_removes_invalid_tools_without_expanding_permissions():
    planner = LLMPlanner(llm_service=MockLLMService())
    plan = ExecutionPlan(
        user_intent="Inspect and fix",
        steps=[
            PlanStep(
                step_id=1,
                agent=AgentRole.DEBUGGING,
                objective="Inspect and fix a defect",
                expected_output="Corrected code",
                allowed_tools=["list_files", "write_file", "not_a_real_tool"],
            ),
            PlanStep(
                step_id=2,
                agent=AgentRole.DEBUGGING,
                objective="No tools requested",
                expected_output="No tool calls",
                dependencies=[1],
                allowed_tools=["not_a_real_tool"],
            ),
        ],
        estimated_complexity="low",
        rationale="Invalid tool sanitization test",
    )

    sanitized = planner._sanitize_plan(plan)

    assert sanitized.steps[0].allowed_tools == ["list_files", "write_file"]
    assert sanitized.steps[1].allowed_tools == []
