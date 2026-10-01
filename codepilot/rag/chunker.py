"""Syntax and structure-aware code chunking for RAG."""

import ast
import re
from pathlib import Path
from typing import Any, Dict, List

from codepilot.config import settings


class CodeChunker:
    """Chunks code files into semantically meaningful blocks with rich metadata."""

    def __init__(self, chunk_size: int = settings.CHUNK_SIZE, overlap: int = settings.CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_file(self, file_path: Path, workspace_root: Path) -> List[Dict[str, Any]]:
        """Extract semantic chunks with line boundaries and detected symbols."""
        try:
            rel_path = file_path.relative_to(workspace_root).as_posix()
        except ValueError:
            rel_path = file_path.name

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        ext = file_path.suffix.lower()
        if not content.strip():
            return []

        # Python-specific AST extraction
        if ext == ".py":
            chunks = self._chunk_python_ast(content, rel_path)
            if chunks:
                return chunks

        # Generic sliding window chunker
        return self._chunk_generic(content, rel_path, ext)

    def _chunk_python_ast(self, content: str, rel_path: str) -> List[Dict[str, Any]]:
        """Extract functions and classes using Python's AST."""
        chunks: List[Dict[str, Any]] = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []  # Fallback to generic if syntax error

        lines = content.splitlines()

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start_line = node.lineno
                end_line = getattr(node, "end_lineno", None)
                if not end_line:
                    end_line = min(len(lines), start_line + 40)

                snippet = "\n".join(lines[start_line - 1 : end_line])
                node_type = "class" if isinstance(node, ast.ClassDef) else "function"

                chunks.append({
                    "text": snippet,
                    "file_path": rel_path,
                    "language": "python",
                    "start_line": start_line,
                    "end_line": end_line,
                    "symbols": f"{node_type}:{node.name}",
                })

        return chunks

    def _chunk_generic(self, content: str, rel_path: str, ext: str) -> List[Dict[str, Any]]:
        """Extract chunks via line windows with overlap."""
        chunks: List[Dict[str, Any]] = []
        lines = content.splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return []

        # Find rough symbol declarations (def, function, class, etc.)
        symbol_pattern = re.compile(r"^\s*(?:def|class|function|async\s+def|const\s+\w+\s*=\s*(?:async\s*)?\()([A-Za-z0-9_]+)")

        line_step = max(10, self.chunk_size // 40)
        overlap_lines = max(2, self.overlap // 40)

        start_idx = 0
        while start_idx < total_lines:
            end_idx = min(total_lines, start_idx + line_step)
            chunk_lines = lines[start_idx:end_idx]
            chunk_text = "\n".join(chunk_lines)

            # Detect symbols inside chunk
            symbols = []
            for l in chunk_lines:
                m = symbol_pattern.search(l)
                if m:
                    symbols.append(m.group(1))

            chunks.append({
                "text": chunk_text,
                "file_path": rel_path,
                "language": ext.replace(".", "") or "text",
                "start_line": start_idx + 1,
                "end_line": end_idx,
                "symbols": ",".join(symbols) if symbols else "general",
            })

            if end_idx >= total_lines:
                break
            start_idx += max(1, line_step - overlap_lines)

        return chunks
