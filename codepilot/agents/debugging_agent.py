"""Debugging/Fixing Agent: Specializes in defect diagnosis, controlled edits, and syntax verification."""

import json
import logging
import re
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
)
from codepilot.workspace.manager import Workspace

logger = logging.getLogger(__name__)


class ProposedFix(BaseModel):
    """Structured code modification proposed by the Debugging Agent."""
    target_file: str = Field(description="Relative path of file to modify")
    root_cause_analysis: str = Field(description="Explanation of the identified defect")
    complete_fixed_code: str = Field(description="Full corrected code for the file")
    summary_of_changes: str = Field(description="Concise description of edits")


class DebuggingAgent(BaseAgent):
    """Specialist worker agent for diagnosing and surgically repairing software defects."""

    def __init__(self, llm_service: BaseLLMService, mcp_client: MCPClient):
        super().__init__(role=AgentRole.DEBUGGING, llm_service=llm_service, mcp_client=mcp_client)

    def get_system_prompt(self, task: AgentTask) -> str:
        return (
            "You are the Debugging/Fixing Agent in CodePilot.\n"
            "Your objective is to diagnose the root cause of software errors, exceptions, or failures, "
            "and produce reliable, complete, and syntactically correct code modifications.\n"
            "Rules:\n"
            "- Connect reported errors and test failures directly to the code.\n"
            "- Never produce incomplete code, placeholders, or ellipsis like '// ... existing code ...'.\n"
            "- Always preserve existing imports and logic that were working correctly.\n"
            "- You must provide the full, valid corrected file content.\n"
            "- A bug is never considered fixed until changes are applied and verified.\n"
        )

    def run(self, task: AgentTask, workspace: Workspace) -> AgentResult:
        logger.info("[DebuggingAgent] Beginning debugging for task: %s", task.objective)
        files_inspected: List[str] = []
        tool_calls_made: List[ToolCall] = []

        # 1. Identify primary files in workspace to inspect
        list_res = self.execute_tool("list_files", {"subpath": ".", "max_depth": 2}, workspace, task.allowed_tools)
        tool_calls_made.append(ToolCall(call_id="call_list", tool_name="list_files", arguments={"max_depth": 2}))
        if list_res.is_error:
            return AgentResult(
                status=TaskStatus.FAILURE,
                agent=self.role,
                summary="Could not inspect workspace files; debugging stopped.",
                evidence=list_res.output,
                errors=[list_res.output],
                confidence=0.0,
                tool_calls_made=tool_calls_made,
            )
        items = list_res.structured_data.get("items", []) if list_res.structured_data else []

        code_files = [
            it["path"] for it in items
            if it.get("type") == "file" and not it["path"].startswith("test_")
        ]
        if not code_files:
            code_files = [it["path"] for it in items if it.get("type") == "file"]

        # Read contents of relevant files
        file_contents: Dict[str, str] = {}
        for p in code_files[:4]:
            r_res = self.execute_tool("read_file", {"file_path": p}, workspace, task.allowed_tools)
            tool_calls_made.append(ToolCall(call_id=f"call_read_{p}", tool_name="read_file", arguments={"file_path": p}))
            if r_res.is_error:
                return AgentResult(
                    status=TaskStatus.FAILURE,
                    agent=self.role,
                    summary=f"Could not read '{p}'; debugging stopped.",
                    evidence=r_res.output,
                    files_inspected=files_inspected,
                    errors=[r_res.output],
                    confidence=0.0,
                    tool_calls_made=tool_calls_made,
                )
            files_inspected.append(p)
            file_contents[p] = r_res.output

        context_str = "\n\n".join(f"=== FILE: {p} ===\n{content}" for p, content in file_contents.items())

        # 2. Formulate prompt for Gemini with structured output
        prompt = f"""
TASK OBJECTIVE:
{task.objective}

CONTEXT FROM PRIOR STEPS / RAG:
{json.dumps(task.context, indent=2) if task.context else 'None'}

FAILURE EVIDENCE / FEEDBACK (IF RETRY):
{task.feedback or 'No prior failures.'}

CURRENT WORKSPACE FILES:
{context_str}

Analyze the root cause, repair any syntax, logic, or runtime defects, and output the full corrected code.
"""

        system_prompt = self.get_system_prompt(task)

        try:
            fix: ProposedFix = self.llm_service.generate_structured(
                prompt=prompt,
                response_model=ProposedFix,
                system_prompt=system_prompt,
                temperature=0.1,
            )
        except Exception as e:
            logger.warning("Structured fix generation failed, falling back to text extraction: %s", e)
            # Text fallback
            text_resp = self.llm_service.generate_text(prompt=prompt, system_prompt=system_prompt)
            # Try to extract code block
            code_match = re.search(r"```(?:\w+)?\n([\s\S]+?)\n```", text_resp)
            target = code_files[0] if code_files else "main.py"
            fix = ProposedFix(
                target_file=target,
                root_cause_analysis="Analysis extracted from model generation.",
                complete_fixed_code=code_match.group(1) if code_match else text_resp,
                summary_of_changes="Applied recommended patch.",
            )

        # 3. Apply the fix using MCP write_file tool
        target_path = fix.target_file or (code_files[0] if code_files else "main.py")
        write_res = self.execute_tool(
            "write_file",
            {"file_path": target_path, "content": fix.complete_fixed_code, "overwrite": True},
            workspace,
            task.allowed_tools,
        )
        tool_calls_made.append(
            ToolCall(
                call_id=f"call_write_{target_path}",
                tool_name="write_file",
                arguments={"file_path": target_path, "bytes": len(fix.complete_fixed_code)},
            )
        )
        if write_res.is_error:
            return AgentResult(
                status=TaskStatus.FAILURE,
                agent=self.role,
                summary=f"Could not apply the proposed fix to '{target_path}'.",
                evidence=write_res.output,
                files_inspected=files_inspected,
                errors=[write_res.output],
                confidence=0.0,
                tool_calls_made=tool_calls_made,
            )

        # 4. Inspect diff using MCP git_diff
        diff_res = self.execute_tool("git_diff", {}, workspace, task.allowed_tools)
        tool_calls_made.append(ToolCall(call_id="call_diff", tool_name="git_diff", arguments={}))
        if diff_res.is_error:
            return AgentResult(
                status=TaskStatus.FAILURE,
                agent=self.role,
                summary="Could not verify the applied change with git diff.",
                evidence=diff_res.output,
                files_inspected=files_inspected,
                errors=[diff_res.output],
                confidence=0.0,
                tool_calls_made=tool_calls_made,
            )
        diff_text = diff_res.structured_data.get("diff", "") if diff_res.structured_data else diff_res.output

        # 5. Quick syntax validation if Python
        syntax_ok = True
        syntax_err = ""
        if target_path.endswith(".py"):
            compile_res = self.execute_tool(
                "run_command",
                {"command": f'python -m py_compile "{target_path}"'},
                workspace,
                task.allowed_tools,
            )
            tool_calls_made.append(ToolCall(call_id="call_syntax_check", tool_name="run_command", arguments={"command": "py_compile"}))
            if compile_res.is_error:
                return AgentResult(
                    status=TaskStatus.FAILURE,
                    agent=self.role,
                    summary=f"Could not validate syntax for '{target_path}'.",
                    evidence=compile_res.output,
                    files_inspected=files_inspected,
                    errors=[compile_res.output],
                    confidence=0.0,
                    tool_calls_made=tool_calls_made,
                )
            if not compile_res.structured_data.get("success", True):
                syntax_ok = False
                syntax_err = compile_res.output

        changes_made = [
            {
                "file_path": target_path,
                "summary": fix.summary_of_changes,
                "diff": diff_text or write_res.structured_data.get("diff", ""),
                "root_cause": fix.root_cause_analysis,
            }
        ]

        status = TaskStatus.SUCCESS if syntax_ok else TaskStatus.NEEDS_RETRY
        summary = (
            f"Diagnosed defect in '{target_path}' and applied patch: {fix.summary_of_changes}"
            if syntax_ok
            else f"Applied patch to '{target_path}', but syntax verification flagged errors: {syntax_err[:150]}"
        )

        return AgentResult(
            status=status,
            agent=self.role,
            summary=summary,
            evidence=f"Root Cause: {fix.root_cause_analysis}\n\nDiff:\n{diff_text}",
            files_inspected=files_inspected,
            changes_made=changes_made,
            confidence=0.95 if syntax_ok else 0.5,
            recommended_next_action="Pass workspace to TestingAgent to execute automated test suites.",
            tool_calls_made=tool_calls_made,
            errors=[syntax_err] if syntax_err else [],
        )
