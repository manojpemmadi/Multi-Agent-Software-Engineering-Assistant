"""File editing and modification tools for MCP layer."""

import difflib
from pathlib import Path
from typing import Any, Dict

from codepilot.config import settings
from codepilot.workspace.manager import Workspace


def write_file_impl(
    workspace: Workspace,
    file_path: str,
    content: str,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """Write or overwrite content into a specified file inside the workspace."""
    target_file = workspace.resolve_safe_path(file_path)

    if target_file.exists() and not overwrite:
        return {
            "error": f"File '{file_path}' already exists and overwrite is set to False.",
            "success": False,
        }

    # Ensure parent directory exists
    target_file.parent.mkdir(parents=True, exist_ok=True)

    previous_content = ""
    is_created = not target_file.exists()
    if not is_created:
        try:
            previous_content = target_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

    target_file.write_text(content, encoding="utf-8")

    diff_lines = list(
        difflib.unified_diff(
            previous_content.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
    )

    return {
        "success": True,
        "file_path": file_path,
        "is_created": is_created,
        "bytes_written": len(content.encode("utf-8")),
        "lines_written": len(content.splitlines()),
        "diff": "".join(diff_lines),
    }


def replace_file_content_impl(
    workspace: Workspace,
    file_path: str,
    target_content: str,
    replacement_content: str,
) -> Dict[str, Any]:
    """Replace an exact block of code inside a workspace file."""
    target_file = workspace.resolve_safe_path(file_path)
    if not target_file.exists() or not target_file.is_file():
        return {
            "error": f"File '{file_path}' does not exist.",
            "success": False,
        }

    try:
        content = target_file.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Failed reading file '{file_path}': {e}", "success": False}

    if target_content not in content:
        # Check normalized whitespace match
        norm_content = "\n".join(line.rstrip() for line in content.splitlines())
        norm_target = "\n".join(line.rstrip() for line in target_content.splitlines())
        if norm_target not in norm_content:
            return {
                "error": f"Target content was not found verbatim in '{file_path}'. Please check indentation and whitespace.",
                "success": False,
            }
        # Replace normalized
        new_content = norm_content.replace(norm_target, replacement_content, 1)
    else:
        new_content = content.replace(target_content, replacement_content, 1)

    target_file.write_text(new_content, encoding="utf-8")

    diff_lines = list(
        difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
    )

    return {
        "success": True,
        "file_path": file_path,
        "diff": "".join(diff_lines),
    }
