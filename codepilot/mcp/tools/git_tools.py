"""Git and version control tools for MCP layer."""

import shutil
import subprocess
from typing import Any, Dict

from codepilot.workspace.manager import Workspace


def git_status_impl(workspace: Workspace) -> Dict[str, Any]:
    """Get current git status or file change status in workspace."""
    git_dir = workspace.root_path / ".git"
    if not git_dir.exists():
        # Fall back to workspace baseline snapshot tracking
        changes = workspace.get_modified_files()
        return {
            "is_git_repo": False,
            "modified_files": [c["file_path"] for c in changes],
            "total_changes": len(changes),
            "summary": f"{len(changes)} files modified relative to baseline snapshot.",
        }

    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(workspace.root_path),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return {
            "is_git_repo": True,
            "status_output": proc.stdout.strip(),
            "exit_code": proc.returncode,
        }
    except Exception as e:
        return {"error": f"Failed running git status: {e}", "is_git_repo": True}


def git_diff_impl(workspace: Workspace) -> Dict[str, Any]:
    """Get unified git diff of all modifications in workspace."""
    git_dir = workspace.root_path / ".git"
    if not git_dir.exists():
        # Use diff from snapshot
        changes = workspace.get_modified_files()
        combined_diff = "\n\n".join(c["diff"] for c in changes if c.get("diff"))
        return {
            "is_git_repo": False,
            "diff": combined_diff,
            "modified_files": [c["file_path"] for c in changes],
        }

    try:
        proc = subprocess.run(
            ["git", "diff"],
            cwd=str(workspace.root_path),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        diff_text = proc.stdout.strip()
        if not diff_text:
            # Also check untracked/staged diff
            diff_text = "\n".join(c["diff"] for c in workspace.get_modified_files())

        return {
            "is_git_repo": True,
            "diff": diff_text,
            "exit_code": proc.returncode,
        }
    except Exception as e:
        return {"error": f"Failed running git diff: {e}", "is_git_repo": True}
