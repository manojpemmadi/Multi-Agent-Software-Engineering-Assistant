"""Unit tests for MCP server, tools, and independent permission enforcement."""

import pytest
from codepilot.mcp.client import MCPClient
from codepilot.mcp.server import MCPServerRegistry
from codepilot.models.schemas import AgentRole
from codepilot.workspace.manager import WorkspaceManager


@pytest.fixture
def mcp_setup(tmp_path):
    mgr = WorkspaceManager(root_dir=tmp_path / "workspaces")
    ws = mgr.create_paste_workspace("x = 10\ny = 20\n", language="python", file_name="sample.py")
    server = MCPServerRegistry()
    client = MCPClient(server=server)
    return {"workspace": ws, "server": server, "client": client}


def test_mcp_server_lists_tools(mcp_setup):
    server = mcp_setup["server"]
    tools = server.list_tools()
    tool_names = [t["name"] for t in tools]

    expected = [
        "list_files",
        "view_tree",
        "read_file",
        "search_code",
        "write_file",
        "replace_file_content",
        "run_command",
        "run_tests",
        "git_status",
        "git_diff",
    ]
    for exp in expected:
        assert exp in tool_names


def test_mcp_read_and_search_tools(mcp_setup):
    server = mcp_setup["server"]
    ws = mcp_setup["workspace"]

    # Read file
    res = server.execute_tool("read_file", {"file_path": "sample.py"}, ws)
    assert not res.is_error
    assert "x = 10" in res.output

    # Search code
    search_res = server.execute_tool("search_code", {"query": "y = 20"}, ws)
    assert not search_res.is_error
    assert search_res.structured_data["total_matches"] == 1


def test_mcp_write_and_replace_tools(mcp_setup):
    server = mcp_setup["server"]
    ws = mcp_setup["workspace"]

    # Write new file
    w_res = server.execute_tool("write_file", {"file_path": "new_mod.py", "content": "def foo(): return 42\n"}, ws)
    assert not w_res.is_error
    assert (ws.root_path / "new_mod.py").exists()

    # Replace content
    r_res = server.execute_tool(
        "replace_file_content",
        {"file_path": "new_mod.py", "target_content": "return 42", "replacement_content": "return 100"},
        ws,
    )
    assert not r_res.is_error
    assert "return 100" in (ws.root_path / "new_mod.py").read_text()


def test_mcp_blocked_command_security(mcp_setup):
    server = mcp_setup["server"]
    ws = mcp_setup["workspace"]

    res = server.execute_tool("run_command", {"command": "rm -rf /"}, ws)
    assert res.is_error
    assert "Security violation" in res.output or res.structured_data.get("is_blocked")


def test_mcp_role_based_permissions(mcp_setup):
    client = mcp_setup["client"]
    ws = mcp_setup["workspace"]

    # 1. Code Analysis Agent is read-only: calling write_file MUST be rejected
    denied_res = client.call_tool(
        role=AgentRole.CODE_ANALYSIS,
        tool_name="write_file",
        arguments={"file_path": "forbidden.py", "content": "bad"},
        workspace=ws,
    )
    assert denied_res.is_error
    assert "PERMISSION DENIED" in denied_res.output
    assert not (ws.root_path / "forbidden.py").exists()

    # 2. Debugging Agent calling write_file MUST be allowed
    allowed_res = client.call_tool(
        role=AgentRole.DEBUGGING,
        tool_name="write_file",
        arguments={"file_path": "allowed.py", "content": "valid"},
        workspace=ws,
    )
    assert not allowed_res.is_error
    assert (ws.root_path / "allowed.py").exists()
