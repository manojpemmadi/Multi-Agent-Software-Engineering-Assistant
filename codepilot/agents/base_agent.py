"""Base agent class providing tool calling loop and structured output."""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from codepilot.llm.base import BaseLLMService
from codepilot.mcp.client import MCPClient
from codepilot.models.schemas import (
    AgentResult,
    AgentRole,
    AgentTask,
    TaskStatus,
    ToolCall,
    ToolResult,
)
from codepilot.workspace.manager import Workspace

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all specialized worker agents."""

    def __init__(
        self,
        role: AgentRole,
        llm_service: BaseLLMService,
        mcp_client: MCPClient,
        max_tool_steps: int = 5,
    ):
        self.role = role
        self.llm_service = llm_service
        self.mcp_client = mcp_client
        self.max_tool_steps = max_tool_steps

    @abstractmethod
    def get_system_prompt(self, task: AgentTask) -> str:
        """Provide specialized role-specific system instructions."""
        pass

    @abstractmethod
    def run(self, task: AgentTask, workspace: Workspace) -> AgentResult:
        """Execute the agent's assigned task using LLM reasoning and MCP tools."""
        pass

    def get_allowed_tool_descriptions(self, step_tools: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Retrieve MCP tool schemas permitted for this agent's role."""
        allowed = self.mcp_client.get_allowed_tools_for_role(self.role)
        if step_tools is not None:
            allowed = [t for t in allowed if t["name"] in step_tools]
        return allowed

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        workspace: Workspace,
        step_tools: Optional[List[str]] = None,
    ) -> ToolResult:
        """Invoke an MCP tool through the permission-enforcing MCP client."""
        return self.mcp_client.call_tool(
            role=self.role,
            tool_name=tool_name,
            arguments=arguments,
            workspace=workspace,
            step_allowed_tools=step_tools,
        )
