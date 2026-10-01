"""Automated test execution and failure categorization tool for MCP layer."""

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from codepilot.config import settings
from codepilot.mcp.tools.exec_tools import run_command_impl
from codepilot.models.schemas import ValidationResult
from codepilot.workspace.detector import ProjectDetector
from codepilot.workspace.manager import Workspace


def _parse_pytest_output(stdout: str, stderr: str, exit_code: int) -> Dict[str, Any]:
    """Parse pytest stdout/stderr to extract counts and failure category."""
    combined = f"{stdout}\n{stderr}"

    passed_count = 0
    failed_count = 0
    error_count = 0

    # Match summary line: "1 passed, 2 failed in 0.05s"
    summary_match = re.search(r"===\s*(.+?)\s*in\s*[\d\.]+s\s*===", combined)
    if summary_match:
        text = summary_match.group(1)
        p = re.search(r"(\d+)\s+passed", text)
        f = re.search(r"(\d+)\s+failed", text)
        e = re.search(r"(\d+)\s+error", text)
        if p:
            passed_count = int(p.group(1))
        if f:
            failed_count = int(f.group(1))
        if e:
            error_count = int(e.group(1))
    else:
        # Fallback check for single tests
        passed_count = len(re.findall(r"PASSED", combined))
        failed_count = len(re.findall(r"FAILED", combined))
        error_count = len(re.findall(r"ERROR", combined))

    total = passed_count + failed_count + error_count
    passed = (exit_code == 0) and (failed_count == 0) and (error_count == 0)

    # Categorize failure
    category = "none" if passed else "fix_failure"
    if not passed:
        if "SyntaxError" in combined or "IndentationError" in combined:
            category = "syntax_error"
        elif "ModuleNotFoundError" in combined or "No module named" in combined:
            category = "environment_failure"
        elif "AssertionError" in combined or "assert" in combined:
            category = "fix_failure"

    return {
        "passed": passed,
        "total": total,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "error_count": error_count,
        "category": category,
    }


def run_tests_impl(
    workspace: Workspace,
    test_path: Optional[str] = None,
    framework: Optional[str] = None,
) -> Dict[str, Any]:
    """Run automated tests inside the workspace and return structured validation evidence."""
    eco = ProjectDetector.detect(str(workspace.root_path))
    lang = eco.get("language", "python")

    # Use the current virtual environment's Python if available
    python_exe = sys.executable

    # Formulate test command
    if framework == "pytest" or lang == "python":
        target = test_path or ""
        cmd = f'"{python_exe}" -m pytest {target} -v --tb=short'
        used_framework = "pytest"
    elif lang in ("javascript", "typescript"):
        cmd = f"npm test -- {test_path or ''}"
        used_framework = "npm/jest"
    elif lang == "rust":
        cmd = "cargo test"
        used_framework = "cargo"
    elif lang == "go":
        cmd = "go test -v ./..."
        used_framework = "go"
    else:
        # Generic command
        cmd = eco.get("test_command") or f'"{python_exe}" -m pytest -v'
        used_framework = eco.get("test_framework", "generic")

    exec_res = run_command_impl(workspace, cmd, timeout_seconds=settings.COMMAND_TIMEOUT_SECONDS)

    stdout = exec_res.get("stdout", "")
    stderr = exec_res.get("stderr", "")
    exit_code = exec_res.get("exit_code", 1)

    parsed = _parse_pytest_output(stdout, stderr, exit_code)

    validation = ValidationResult(
        passed=parsed["passed"],
        test_framework=used_framework,
        total_tests=parsed["total"],
        passed_tests=parsed["passed_count"],
        failed_tests=parsed["failed_count"],
        error_tests=parsed["error_count"],
        failure_category=parsed["category"],
        test_command=cmd,
        raw_output=f"{stdout}\n{stderr}".strip(),
        details=[f"Exit code: {exit_code}", f"Category: {parsed['category']}"],
    )

    return {
        "validation": validation.model_dump(),
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "passed": validation.passed,
    }
