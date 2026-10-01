from codebase_loader import load_codebase
from code_reader import read_codebase
from code_chunker import chunk_text
from embedding_service import EmbeddingService
from vector_store import VectorStore


def index_repository(repository_path: str) -> None:
    print("\n1. Loading repository files...")

    file_paths = load_codebase(repository_path)

    print(f"Found {len(file_paths)} files.")

    if not file_paths:
        print("No supported files found.")
        return

    print("\n2. Reading files...")

    codebase = read_codebase(file_paths)

    print(f"Successfully read {len(codebase)} files.")

    print("\n3. Creating chunks...")

    all_chunks = []
    all_file_paths = []

    for file_path, content in codebase.items():

        chunks = chunk_text(content)

        for chunk in chunks:
            all_chunks.append(chunk)
            all_file_paths.append(file_path)

    print(f"Created {len(all_chunks)} chunks.")

    if not all_chunks:
        print("No chunks were created.")
        return

    print("\n4. Creating embeddings...")

    embedding_service = EmbeddingService()

    embeddings = embedding_service.embed_chunks(all_chunks)

    print(f"Created {len(embeddings)} embeddings.")

    print("\n5. Storing in ChromaDB...")

    vector_store = VectorStore()

    vector_store.add_chunks(
        chunks=all_chunks,
        embeddings=embeddings,
        file_paths=all_file_paths,
    )

    print(
        f"Successfully indexed {vector_store.count()} chunks."
    )


if __name__ == "__main__":
    repository_path = input(
        "Enter cloned repository path: "
    ).strip()

    try:
        index_repository(repository_path)

    except Exception as error:
        print(f"\nIndexing failed: {error}")