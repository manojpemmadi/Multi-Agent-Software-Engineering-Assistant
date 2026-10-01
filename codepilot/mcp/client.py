"""MCP Client enforcing role-based permissions independently of the LLM."""

import logging
from typing import Any, Dict, List, Optional, Set

from codepilot.mcp.server import MCPServerRegistry
from codepilot.models.schemas import AgentRole, ToolResult
from codepilot.workspace.manager import Workspace

logger = logging.getLogger(__name__)


# Declarative permission matrix: Independent permission boundaries
ROLE_PERMISSIONS: Dict[AgentRole, Set[str]] = {
    AgentRole.CODE_ANALYSIS: {
        "list_files",
        "view_tree",
        "read_file",
        "search_code",
        "git_status",
    },
    AgentRole.DEBUGGING: {
        "list_files",
        "view_tree",
        "read_file",
        "search_code",
        "write_file",
        "replace_file_content",
        "run_command",
        "git_status",
        "git_diff",
    },
    AgentRole.TESTING: {
        "list_files",
        "view_tree",
        "read_file",
        "search_code",
        "write_file",
        "replace_file_content",
        "run_tests",
        "run_command",
        "git_status",
        "git_diff",
    },
    AgentRole.ORCHESTRATOR: {
        "list_files",
        "view_tree",
        "read_file",
        "search_code",
        "git_status",
    },
}


class MCPClient:
    """Client interface through which agents invoke external capabilities via MCP."""

    def __init__(self, server: Optional[MCPServerRegistry] = None):
        self.server = server or MCPServerRegistry()

    def get_allowed_tools_for_role(self, role: AgentRole) -> List[Dict[str, Any]]:
        """Return MCP tool descriptors that this agent role is authorized to use."""
        allowed_names = ROLE_PERMISSIONS.get(role, set())
        all_tools = self.server.list_tools()
        return [t for t in all_tools if t["name"] in allowed_names]

    def is_tool_allowed(
        self,
        role: AgentRole,
        tool_name: str,
        step_allowed_tools: Optional[List[str]] = None,
    ) -> bool:
        """Verify role-level and step-level permission."""
        role_allowed = ROLE_PERMISSIONS.get(role, set())
        if tool_name not in role_allowed:
            return False

        if step_allowed_tools:
            return tool_name in step_allowed_tools

        return True

    def call_tool(
        self,
        role: AgentRole,
        tool_name: str,
        arguments: Dict[str, Any],
        workspace: Workspace,
        step_allowed_tools: Optional[List[str]] = None,
    ) -> ToolResult:
        """Execute a tool with independent role-based security validation."""
        # 1. Independent Permission Enforcement
        if not self.is_tool_allowed(role, tool_name, step_allowed_tools):
            logger.warning(
                "Permission Denied: Agent role '%s' attempted to call unauthorized tool '%s'.",
                role.value,
                tool_name,
            )
            role_allowed = sorted(list(ROLE_PERMISSIONS.get(role, set())))
            return ToolResult(
                tool_name=tool_name,
                is_error=True,
                output=(
                    f"PERMISSION DENIED: Agent role '{role.value}' is not permitted to execute tool '{tool_name}'. "
                    f"Allowed tools for your role are: {role_allowed}"
                ),
            )

        # 2. Dispatch to MCP Server
        logger.info(
            "Agent [%s] calling MCP tool '%s' on workspace '%s'",
            role.value,
            tool_name,
            workspace.workspace_id,
        )
        return self.server.execute_tool(tool_name, arguments, workspace)
