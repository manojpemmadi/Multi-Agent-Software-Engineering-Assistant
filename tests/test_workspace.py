"""Unit tests for workspace management and security sandboxing."""

import shutil
from pathlib import Path
import pytest

from codepilot.workspace.manager import (
    WorkspaceManager,
    WorkspaceSecurityError,
)


@pytest.fixture
def temp_ws_mgr(tmp_path):
    mgr = WorkspaceManager(root_dir=tmp_path / "workspaces")
    yield mgr
    shutil.rmtree(tmp_path / "workspaces", ignore_errors=True)


def test_create_paste_workspace(temp_ws_mgr):
    code = "def hello():\n    return 'world'\n"
    ws = temp_ws_mgr.create_paste_workspace(code, language="python", file_name="main.py")

    assert ws.root_path.exists()
    assert (ws.root_path / "main.py").exists()
    assert (ws.root_path / "main.py").read_text(encoding="utf-8") == code


def test_path_traversal_prevention(temp_ws_mgr):
    code = "x = 1\n"
    ws = temp_ws_mgr.create_paste_workspace(code, language="python")

    # Safe relative paths should resolve
    safe_path = ws.resolve_safe_path("main.py")
    assert safe_path == ws.root_path / "main.py"

    safe_nested = ws.resolve_safe_path("src/sub/mod.py")
    assert safe_nested == ws.root_path / "src" / "sub" / "mod.py"

    # Malicious path traversal attempts must raise WorkspaceSecurityError
    with pytest.raises(WorkspaceSecurityError):
        ws.resolve_safe_path("../../outside.txt")

    with pytest.raises(WorkspaceSecurityError):
        ws.resolve_safe_path("../../../windows/system32/cmd.exe")


def test_baseline_snapshot_and_diffs(temp_ws_mgr):
    initial_code = "def calculate(a, b):\n    return a + b\n"
    ws = temp_ws_mgr.create_paste_workspace(initial_code, language="python", file_name="math_ops.py")

    # Initially no modifications
    changes = ws.get_modified_files()
    assert len(changes) == 0

    # Modify math_ops.py
    modified_code = "def calculate(a, b):\n    return a * b\n"
    (ws.root_path / "math_ops.py").write_text(modified_code, encoding="utf-8")

    changes = ws.get_modified_files()
    assert len(changes) == 1
    assert changes[0]["file_path"] == "math_ops.py"
    assert changes[0]["change_type"] == "modified"
    assert "+    return a * b" in changes[0]["diff"]
