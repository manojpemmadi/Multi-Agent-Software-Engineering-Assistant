"""Secure command execution tools for MCP layer."""

import logging
import os
import subprocess
import time
from typing import Any, Dict, Optional

from codepilot.config import settings
from codepilot.workspace.manager import Workspace

logger = logging.getLogger(__name__)


def _sanitize_env() -> Dict[str, str]:
    """Create a sanitized copy of environment variables, stripping sensitive secrets."""
    safe_env = os.environ.copy()
    sensitive_keys = [
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTIGRAVITY_CSRF_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "SLACK_BOT_TOKEN",
    ]
    for key in list(safe_env.keys()):
        if any(secret in key.upper() for secret in ["API_KEY", "SECRET", "TOKEN", "PASSWORD"]):
            safe_env.pop(key, None)
        elif key in sensitive_keys:
            safe_env.pop(key, None)

    return safe_env


def run_command_impl(
    workspace: Workspace,
    command: str,
    timeout_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute a safe shell command inside the workspace directory."""
    clean_cmd = command.strip()
    if not clean_cmd:
        return {"error": "Command cannot be empty.", "exit_code": 1}

    # Block destructive commands
    cmd_lower = clean_cmd.lower()
    for blocked in settings.BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            logger.warning("Blocked dangerous command attempted: %s", clean_cmd)
            return {
                "error": f"Security violation: Command contains prohibited operation '{blocked}'.",
                "exit_code": -1,
                "is_blocked": True,
            }

    timeout = timeout_seconds or settings.COMMAND_TIMEOUT_SECONDS
    env = _sanitize_env()

    start_time = time.time()
    try:
        proc = subprocess.run(
            clean_cmd,
            shell=True,
            cwd=str(workspace.root_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = (time.time() - start_time) * 1000

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        # Limit output length to prevent overflow
        if len(stdout) > settings.MAX_COMMAND_OUTPUT_BYTES:
            stdout = stdout[:settings.MAX_COMMAND_OUTPUT_BYTES] + "\n...[stdout truncated]..."
        if len(stderr) > settings.MAX_COMMAND_OUTPUT_BYTES:
            stderr = stderr[:settings.MAX_COMMAND_OUTPUT_BYTES] + "\n...[stderr truncated]..."

        return {
            "command": clean_cmd,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": round(duration_ms, 2),
            "success": proc.returncode == 0,
        }

    except subprocess.TimeoutExpired:
        duration_ms = (time.time() - start_time) * 1000
        return {
            "command": clean_cmd,
            "exit_code": -1,
            "error": f"Command timed out after {timeout} seconds.",
            "duration_ms": round(duration_ms, 2),
            "success": False,
        }
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return {
            "command": clean_cmd,
            "exit_code": -1,
            "error": f"Command execution failed: {str(e)}",
            "duration_ms": round(duration_ms, 2),
            "success": False,
        }
