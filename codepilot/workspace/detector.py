"""Project language, ecosystem, and test framework detector."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProjectDetector:
    """Detects programming languages, frameworks, and test runners in a workspace."""

    @staticmethod
    def detect(workspace_path: str) -> Dict[str, Any]:
        """Analyze files in the workspace and return ecosystem metadata."""
        root = Path(workspace_path)
        if not root.exists():
            return {
                "language": "unknown",
                "framework": "none",
                "test_command": "",
                "test_framework": "unknown",
            }

        files = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
        filenames = {Path(f).name.lower() for f in files}
        extensions = {Path(f).suffix.lower() for f in files}

        # Python detection
        if any(f in filenames for f in ["pyproject.toml", "setup.py", "requirements.txt", "pipfile"]) or ".py" in extensions:
            test_cmd = "pytest"
            test_framework = "pytest"
            # Check if pytest is configured or unittest
            has_tests = any("test" in f.lower() for f in files)
            return {
                "language": "python",
                "framework": "python",
                "test_command": "pytest -v",
                "test_framework": test_framework,
                "has_tests": has_tests,
                "files_count": len(files),
            }

        # Node / TypeScript / JavaScript
        if "package.json" in filenames or ".ts" in extensions or ".js" in extensions:
            return {
                "language": "typescript" if ".ts" in extensions else "javascript",
                "framework": "node",
                "test_command": "npm test",
                "test_framework": "jest_or_npm",
                "has_tests": any("test" in f.lower() or "spec" in f.lower() for f in files),
                "files_count": len(files),
            }

        # Rust
        if "cargo.toml" in filenames or ".rs" in extensions:
            return {
                "language": "rust",
                "framework": "cargo",
                "test_command": "cargo test",
                "test_framework": "cargo_test",
                "has_tests": True,
                "files_count": len(files),
            }

        # Go
        if "go.mod" in filenames or ".go" in extensions:
            return {
                "language": "go",
                "framework": "go_modules",
                "test_command": "go test ./...",
                "test_framework": "go_test",
                "has_tests": any("_test.go" in f for f in files),
                "files_count": len(files),
            }

        # Java
        if any(f in filenames for f in ["pom.xml", "build.gradle", "build.gradle.kts"]) or ".java" in extensions:
            cmd = "mvn test" if "pom.xml" in filenames else "gradle test"
            return {
                "language": "java",
                "framework": "maven" if "pom.xml" in filenames else "gradle",
                "test_command": cmd,
                "test_framework": "junit",
                "has_tests": any("test" in f.lower() for f in files),
                "files_count": len(files),
            }

        # Default fallback
        primary_ext = max(extensions, key=lambda ext: sum(1 for f in files if f.endswith(ext))) if extensions else ""
        return {
            "language": primary_ext.replace(".", "") or "text",
            "framework": "generic",
            "test_command": "",
            "test_framework": "generic",
            "has_tests": False,
            "files_count": len(files),
        }
