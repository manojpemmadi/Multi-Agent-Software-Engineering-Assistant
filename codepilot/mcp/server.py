"""Model Context Protocol (MCP) Server hosting tools for CodePilot."""

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from codepilot.mcp.tools.edit_tools import replace_file_content_impl, write_file_impl
from codepilot.mcp.tools.exec_tools import run_command_impl
from codepilot.mcp.tools.fs_tools import list_files_impl, read_file_impl, search_code_impl, view_tree_impl
from codepilot.mcp.tools.git_tools import git_diff_impl, git_status_impl
from codepilot.mcp.tools.test_tools import run_tests_impl
from codepilot.models.schemas import ToolResult
from codepilot.workspace.manager import Workspace

logger = logging.getLogger(__name__)


class MCPServerRegistry:
    """Production Model Context Protocol tool server."""

    def __init__(self, name: str = "codepilot-mcp-server"):
        self.name = name
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._register_all_tools()

    def _register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "input_schema": input_schema,
            "handler": handler,
        }

    def _register_all_tools(self) -> None:
        # 1. list_files
        self._register_tool(
            name="list_files",
            description="List directory files and folders in workspace up to a max depth.",
            input_schema={
                "type": "object",
                "properties": {
                    "subpath": {"type": "string", "default": ".", "description": "Relative path in workspace"},
                    "max_depth": {"type": "integer", "default": 3, "description": "Maximum directory traversal depth"},
                },
            },
            handler=lambda ws, **kw: list_files_impl(ws, kw.get("subpath", "."), kw.get("max_depth", 3)),
        )

        # 2. view_tree
        self._register_tool(
            name="view_tree",
            description="Generate a visual ASCII tree hierarchy of files in the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "subpath": {"type": "string", "default": ".", "description": "Relative path in workspace"},
                    "max_depth": {"type": "integer", "default": 3, "description": "Maximum depth"},
                },
            },
            handler=lambda ws, **kw: view_tree_impl(ws, kw.get("subpath", "."), kw.get("max_depth", 3)),
        )

        # 3. read_file
        self._register_tool(
            name="read_file",
            description="Read the entire contents or specific line slice of a file in the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file relative to workspace"},
                    "start_line": {"type": "integer", "description": "Optional 1-indexed starting line"},
                    "end_line": {"type": "integer", "description": "Optional 1-indexed ending line"},
                },
                "required": ["file_path"],
            },
            handler=lambda ws, **kw: read_file_impl(
                ws, kw["file_path"], kw.get("start_line"), kw.get("end_line")
            ),
        )

        # 4. search_code
        self._register_tool(
            name="search_code",
            description="Search for symbols, function names, error patterns, or regex in code files.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword or regular expression to search for"},
                    "file_pattern": {"type": "string", "description": "Optional glob pattern like '*.py'"},
                    "is_regex": {"type": "boolean", "default": False, "description": "Whether query is a regex"},
                },
                "required": ["query"],
            },
            handler=lambda ws, **kw: search_code_impl(
                ws, kw["query"], kw.get("file_pattern"), kw.get("is_regex", False)
            ),
        )

        # 5. write_file
        self._register_tool(
            name="write_file",
            description="Create a new file or completely overwrite an existing file in the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative file path to write"},
                    "content": {"type": "string", "description": "Full text content to write"},
                    "overwrite": {"type": "boolean", "default": True, "description": "Whether to overwrite existing file"},
                },
                "required": ["file_path", "content"],
            },
            handler=lambda ws, **kw: write_file_impl(
                ws, kw["file_path"], kw["content"], kw.get("overwrite", True)
            ),
        )

        # 6. replace_file_content
        self._register_tool(
            name="replace_file_content",
            description="Perform a surgical replacement of an exact matching block of code in a file.",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Relative file path"},
                    "target_content": {"type": "string", "description": "Exact text snippet to replace"},
                    "replacement_content": {"type": "string", "description": "New text snippet to insert"},
                },
                "required": ["file_path", "target_content", "replacement_content"],
            },
            handler=lambda ws, **kw: replace_file_content_impl(
                ws, kw["file_path"], kw["target_content"], kw["replacement_content"]
            ),
        )

        # 7. run_command
        self._register_tool(
            name="run_command",
            description="Execute a safe shell command inside the workspace sandbox with timeout limits.",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run in workspace"},
                    "timeout_seconds": {"type": "integer", "description": "Timeout in seconds"},
                },
                "required": ["command"],
            },
            handler=lambda ws, **kw: run_command_impl(
                ws, kw["command"], kw.get("timeout_seconds")
            ),
        )

        # 8. run_tests
        self._register_tool(
            name="run_tests",
            description="Execute automated tests (pytest, unittest, etc.) and return structured pass/fail results.",
            input_schema={
                "type": "object",
                "properties": {
                    "test_path": {"type": "string", "description": "Specific test file or directory path"},
                    "framework": {"type": "string", "description": "e.g. 'pytest', 'npm'"},
                },
            },
            handler=lambda ws, **kw: run_tests_impl(
                ws, kw.get("test_path"), kw.get("framework")
            ),
        )

        # 9. git_status
        self._register_tool(
            name="git_status",
            description="Inspect git workspace status and check modified, untracked, or deleted files.",
            input_schema={"type": "object", "properties": {}},
            handler=lambda ws, **kw: git_status_impl(ws),
        )

        # 10. git_diff
        self._register_tool(
            name="git_diff",
            description="Inspect unified diff of code modifications made in workspace.",
            input_schema={"type": "object", "properties": {}},
            handler=lambda ws, **kw: git_diff_impl(ws),
        )

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return list of all registered tools with their MCP-compliant schemas."""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["input_schema"],
            }
            for t in self._tools.values()
        ]

    def get_tool(self, name: str) -> Optional[Dict[str, Any]]:
        return self._tools.get(name)

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        workspace: Workspace,
    ) -> ToolResult:
        """Execute a tool with error boundary and output structuring."""
        if tool_name not in self._tools:
            return ToolResult(
                tool_name=tool_name,
                is_error=True,
                output=f"Error: Tool '{tool_name}' is not registered on the MCP server.",
            )

        start_time = time.time()
        tool_entry = self._tools[tool_name]
        handler = tool_entry["handler"]

        try:
            res = handler(workspace, **arguments)
            elapsed_ms = (time.time() - start_time) * 1000

            if isinstance(res, str):
                return ToolResult(
                    tool_name=tool_name,
                    is_error=False,
                    output=res,
                    execution_time_ms=round(elapsed_ms, 2),
                )
            elif isinstance(res, dict):
                is_error = res.get("is_error", False) or bool(res.get("error"))
                # Format string output
                if "output" in res:
                    out_str = str(res["output"])
                elif "stdout" in res or "stderr" in res:
                    out_str = f"{res.get('stdout', '')}\n{res.get('stderr', '')}".strip()
                elif "error" in res:
                    out_str = f"Error: {res['error']}"
                else:
                    out_str = json.dumps(res, indent=2)

                return ToolResult(
                    tool_name=tool_name,
                    is_error=is_error,
                    output=out_str,
                    structured_data=res,
                    execution_time_ms=round(elapsed_ms, 2),
                )
            else:
                return ToolResult(
                    tool_name=tool_name,
                    is_error=False,
                    output=str(res),
                    execution_time_ms=round(elapsed_ms, 2),
                )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error("Error executing MCP tool '%s': %s", tool_name, e, exc_info=True)
            return ToolResult(
                tool_name=tool_name,
                is_error=True,
                output=f"Tool execution exception: {str(e)}",
                execution_time_ms=round(elapsed_ms, 2),
            )
