"""Code Analysis Agent: Specializes in codebase understanding, RAG reasoning, and execution tracing."""

import json
import logging
from typing import Any, Dict, List

from codepilot.agents.base_agent import BaseAgent
from codepilot.llm.base import BaseLLMService
from codepilot.mcp.client import MCPClient
from codepilot.models.schemas import (
    AgentResult,
    AgentRole,
    AgentTask,
    TaskStatus,
    ToolCall,
)
from codepilot.workspace.manager import Workspace

logger = logging.getLogger(__name__)


class CodeAnalysisAgent(BaseAgent):
    """Specialist worker agent for repository understanding, dependency tracing, and problem localization."""

    def __init__(self, llm_service: BaseLLMService, mcp_client: MCPClient):
        super().__init__(role=AgentRole.CODE_ANALYSIS, llm_service=llm_service, mcp_client=mcp_client)

    def get_system_prompt(self, task: AgentTask) -> str:
        return (
            "You are the Code Analysis Agent in CodePilot, a specialized AI software engineer.\n"
            "Your role is to deeply analyze unfamiliar codebases, locate defects, trace execution paths, "
            "and examine architecture and dependencies.\n"
            "Rules:\n"
            "- Never hallucinate files, symbols, or functions.\n"
            "- Ground all your findings on actual files read or searched.\n"
            "- Reason thoroughly over code structure, control flow, and edge cases.\n"
            "- Provide structured findings: relevant files, suspect functions/lines, potential failure causes, and confidence.\n"
        )

    def run(self, task: AgentTask, workspace: Workspace) -> AgentResult:
        logger.info("[CodeAnalysisAgent] Beginning analysis for task: %s", task.objective)
        files_inspected: List[str] = []
        tool_calls_made: List[ToolCall] = []

        # 1. Inspect workspace structure
        tree_res = self.execute_tool("view_tree", {"subpath": ".", "max_depth": 3}, workspace, task.allowed_tools)
        tool_calls_made.append(ToolCall(call_id="call_tree", tool_name="view_tree", arguments={"max_depth": 3}))

        # 2. Gather relevant code context from RAG chunks
        rag_context_blocks = []
        for chunk in task.retrieved_code_chunks:
            f_path = chunk.get("file_path", "")
            if f_path and f_path not in files_inspected:
                files_inspected.append(f_path)
            rag_context_blocks.append(
                f"FILE: {f_path} (lines {chunk.get('start_line', '?')}-{chunk.get('end_line', '?')})\n"
                f"SYMBOLS: {chunk.get('symbols', 'none')}\n"
                f"CODE:\n{chunk.get('text', '')}\n"
            )

        # 3. If RAG chunks are sparse or empty, inspect files or search for symbols via MCP
        if not rag_context_blocks:
            # Check files in root
            list_res = self.execute_tool("list_files", {"subpath": ".", "max_depth": 2}, workspace, task.allowed_tools)
            tool_calls_made.append(ToolCall(call_id="call_list", tool_name="list_files", arguments={"max_depth": 2}))
            items = list_res.structured_data.get("items", []) if list_res.structured_data else []
            for item in items[:5]:
                if item.get("type") == "file":
                    p = item["path"]
                    r_res = self.execute_tool("read_file", {"file_path": p, "start_line": 1, "end_line": 150}, workspace, task.allowed_tools)
                    tool_calls_made.append(ToolCall(call_id=f"call_read_{p}", tool_name="read_file", arguments={"file_path": p}))
                    files_inspected.append(p)
                    rag_context_blocks.append(f"FILE: {p}\nCODE:\n{r_res.output}\n")

        rag_text = "\n---\n".join(rag_context_blocks) if rag_context_blocks else "No prior chunks indexed."

        # 4. Prompt LLM to reason over retrieved context and workspace structure
        analysis_prompt = f"""
TASK OBJECTIVE:
{task.objective}

WORKSPACE STRUCTURE:
{tree_res.output}

RETRIEVED CODE CONTEXT:
{rag_text}

FEEDBACK / RETRY CONTEXT (IF ANY):
{task.feedback or 'None'}

Please provide a structured, in-depth technical analysis addressing:
1. Architecture and key components involved.
2. Localization of defect or target functions/classes.
3. Suspected execution flow and failure mechanism.
4. Concrete recommendation for the Debugging Agent.
"""

        system_prompt = self.get_system_prompt(task)
        llm_response = self.llm_service.generate_text(
            prompt=analysis_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
        )

        return AgentResult(
            status=TaskStatus.SUCCESS,
            agent=self.role,
            summary=f"Completed architectural and code analysis for: {task.objective[:80]}...",
            evidence=llm_response,
            files_inspected=files_inspected,
            confidence=0.92,
            recommended_next_action="Pass findings to DebuggingAgent to implement required patch or fix.",
            tool_calls_made=tool_calls_made,
        )
