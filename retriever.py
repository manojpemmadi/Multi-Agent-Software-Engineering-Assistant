from embedding_service import EmbeddingService
from vector_store import VectorStore


class CodeRetriever:
    def __init__(self, top_k: int = 5):
        self.top_k = top_k
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()

    def retrieve(self, query: str) -> list[dict]:
        """
        Retrieve the most relevant code chunks for a query.
        """

        if not query.strip():
            return []

        # Convert user question into an embedding
        query_embedding = self.embedding_service.embed_text(query)

        # Search ChromaDB
        results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=self.top_k,
        )

        retrieved = []

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for document, metadata, distance in zip(
            documents,
            metadatas,
            distances,
        ):
            retrieved.append(
                {
                    "text": document,
                    "file_path": metadata.get("file_path"),
                    "distance": distance,
                }
            )

        return retrieved


if __name__ == "__main__":
    retriever = CodeRetriever(top_k=3)

    query = input(
        "Ask something about the codebase: "
    ).strip()

    results = retriever.retrieve(query)

    print("\nRelevant code:\n")

    for index, result in enumerate(results, start=1):
        print("=" * 60)
        print(f"Result {index}")
        print(f"File: {result['file_path']}")
        print(f"Distance: {result['distance']}")
        print("=" * 60)
        print(result["text"][:1000])
        print()