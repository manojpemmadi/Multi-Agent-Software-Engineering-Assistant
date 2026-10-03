"""Agent Registry: Declarative capabilities, responsibilities, and tool permissions."""

from typing import Any, Dict, List, Optional, Set, Tuple
from codepilot.mcp.client import ROLE_PERMISSIONS
from codepilot.models.schemas import AgentRole, ExecutionPlan, PlanStep


class AgentCapability:
    """Describes an agent's domain, responsibilities, and capabilities."""

    def __init__(
        self,
        role: AgentRole,
        title: str,
        description: str,
        responsibilities: List[str],
        allowed_tools: Set[str],
    ):
        self.role = role
        self.title = title
        self.description = description
        self.responsibilities = responsibilities
        self.allowed_tools = allowed_tools

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "title": self.title,
            "description": self.description,
            "responsibilities": self.responsibilities,
            "allowed_tools": sorted(list(self.allowed_tools)),
        }


class AgentRegistry:
    """Central registry describing worker agents and validating execution plans."""

    def __init__(self):
        self._registry: Dict[AgentRole, AgentCapability] = {
            AgentRole.CODE_ANALYSIS: AgentCapability(
                role=AgentRole.CODE_ANALYSIS,
                title="Code Analysis Agent",
                description="Understands unfamiliar codebases, scans architectures, traces execution flows, searches symbols, and localizes defects using RAG and file inspection.",
                responsibilities=[
                    "Inspect repository structure and read code files.",
                    "Search for functions, classes, error strings, and symbols.",
                    "Analyze dependencies, architecture, and control flow.",
                    "Localize root cause or defect locations for other agents.",
                ],
                allowed_tools=ROLE_PERMISSIONS[AgentRole.CODE_ANALYSIS],
            ),
            AgentRole.DEBUGGING: AgentCapability(
                role=AgentRole.DEBUGGING,
                title="Debugging / Fixing Agent",
                description="Diagnoses software defects, investigates error traces, produces controlled surgical code modifications, and verifies syntax.",
                responsibilities=[
                    "Investigate root cause of bugs, syntax errors, and runtime exceptions.",
                    "Discover and inspect relevant workspace files before diagnosing a defect.",
                    "Formulate precise surgical patches and modifications.",
                    "Apply changes using controlled MCP file write/edit tools.",
                    "Verify syntax and check compilation.",
                ],
                allowed_tools=ROLE_PERMISSIONS[AgentRole.DEBUGGING],
            ),
            AgentRole.TESTING: AgentCapability(
                role=AgentRole.TESTING,
                title="Testing / Validation Agent",
                description="Constructs automated unit/integration tests, runs test suites, captures execution evidence, and checks for regressions.",
                responsibilities=[
                    "Determine test requirements covering normal, edge, and failure cases.",
                    "Generate or modify test files using MCP tools.",
                    "Execute test suites (pytest, npm test, etc.) and inspect output.",
                    "Categorize failures (fix failure, unrelated failure, environment issue).",
                ],
                allowed_tools=ROLE_PERMISSIONS[AgentRole.TESTING],
            ),
        }

    def get_agent_capability(self, role: AgentRole) -> Optional[AgentCapability]:
        return self._registry.get(role)

    def get_prompt_description(self) -> str:
        """Format the registry into a prompt-friendly string for the LLM Planner."""
        blocks = []
        for role, cap in self._registry.items():
            tools = ", ".join(sorted(list(cap.allowed_tools)))
            resps = "\n  - ".join(cap.responsibilities)
            blocks.append(
                f"- Role: '{role.value}' ({cap.title})\n"
                f"  Description: {cap.description}\n"
                f"  Responsibilities:\n  - {resps}\n"
                f"  Authorized MCP tools (exact names): [{tools}]"
            )
        return "\n\n".join(blocks)

    def validate_plan(self, plan: ExecutionPlan) -> Tuple[bool, List[str]]:
        """Validate that all planned steps target registered agents and legitimate tools."""
        errors: List[str] = []
        seen_step_ids: Set[int] = set()

        if not plan.steps:
            errors.append("Execution plan cannot have zero steps.")
            return False, errors

        for step in plan.steps:
            if step.step_id in seen_step_ids:
                errors.append(f"Duplicate step_id {step.step_id} found in plan.")
            seen_step_ids.add(step.step_id)

            # Validate agent role
            if step.agent not in self._registry:
                errors.append(
                    f"Step {step.step_id} specifies unknown agent role '{step.agent}'. "
                    f"Must be one of {[r.value for r in self._registry.keys()]}"
                )
                continue

            cap = self._registry[step.agent]

            # Validate allowed_tools
            for tool_name in step.allowed_tools:
                if tool_name not in cap.allowed_tools:
                    errors.append(
                        f"Step {step.step_id} assigns tool '{tool_name}' to agent '{step.agent.value}', "
                        f"which exceeds the agent's declared permissions: {sorted(list(cap.allowed_tools))}"
                    )

            # Validate dependencies
            for dep_id in step.dependencies:
                if dep_id >= step.step_id or dep_id not in seen_step_ids:
                    errors.append(
                        f"Step {step.step_id} has invalid dependency {dep_id}. Dependencies must precede the step."
                    )

        return len(errors) == 0, errors
