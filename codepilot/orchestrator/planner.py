"""LLM-Powered Planner: Generates structured multi-agent plans based on declared capabilities."""

import json
import logging
from typing import Any, Dict, Optional

from codepilot.llm.base import BaseLLMService
from codepilot.models.schemas import ExecutionPlan, PlanStep, UserRequest
from codepilot.orchestrator.agent_registry import AgentRegistry

logger = logging.getLogger(__name__)


class LLMPlanner:
    """Uses LLM reasoning to decompose user requests into structured, validated agent workflows."""

    def __init__(self, llm_service: BaseLLMService, registry: Optional[AgentRegistry] = None):
        self.llm_service = llm_service
        self.registry = registry or AgentRegistry()

    def create_plan(
        self,
        request: UserRequest,
        workspace_context: Dict[str, Any],
    ) -> ExecutionPlan:
        """Ask LLM to formulate an execution plan and validate it against the Agent Registry."""
        capabilities_text = self.registry.get_prompt_description()

        system_prompt = (
            "You are the Orchestration Planner in CodePilot, an autonomous multi-agent software engineering system.\n"
            "Your job is to reason about the user's objective and construct an optimal, dependency-ordered "
            "execution plan using ONLY the registered worker agents and their declared capabilities.\n"
            "CRITICAL RULES:\n"
            "- NEVER use hardcoded keyword matching. Reason directly about the technical problem.\n"
            "- Select agents solely based on their declared capabilities.\n"
            "- Ensure step dependencies form a valid DAG (dependencies must reference prior step IDs).\n"
            "- allowed_tools is an enforced authorization boundary for that specific step, not a suggestion.\n"
            "- Include every registered MCP tool that the assigned agent needs for its specific objective; "
            "the agent cannot request tools omitted from allowed_tools.\n"
            "- For existing-codebase inspection or debugging, include the required discovery/inspection tools "
            "from the assigned role's authorized tools, such as list_files, view_tree, read_file, and search_code.\n"
            "- Every Debugging / Fixing step must include list_files: that agent calls it before it can discover files. "
            "Also include read_file, write_file, and git_diff when the step inspects and modifies workspace code; "
            "include run_command when syntax or command validation is required.\n"
            "- For code modifications, include the authorized write/replace tools the agent needs.\n"
            "- For testing, include authorized source inspection and test execution tools needed for that step.\n"
            "- Select a sensible least-privilege subset; do not grant every role every tool.\n"
            "- Never assign a tool that is not listed for the selected role in REGISTERED AGENTS & CAPABILITIES.\n"
            "- Typical workflows:\n"
            "  * Bug fix / error: Code Analysis -> Debugging / Fixing -> Testing / Validation\n"
            "  * Codebase question: Code Analysis\n"
            "  * Syntax error fix: Debugging / Fixing -> Testing / Validation\n"
            "  * Add tests: Testing / Validation\n"
        )

        prompt = f"""
USER REQUEST:
Message: {request.message}
Input Mode: {request.input_mode.value}
Error Description: {request.error_message or 'None'}
Code Snippet Provided: {'Yes (' + str(len(request.code_snippet or '')) + ' chars)' if request.code_snippet else 'No'}
GitHub Repo: {request.github_url or 'None'}

WORKSPACE METADATA:
Language / Ecosystem: {workspace_context.get('language', 'unknown')}
Files Detected: {workspace_context.get('files_count', 0)}
Has Existing Tests: {workspace_context.get('has_tests', False)}

REGISTERED AGENTS & CAPABILITIES:
{capabilities_text}

Generate a comprehensive ExecutionPlan matching the ExecutionPlan schema.
"""

        try:
            plan = self.llm_service.generate_structured(
                prompt=prompt,
                response_model=ExecutionPlan,
                system_prompt=system_prompt,
                temperature=0.1,
            )
        except RuntimeError as e:
            logger.warning("Structured plan generation failed, falling back to heuristic plan: %s", e)
            plan = self._fallback_plan(request, workspace_context)

        # Validate plan against Agent Registry
        is_valid, errors = self.registry.validate_plan(plan)
        if not is_valid:
            logger.warning("Generated plan had validation issues: %s. Sanitizing...", errors)
            plan = self._sanitize_plan(plan)

        return plan

    def _fallback_plan(self, request: UserRequest, workspace_context: Dict[str, Any]) -> ExecutionPlan:
        """Reliable fallback if LLM is unavailable or fails structured schema."""
        from codepilot.models.schemas import AgentRole

        steps = []
        step_id = 1

        # If repo or broad query, analyze first
        if request.github_url or workspace_context.get("files_count", 0) > 1:
            steps.append(
                PlanStep(
                    step_id=step_id,
                    agent=AgentRole.CODE_ANALYSIS,
                    objective=f"Analyze codebase structure and trace: {request.message}",
                    expected_output="Architectural overview and suspect defect locations.",
                    dependencies=[],
                    allowed_tools=["read_file", "search_code", "view_tree", "list_files"],
                )
            )
            step_id += 1

        # If bug, error, or code fix requested
        steps.append(
            PlanStep(
                step_id=step_id,
                agent=AgentRole.DEBUGGING,
                objective=f"Diagnose and correct the defect: {request.message}",
                expected_output="Repaired code with verified syntax.",
                dependencies=[step_id - 1] if step_id > 1 else [],
                allowed_tools=[
                    "list_files",
                    "view_tree",
                    "read_file",
                    "search_code",
                    "write_file",
                    "replace_file_content",
                    "run_command",
                    "git_status",
                    "git_diff",
                ],
            )
        )
        step_id += 1

        # Always validate with tests
        steps.append(
            PlanStep(
                step_id=step_id,
                agent=AgentRole.TESTING,
                objective="Execute automated tests to validate the correction and ensure no regressions.",
                expected_output="Test execution report with pass/fail evidence.",
                dependencies=[step_id - 1],
                allowed_tools=["read_file", "write_file", "run_tests", "run_command"],
            )
        )

        return ExecutionPlan(
            user_intent=request.message,
            steps=steps,
            estimated_complexity="medium",
            rationale="Robust fallback plan spanning inspection, debugging, and automated test validation.",
        )

    def _sanitize_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Sanitize tools and dependencies in plan to conform strictly to registry."""
        sanitized_steps = []
        seen_ids = set()

        for step in plan.steps:
            seen_ids.add(step.step_id)
            cap = self.registry.get_agent_capability(step.agent)
            if not cap:
                continue

            valid_tools = [t for t in step.allowed_tools if t in cap.allowed_tools]
            valid_deps = [d for d in step.dependencies if d < step.step_id and d in seen_ids]

            step.allowed_tools = valid_tools
            step.dependencies = valid_deps
            sanitized_steps.append(step)

        plan.steps = sanitized_steps
        return plan
