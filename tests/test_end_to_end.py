"""Integration tests for end-to-end multi-agent workflows."""

import pytest
from codepilot.llm.mock_provider import MockLLMService
from codepilot.mcp.client import MCPClient
from codepilot.models.schemas import (
    AgentRole,
    ExecutionPlan,
    InputMode,
    PlanStep,
    UserRequest,
)
from codepilot.orchestrator.orchestrator import MultiAgentOrchestrator
from codepilot.workspace.manager import WorkspaceManager


def test_end_to_end_syntax_error_workflow(tmp_path):
    """End-to-end scenario: Broken code pasted -> Multi-agent plan -> Fix -> Test -> Evaluation."""
    ws_mgr = WorkspaceManager(root_dir=tmp_path / "workspaces")
    mock_llm = MockLLMService()

    # Configure deterministic plan
    mock_llm.set_preset_structured(
        ExecutionPlan(
            user_intent="Fix syntax error and validate code",
            steps=[
                PlanStep(
                    step_id=1,
                    agent=AgentRole.CODE_ANALYSIS,
                    objective="Inspect syntax defect in main.py",
                    expected_output="Defect analysis",
                    dependencies=[],
                    allowed_tools=["read_file", "search_code", "view_tree"],
                ),
                PlanStep(
                    step_id=2,
                    agent=AgentRole.DEBUGGING,
                    objective="Correct missing colon and invalid syntax",
                    expected_output="Fixed main.py",
                    dependencies=[1],
                    allowed_tools=["read_file", "write_file", "list_files", "run_command", "git_diff"],
                ),
                PlanStep(
                    step_id=3,
                    agent=AgentRole.TESTING,
                    objective="Validate corrected code using test runner",
                    expected_output="Test execution evidence",
                    dependencies=[2],
                    allowed_tools=["read_file", "write_file", "list_files", "run_tests", "run_command"],
                ),
            ],
            estimated_complexity="low",
            rationale="3-stage fix and validation pipeline",
        )
    )

    orchestrator = MultiAgentOrchestrator(
        llm_service=mock_llm,
        workspace_manager=ws_mgr,
    )

    broken_code = "def calculate_discount(price, rate)\n    return price * (1 - rate)\n"
    req = UserRequest(
        message="This code is throwing a syntax error; correct it and make sure it works.",
        input_mode=InputMode.PASTE_CODE,
        code_snippet=broken_code,
        error_message="SyntaxError: expected ':' at line 1",
    )

    events_captured = []
    result = orchestrator.run(req, event_callback=lambda ev: events_captured.append(ev))

    # Assertions on final result
    assert result.success is True
    assert result.solution_code is not None
    assert len(events_captured) >= 5

    # Check step events were emitted
    step_names = [ev.step for ev in events_captured]
    assert "workspace" in step_names
    assert "planning" in step_names
    assert "evaluation" in step_names
