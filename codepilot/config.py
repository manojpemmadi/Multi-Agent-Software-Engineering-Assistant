"""Configuration management for CodePilot."""

import os
from pathlib import Path
from typing import List, Set
from dotenv import load_dotenv

# Load .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    # Project Info
    APP_NAME: str = "CodePilot"
    VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # Host & Port for Web UI
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # LLM Settings
    # Primary: gemini. Swappable to openai or mock.
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    
    # OpenAI backup / alternative
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Vector Store & Embeddings
    CHROMA_PERSIST_DIR: Path = BASE_DIR / os.getenv("CHROMA_DIR", "chroma_db")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "6"))
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "150"))

    # Workspaces
    WORKSPACES_ROOT: Path = BASE_DIR / os.getenv("WORKSPACES_DIR", ".workspaces")
    WORKSPACE_RETENTION_HOURS: int = int(os.getenv("WORKSPACE_RETENTION_HOURS", "24"))

    # Security & Execution Limits
    COMMAND_TIMEOUT_SECONDS: int = int(os.getenv("COMMAND_TIMEOUT_SECONDS", "45"))
    MAX_COMMAND_OUTPUT_BYTES: int = 150_000  # 150 KB
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    MAX_FILE_SIZE_BYTES: int = 2_000_000  # 2 MB per file

    # Blocked dangerous commands for security sandboxing
    BLOCKED_COMMANDS: Set[str] = {
        "rm -rf /",
        "rmdir /s /q c:\\",
        "mkfs",
        "dd if=",
        ":(){ :|:& };:",
        "shutdown",
        "reboot",
        "format",
        "diskpart",
        "net user",
        "curl http",
        "wget http",
        "powershell -enc",
        "nc -e",
    }

    # Supported source extensions for scanning/RAG
    SUPPORTED_SOURCE_EXTENSIONS: Set[str] = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
        ".cs", ".go", ".rs", ".rb", ".php", ".html", ".css", ".json", ".yaml",
        ".yml", ".toml", ".sql", ".sh", ".bash", ".ps1", ".md", ".txt"
    }

    # Ignored directories for repository scanning
    IGNORED_DIRECTORIES: Set[str] = {
        ".git", ".svn", ".hg", ".venv", "venv", "env", "__pycache__",
        "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "build", "dist", "target", "out", "bin", "obj", ".next", ".nuxt",
        ".idea", ".vscode", "coverage", ".turbo", "chroma_db", ".workspaces"
    }

settings = Settings()
# Ensure directories exist
settings.WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)
settings.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
