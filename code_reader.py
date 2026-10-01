from pathlib import Path


def read_file(file_path: str) -> str:
    """
    Read and return the contents of a single file.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not path.is_file():
        raise ValueError(f"Not a file: {file_path}")

    try:
        return path.read_text(encoding="utf-8")

    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def read_codebase(file_paths: list[str]) -> dict[str, str]:
    """
    Read multiple files and return their contents.

    Returns:
        {
            "path/to/file.py": "file contents...",
            ...
        }
    """

    codebase = {}

    for file_path in file_paths:
        try:
            content = read_file(file_path)
            codebase[file_path] = content

        except Exception as error:
            print(f"Could not read {file_path}: {error}")

    return codebase


if __name__ == "__main__":
    from codebase_loader import load_codebase

    repository_path = input(
        "Enter cloned repository path: "
    ).strip()

    try:
        # First find the files
        files = load_codebase(repository_path)

        # Then read their contents
        codebase = read_codebase(files)

        print(f"\nSuccessfully read {len(codebase)} files.\n")

        for file_path, content in codebase.items():
            print("=" * 60)
            print(file_path)
            print("=" * 60)
            print(content[:500])
            print()

    except Exception as error:
        print(f"Error: {error}")