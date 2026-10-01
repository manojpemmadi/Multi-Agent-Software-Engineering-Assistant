"""Unit tests for RAG indexing, chunking, and semantic retrieval."""

import pytest
from pathlib import Path
from codepilot.rag.chunker import CodeChunker
from codepilot.rag.loader import scan_workspace_source_files
from codepilot.rag.retriever import CodeRetriever
from codepilot.workspace.manager import WorkspaceManager


def test_chunker_extracts_python_ast(tmp_path):
    sample_file = tmp_path / "service.py"
    sample_file.write_text(
        "class AuthService:\n"
        "    def authenticate(self, user, pwd):\n"
        "        return True\n\n"
        "def helper_func():\n"
        "    return 42\n",
        encoding="utf-8",
    )

    chunker = CodeChunker()
    chunks = chunker.chunk_file(sample_file, tmp_path)

    assert len(chunks) >= 2
    symbols = [c["symbols"] for c in chunks]
    assert any("AuthService" in s for s in symbols)
    assert any("helper_func" in s for s in symbols)


def test_scan_workspace_source_files(tmp_path):
    # Create valid files
    (tmp_path / "app.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Doc", encoding="utf-8")
    # Create ignored files
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("git config", encoding="utf-8")
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "app.cpython-311.pyc").write_text("bin", encoding="utf-8")

    files = scan_workspace_source_files(str(tmp_path))
    filenames = [f.name for f in files]

    assert "app.py" in filenames
    assert "README.md" in filenames
    assert "config" not in filenames
    assert "app.cpython-311.pyc" not in filenames


def test_retriever_indexing_and_search(tmp_path):
    mgr = WorkspaceManager(root_dir=tmp_path / "workspaces")
    code = (
        "def calculate_tax(income):\n"
        "    if income < 10000:\n"
        "        return 0\n"
        "    return income * 0.2\n"
    )
    ws = mgr.create_paste_workspace(code, language="python", file_name="tax.py")

    retriever = CodeRetriever()
    idx_res = retriever.index_workspace(str(ws.root_path), ws.workspace_id)
    assert idx_res["indexed_files"] >= 1

    results = retriever.retrieve("calculate tax rate for income", ws.workspace_id, top_k=2)
    assert len(results) > 0
    assert any("calculate_tax" in r["text"] for r in results)
