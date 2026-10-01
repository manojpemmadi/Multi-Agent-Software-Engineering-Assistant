"""Testing/Validation Agent: Specializes in automated validation, test generation, and regression detection."""

import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from codepilot.agents.base_agent import BaseAgent
from codepilot.llm.base import BaseLLMService
from codepilot.mcp.client import MCPClient
from codepilot.models.schemas import (
    AgentResult,
    AgentRole,
    AgentTask,
    TaskStatus,
    ToolCall,
    ValidationResult,
)
from codepilot.workspace.detector import ProjectDetector
from codepilot.workspace.manager import Workspace

logger = logging.getLogger(__name__)


class TestSuiteProposal(BaseModel):
    """Structured test suite generated or updated by Testing Agent."""
    test_file_path: str = Field(description="Relative path of test file, e.g. test_main.py")
    test_code: str = Field(description="Full runnable test code covering normal, edge, and failure cases")
    coverage_explanation: str = Field(description="Summary of test cases covered")


class TestingAgent(BaseAgent):
    """Specialist worker agent for test execution, verification, and regression detection."""

    def __init__(self, llm_service: BaseLLMService, mcp_client: MCPClient):
        super().__init__(role=AgentRole.TESTING, llm_service=llm_service, mcp_client=mcp_client)

    def get_system_prompt(self, task: AgentTask) -> str:
        return (
            "You are the Testing/Validation Agent in CodePilot.\n"
            "Your responsibility is to rigorously validate software fixes and detect regressions.\n"
            "Rules:\n"
            "- Never declare code 'looks good' without tool test execution evidence.\n"
            "- Always construct tests that probe: normal cases, edge cases, invalid inputs, and regression cases.\n"
            "- Distinguish between: fix failure, existing unrelated failure, and environment dependency failure.\n"
            "- Ground all your judgments on executed test runner outputs.\n"
        )

    def run(self, task: AgentTask, workspace: Workspace) -> AgentResult:
        logger.info("[TestingAgent] Beginning validation for task: %s", task.objective)
        files_inspected: List[str] = []
        tool_calls_made: List[ToolCall] = []

        eco = ProjectDetector.detect(str(workspace.root_path))
        lang = eco.get("language", "python")

        # 1. Search for existing tests in workspace
        list_res = self.execute_tool("list_files", {"subpath": ".", "max_depth": 3}, workspace, task.allowed_tools)
        tool_calls_made.append(ToolCall(call_id="call_list", tool_name="list_files", arguments={"max_depth": 3}))
        items = list_res.structured_data.get("items", []) if list_res.structured_data else []

        test_files = [
            it["path"] for it in items
            if it.get("type") == "file" and ("test" in it["path"].lower() or "spec" in it["path"].lower())
        ]
        code_files = [
            it["path"] for it in items
            if it.get("type") == "file" and it["path"] not in test_files
        ]

        # 2. Inspect implementation code to formulate comprehensive test cases
        impl_context = {}
        for p in (code_files[:3] + test_files[:2]):
            r_res = self.execute_tool("read_file", {"file_path": p}, workspace, task.allowed_tools)
            tool_calls_made.append(ToolCall(call_id=f"call_read_{p}", tool_name="read_file", arguments={"file_path": p}))
            files_inspected.append(p)
            impl_context[p] = r_res.output

        # 3. If no dedicated test file exists or only a basic import test exists, ask LLM to generate targeted unit tests
        needs_more_tests = not test_files or all("spec.loader.exec_module" in impl_context.get(tf, "") for tf in test_files)
        if needs_more_tests and lang == "python":
            prompt = f"""
TASK OBJECTIVE:
{task.objective}

IMPLEMENTATION FILES:
{json.dumps(impl_context, indent=2)}

Create a comprehensive pytest test suite file (e.g. 'test_solution.py') testing the code above.
Cover:
1. Normal typical execution
2. Edge cases (empty, boundary, zero, special characters)
3. Error handling and exceptions
"""
            system_prompt = self.get_system_prompt(task)
            try:
                proposal: TestSuiteProposal = self.llm_service.generate_structured(
                    prompt=prompt,
                    response_model=TestSuiteProposal,
                    system_prompt=system_prompt,
                    temperature=0.1,
                )
                t_path = proposal.test_file_path or "test_solution.py"
                w_res = self.execute_tool(
                    "write_file",
                    {"file_path": t_path, "content": proposal.test_code, "overwrite": True},
                    workspace,
                    task.allowed_tools,
                )
                tool_calls_made.append(ToolCall(call_id=f"call_write_test_{t_path}", tool_name="write_file", arguments={"file_path": t_path}))
                test_files.append(t_path)
            except Exception as e:
                logger.warning("Automated test generation failed: %s", e)

        # 4. Execute test suite via MCP run_tests tool
        test_res = self.execute_tool("run_tests", {}, workspace, task.allowed_tools)
        tool_calls_made.append(ToolCall(call_id="call_run_tests", tool_name="run_tests", arguments={}))

        raw_val = test_res.structured_data.get("validation", {}) if test_res.structured_data else {}
        passed = test_res.structured_data.get("passed", False) if test_res.structured_data else False

        val_result = ValidationResult(
            passed=passed,
            test_framework=raw_val.get("test_framework", "pytest"),
            total_tests=raw_val.get("total_tests", 0),
            passed_tests=raw_val.get("passed_tests", 0),
            failed_tests=raw_val.get("failed_tests", 0),
            error_tests=raw_val.get("error_tests", 0),
            failure_category=raw_val.get("failure_category", "none" if passed else "fix_failure"),
            test_command=raw_val.get("test_command", "pytest -v"),
            raw_output=test_res.output,
            details=raw_val.get("details", []),
        )

        status = TaskStatus.SUCCESS if passed else TaskStatus.NEEDS_RETRY
        summary = (
            f"Test execution PASSED: {val_result.passed_tests}/{val_result.total_tests} tests succeeded."
            if passed
            else f"Test execution FAILED: {val_result.failed_tests} failed, {val_result.error_tests} errors (Category: {val_result.failure_category})."
        )

        next_action = (
            "Validation successful. Ready for final evaluation."
            if passed
            else "Feed test failure output back into DebuggingAgent to revise code fix."
        )

        return AgentResult(
            status=status,
            agent=self.role,
            summary=summary,
            evidence=test_res.output,
            files_inspected=files_inspected,
            tests_executed=test_files,
            validation=val_result,
            confidence=0.98 if passed else 0.4,
            recommended_next_action=next_action,
            tool_calls_made=tool_calls_made,
            errors=[test_res.output] if not passed else [],
        )
