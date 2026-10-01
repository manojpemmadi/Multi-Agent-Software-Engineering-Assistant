"""Isolated workspace management with strict path traversal and sandbox security."""

import difflib
import logging
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codepilot.config import settings

logger = logging.getLogger(__name__)


class WorkspaceSecurityError(Exception):
    """Raised when an operation attempts to violate workspace isolation boundaries."""
    pass


class Workspace:
    """Represents an isolated directory environment for a task or repository."""

    def __init__(self, workspace_id: str, root_path: Path):
        self.workspace_id = workspace_id
        self.root_path = root_path.resolve()
        self.baseline_snapshot: Dict[str, str] = {}
        self.created_at = None

    def resolve_safe_path(self, relative_path: str) -> Path:
        """Resolve a path relative to the workspace root and verify it cannot escape."""
        if not relative_path:
            return self.root_path

        # Reject path traversal patterns explicitly
        clean_rel = os.path.normpath(relative_path.strip().lstrip("/\\"))
        target = (self.root_path / clean_rel).resolve()

        # Strict containment check
        try:
            target.relative_to(self.root_path)
        except ValueError:
            raise WorkspaceSecurityError(
                f"Path traversal detected! Path '{relative_path}' resolves outside workspace root."
            )

        return target

    def take_baseline_snapshot(self) -> None:
        """Capture the initial contents of files to compute diffs later."""
        self.baseline_snapshot.clear()
        for file_path in self.root_path.rglob("*"):
            if file_path.is_file() and not self._is_ignored(file_path):
                try:
                    rel = file_path.relative_to(self.root_path).as_posix()
                    self.baseline_snapshot[rel] = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    logger.debug("Could not snapshot %s: %s", file_path, e)

    def get_modified_files(self) -> List[Dict[str, Any]]:
        """Compute unified diffs for all modified, added, or deleted files."""
        current_files: Dict[str, str] = {}
        for file_path in self.root_path.rglob("*"):
            if file_path.is_file() and not self._is_ignored(file_path):
                try:
                    rel = file_path.relative_to(self.root_path).as_posix()
                    current_files[rel] = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        changes: List[Dict[str, Any]] = []

        # Check modified and deleted files
        for rel_path, old_content in self.baseline_snapshot.items():
            if rel_path not in current_files:
                changes.append({
                    "file_path": rel_path,
                    "change_type": "deleted",
                    "diff": f"--- {rel_path}\n+++ /dev/null\n@@ -1 +0,0 @@\n(deleted)",
                    "summary": f"Deleted {rel_path}",
                })
            elif current_files[rel_path] != old_content:
                diff_lines = list(
                    difflib.unified_diff(
                        old_content.splitlines(keepends=True),
                        current_files[rel_path].splitlines(keepends=True),
                        fromfile=f"a/{rel_path}",
                        tofile=f"b/{rel_path}",
                    )
                )
                changes.append({
                    "file_path": rel_path,
                    "change_type": "modified",
                    "diff": "".join(diff_lines),
                    "summary": f"Modified {rel_path} ({len(diff_lines)} diff lines)",
                })

        # Check added files
        for rel_path, new_content in current_files.items():
            if rel_path not in self.baseline_snapshot:
                diff_lines = list(
                    difflib.unified_diff(
                        [],
                        new_content.splitlines(keepends=True),
                        fromfile="/dev/null",
                        tofile=f"b/{rel_path}",
                    )
                )
                changes.append({
                    "file_path": rel_path,
                    "change_type": "created",
                    "diff": "".join(diff_lines),
                    "summary": f"Created {rel_path}",
                })

        return changes

    def _is_ignored(self, file_path: Path) -> bool:
        for part in file_path.parts:
            if part in settings.IGNORED_DIRECTORIES:
                return True
        return False


class WorkspaceManager:
    """Manages creation, sandboxing, and lifecycle of workspaces."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = (root_dir or settings.WORKSPACES_ROOT).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._workspaces: Dict[str, Workspace] = {}

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        return self._workspaces.get(workspace_id)

    def create_paste_workspace(
        self,
        code_snippet: str,
        language: str = "python",
        file_name: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Workspace:
        """Create an isolated workspace containing user-pasted code."""
        ws_id = workspace_id or f"paste_{uuid.uuid4().hex[:8]}"
        ws_path = self.root_dir / ws_id
        if ws_path.exists():
            shutil.rmtree(ws_path, ignore_errors=True)
        ws_path.mkdir(parents=True, exist_ok=True)

        # Determine extension and main file name
        ext_map = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
            "java": ".java",
            "rust": ".rs",
            "go": ".go",
            "cpp": ".cpp",
            "c": ".c",
            "html": ".html",
            "css": ".css",
            "json": ".json",
        }
        ext = ext_map.get(language.lower(), ".py")
        primary_filename = file_name or f"main{ext}"
        primary_file = ws_path / primary_filename

        primary_file.write_text(code_snippet, encoding="utf-8")

        # For Python, also generate a basic pytest template if not already present
        if ext == ".py" and not (ws_path / "test_main.py").exists():
            test_content = (
                f"# Automated test verification for {primary_filename}\n"
                f"import importlib.util\n"
                f"import pytest\n"
                f"\n"
                f"def test_syntax_and_import():\n"
                f"    '''Verify that {primary_filename} can be imported without syntax or runtime error.'''\n"
                f"    spec = importlib.util.spec_from_file_location('solution_module', '{primary_filename}')\n"
                f"    module = importlib.util.module_from_spec(spec)\n"
                f"    spec.loader.exec_module(module)\n"
                f"    assert module is not None\n"
            )
            (ws_path / f"test_{Path(primary_filename).stem}.py").write_text(test_content, encoding="utf-8")

        workspace = Workspace(ws_id, ws_path)
        workspace.take_baseline_snapshot()
        self._workspaces[ws_id] = workspace
        logger.info("Created paste workspace '%s' at %s", ws_id, ws_path)
        return workspace

    def clone_github_repo(
        self,
        repo_url: str,
        branch: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Workspace:
        """Securely clone a public GitHub repository into an isolated sandbox."""
        # Validate URL to avoid command injection or protocol tricks
        sanitized_url = repo_url.strip()
        github_pattern = r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$"
        if not re.match(github_pattern, sanitized_url):
            raise WorkspaceSecurityError(
                f"Invalid or untrusted GitHub URL '{repo_url}'. Only public https://github.com/org/repo URLs are accepted."
            )

        repo_name = sanitized_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        ws_id = workspace_id or f"repo_{repo_name}_{uuid.uuid4().hex[:6]}"
        ws_path = self.root_dir / ws_id

        if ws_path.exists():
            shutil.rmtree(ws_path, ignore_errors=True)
        ws_path.mkdir(parents=True, exist_ok=True)

        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            # Sanitize branch name
            if not re.match(r"^[A-Za-z0-9._/-]+$", branch):
                raise WorkspaceSecurityError(f"Invalid branch name '{branch}'")
            cmd.extend(["--branch", branch])
        cmd.extend([sanitized_url, str(ws_path)])

        logger.info("Cloning repository %s into %s", sanitized_url, ws_path)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.COMMAND_TIMEOUT_SECONDS * 2,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Git clone failed (exit {result.returncode}): {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Git clone timed out after {settings.COMMAND_TIMEOUT_SECONDS * 2} seconds.")

        workspace = Workspace(ws_id, ws_path)
        workspace.take_baseline_snapshot()
        self._workspaces[ws_id] = workspace
        return workspace

    def cleanup_workspace(self, workspace_id: str) -> bool:
        """Delete an isolated workspace directory."""
        workspace = self._workspaces.pop(workspace_id, None)
        if workspace and workspace.root_path.exists():
            shutil.rmtree(workspace.root_path, ignore_errors=True)
            logger.info("Cleaned up workspace %s", workspace_id)
            return True
        return False
