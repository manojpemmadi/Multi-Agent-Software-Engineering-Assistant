from pathlib import Path


# Directories we don't want to scan
IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
}

# File types that CodePilot should understand
SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".html",
    ".css",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
}


def load_codebase(repository_path: str) -> list[str]:
    """
    Scan a repository and return paths of relevant source files.
    """

    repository = Path(repository_path)

    if not repository.exists():
        raise FileNotFoundError(
            f"Repository not found: {repository_path}"
        )

    if not repository.is_dir():
        raise NotADirectoryError(
            f"Path is not a directory: {repository_path}"
        )

    files = []

    for path in repository.rglob("*"):

        # Ignore unwanted directories
        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue

        # Only collect files
        if not path.is_file():
            continue

        # Only collect supported file types
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(str(path))

    return files

if __name__ == "__main__":
    repository_path = input("Enter cloned repository path: ").strip()

    try:
        files = load_codebase(repository_path)

        print(f"\nFound {len(files)} relevant files:\n")

        for file in files:
            print(file)

    except Exception as error:
        print(f"Error: {error}")
        
        