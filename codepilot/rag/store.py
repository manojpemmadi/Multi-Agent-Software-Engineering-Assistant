"""ChromaDB persistent vector store for codebase embeddings."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from codepilot.config import settings

logger = logging.getLogger(__name__)


class CodeVectorStore:
    """Manages ChromaDB collections for indexed repositories and workspaces."""

    def __init__(self, persist_dir: Optional[Path] = None):
        self.persist_dir = persist_dir or settings.CHROMA_PERSIST_DIR
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def get_or_create_collection(self, collection_name: str = "codebase"):
        # ChromaDB collection names must be alphanumeric/underscores/hyphens
        clean_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in collection_name)
        if len(clean_name) < 3:
            clean_name = f"col_{clean_name}"
        return self.client.get_or_create_collection(name=clean_name[:63])

    def add_chunks(
        self,
        collection_name: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
    ) -> None:
        """Store chunk documents with embeddings and metadata."""
        if not chunks:
            return

        collection = self.get_or_create_collection(collection_name)
        doc_ids = ids or [f"chunk_{i}_{hash(chunks[i]) & 0xFFFFFFFF}" for i in range(len(chunks))]

        # Sanitize metadatas: ensure all values are str, int, float, or bool
        clean_metadatas = []
        for m in metadatas:
            clean_m = {}
            for k, v in m.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_m[k] = v
                else:
                    clean_m[k] = str(v)
            clean_metadatas.append(clean_m)

        collection.add(
            ids=doc_ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=clean_metadatas,
        )
        logger.info("Added %d chunks to Chroma collection '%s'", len(chunks), collection_name)

    def search(
        self,
        collection_name: str,
        query_embedding: List[float],
        top_k: int = 5,
        where_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Perform semantic search using query embedding."""
        collection = self.get_or_create_collection(collection_name)
        count = collection.count()
        if count == 0:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        k = min(top_k, count)
        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": k,
        }
        if where_filter:
            kwargs["where"] = where_filter

        return collection.query(**kwargs)

    def count(self, collection_name: str) -> int:
        collection = self.get_or_create_collection(collection_name)
        return collection.count()

    def delete_collection(self, collection_name: str) -> None:
        try:
            self.client.delete_collection(name=collection_name)
        except Exception:
            pass
