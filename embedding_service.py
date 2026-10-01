from sentence_transformers import SentenceTransformer
class EmbeddingService:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        print("Loading embedding model...")

        self.model = SentenceTransformer(model_name)

        print("Embedding model loaded.")

    def embed_text(self, text: str) -> list[float]:
        """
        Convert a single piece of text into an embedding vector.
        """

        if not text.strip():
            raise ValueError("Text cannot be empty.")

        embedding = self.model.encode(
            text,
            convert_to_numpy=True
        )

        return embedding.tolist()

    def embed_chunks(self, chunks: list[str]) -> list[list[float]]:
        """
        Convert multiple chunks into embedding vectors.
        """

        if not chunks:
            return []

        embeddings = self.model.encode(
            chunks,
            convert_to_numpy=True,
            show_progress_bar=True
        )

        return embeddings.tolist()


if __name__ == "__main__":
    embedding_service = EmbeddingService()

    text = "def hello(): return 'Hello World'"

    embedding = embedding_service.embed_text(text)

    print("\nEmbedding created successfully.")
    print(f"Vector dimensions: {len(embedding)}")
    print(f"First 5 values: {embedding[:5]}")