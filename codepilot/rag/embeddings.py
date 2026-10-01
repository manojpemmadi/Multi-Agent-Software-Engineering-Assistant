"""Embedding service utilizing local SentenceTransformers."""

import logging
from typing import List, Optional

from codepilot.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates dense vector embeddings for source code chunks."""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self._model = None

    def _load_model(self):
        if self._model is None:
            logger.info("Loading embedding model '%s'...", self.model_name)
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                logger.info("Embedding model '%s' loaded successfully.", self.model_name)
            except Exception as e:
                logger.error("Failed to load sentence-transformers model: %s", e)
                raise RuntimeError(f"Embedding model initialization failed: {e}") from e
        return self._model

    def embed_text(self, text: str) -> List[float]:
        """Convert a single query or text into an embedding vector."""
        if not text.strip():
            raise ValueError("Text to embed cannot be empty.")

        model = self._load_model()
        vec = model.encode(text, convert_to_numpy=True)
        return vec.tolist()

    def embed_chunks(self, chunks: List[str]) -> List[List[float]]:
        """Convert a batch of text chunks into embedding vectors."""
        if not chunks:
            return []

        model = self._load_model()
        vecs = model.encode(
            chunks,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=32,
        )
        return vecs.tolist()
