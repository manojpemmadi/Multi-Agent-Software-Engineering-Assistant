"""File and repository inspection tools for MCP layer."""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from codepilot.config import settings
from codepilot.workspace.manager import Workspace, WorkspaceManager


def list_files_impl(
    workspace: Workspace,
    subpath: str = ".",
    max_depth: int = 3,
) -> Dict[str, Any]:
    """List directory contents up to a maximum depth."""
    target_dir = workspace.resolve_safe_path(subpath)
    if not target_dir.exists():
        return {"error": f"Directory not found: {subpath}"}
    if not target_dir.is_dir():
        return {"error": f"Path is not a directory: {subpath}"}

    items = []
    base_depth = len(target_dir.parts)

    for root, dirs, files in os.walk(target_dir):
        # Exclude ignored directories
        dirs[:] = [d for d in dirs if d not in settings.IGNORED_DIRECTORIES]
        current_depth = len(Path(root).parts) - base_depth
        if current_depth > max_depth:
            dirs.clear()
            continue

        rel_root = Path(root).relative_to(workspace.root_path).as_posix()
        for f in files:
            file_path = Path(root) / f
            try:
                rel_f = file_path.relative_to(workspace.root_path).as_posix()
                items.append({
                    "path": rel_f,
                    "type": "file",
                    "size_bytes": file_path.stat().st_size,
                })
            except Exception:
                pass

        for d in dirs:
            dir_path = Path(root) / d
            try:
                rel_d = dir_path.relative_to(workspace.root_path).as_posix()
                items.append({
                    "path": rel_d,
                    "type": "directory",
                })
            except Exception:
                pass

    return {
        "workspace_id": workspace.workspace_id,
        "base_path": subpath,
        "total_items": len(items),
        "items": items[:200],  # cap to avoid giant token payloads
    }


def view_tree_impl(
    workspace: Workspace,
    subpath: str = ".",
    max_depth: int = 3,
) -> str:
    """Generate an ASCII visual tree of the workspace structure."""
    target_dir = workspace.resolve_safe_path(subpath)
    if not target_dir.exists():
        return f"Directory not found: {subpath}"

    lines = [f"{workspace.root_path.name}/"]

    def _build_tree(curr_path: Path, prefix: str = "", depth: int = 0):
        if depth >= max_depth:
            return
        try:
            entries = sorted(
                [e for e in curr_path.iterdir() if e.name not in settings.IGNORED_DIRECTORIES],
                key=lambda e: (not e.is_dir(), e.name.lower())
            )
        except PermissionError:
            return

        for index, entry in enumerate(entries):
            is_last = (index == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "
            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                _build_tree(entry, prefix + child_prefix, depth + 1)
            else:
                lines.append(f"{prefix}{connector}{entry.name}")

    _build_tree(target_dir, "", 0)
    return "\n".join(lines)


def read_file_impl(
    workspace: Workspace,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> Dict[str, Any]:
    """Read full file or slice of lines from a workspace file."""
    target_file = workspace.resolve_safe_path(file_path)
    if not target_file.exists():
        return {"error": f"File '{file_path}' does not exist in workspace."}
    if not target_file.is_file():
        return {"error": f"Path '{file_path}' is not a file."}

    file_size = target_file.stat().st_size
    if file_size > settings.MAX_FILE_SIZE_BYTES:
        return {"error": f"File '{file_path}' ({file_size} bytes) exceeds max size limit of {settings.MAX_FILE_SIZE_BYTES} bytes."}

    try:
        content = target_file.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Failed to read file '{file_path}': {str(e)}"}

    lines = content.splitlines()
    total_lines = len(lines)

    if start_line is not None or end_line is not None:
        start_idx = max(0, (start_line or 1) - 1)
        end_idx = min(total_lines, end_line or total_lines)
        sliced_lines = lines[start_idx:end_idx]
        annotated = [
            f"{i + 1:4d} | {line}"
            for i, line in enumerate(sliced_lines, start=start_idx)
        ]
        return {
            "file_path": file_path,
            "total_lines": total_lines,
            "start_line": start_idx + 1,
            "end_line": end_idx,
            "content": "\n".join(annotated),
            "raw_content": "\n".join(sliced_lines),
        }

    annotated = [f"{i + 1:4d} | {line}" for i, line in enumerate(lines)]
    return {
        "file_path": file_path,
        "total_lines": total_lines,
        "start_line": 1,
        "end_line": total_lines,
        "content": "\n".join(annotated),
        "raw_content": content,
    }


def search_code_impl(
    workspace: Workspace,
    query: str,
    file_pattern: Optional[str] = None,
    is_regex: bool = False,
) -> Dict[str, Any]:
    """Search for code snippets matching query or regex across workspace files."""
    if not query.strip():
        return {"error": "Search query cannot be empty."}

    flags = 0 if is_regex else re.IGNORECASE
    try:
        pattern = re.compile(query if is_regex else re.escape(query), flags)
    except re.error as e:
        return {"error": f"Invalid regex pattern '{query}': {str(e)}"}

    matches = []
    for file_path in workspace.root_path.rglob("*"):
        if not file_path.is_file() or workspace._is_ignored(file_path):
            continue

        if file_pattern and not file_path.match(file_pattern):
            continue

        if file_path.suffix.lower() not in settings.SUPPORTED_SOURCE_EXTENSIONS:
            continue

        try:
            rel = file_path.relative_to(workspace.root_path).as_posix()
            content = file_path.read_text(encoding="utf-8", errors="replace")
            for line_idx, line in enumerate(content.splitlines(), start=1):
                if pattern.search(line):
                    matches.append({
                        "file_path": rel,
                        "line_number": line_idx,
                        "line_content": line.strip()[:200],
                    })
                    if len(matches) >= 100:
                        break
        except Exception:
            continue

        if len(matches) >= 100:
            break

    return {
        "query": query,
        "total_matches": len(matches),
        "matches": matches,
    }
