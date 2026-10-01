"""Codebase scanner and file loader for RAG indexing."""

import logging
from pathlib import Path
from typing import List

from codepilot.config import settings

logger = logging.getLogger(__name__)


def scan_workspace_source_files(workspace_path: str) -> List[Path]:
    """Scan workspace and collect all supported source code files, skipping ignored dirs."""
    root = Path(workspace_path).resolve()
    if not root.exists() or not root.is_dir():
        logger.warning("Workspace root %s does not exist or is not a directory.", root)
        return []

    collected: List[Path] = []

    for file_path in root.rglob("*"):
        # Skip if any parent part is in ignored directories
        if any(part in settings.IGNORED_DIRECTORIES for part in file_path.parts):
            continue

        if not file_path.is_file():
            continue

        # Skip files exceeding max size limit
        try:
            if file_path.stat().st_size > settings.MAX_FILE_SIZE_BYTES:
                continue
        except OSError:
            continue

        if file_path.suffix.lower() in settings.SUPPORTED_SOURCE_EXTENSIONS:
            collected.append(file_path)

    logger.info("Found %d supported source files in workspace %s", len(collected), workspace_path)
    return collected
