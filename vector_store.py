import chromadb
class VectorStore:
    def __init__(self, collection_name: str = "codebase"):
        self.client = chromadb.PersistentClient(
            path="./chroma_db"
        )

        self.collection = self.client.get_or_create_collection(
            name=collection_name
        )

    def add_chunks(
        self,
        chunks: list[str],
        embeddings: list[list[float]],
        file_paths: list[str],
    ) -> None:

        if not chunks:
            return

        ids = [
            f"chunk_{index}"
            for index in range(len(chunks))
        ]

        metadatas = [
            {
                "file_path": file_paths[index]
            }
            for index in range(len(chunks))
        ]

        self.collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> dict:

        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )

    def count(self) -> int:
        return self.collection.count()


if __name__ == "__main__":
    store = VectorStore()

    print(
        f"Vector store initialized. "
        f"Stored chunks: {store.count()}"
    )