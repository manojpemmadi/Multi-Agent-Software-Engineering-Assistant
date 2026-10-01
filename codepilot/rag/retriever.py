"""Semantic retrieval subsystem for CodePilot."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from codepilot.config import settings
from codepilot.rag.chunker import CodeChunker
from codepilot.rag.embeddings import EmbeddingService
from codepilot.rag.loader import scan_workspace_source_files
from codepilot.rag.store import CodeVectorStore

logger = logging.getLogger(__name__)


class CodeRetriever:
    """High-level codebase indexer and semantic retriever."""

    def __init__(
        self,
        vector_store: Optional[CodeVectorStore] = None,
        embedding_service: Optional[EmbeddingService] = None,
        chunker: Optional[CodeChunker] = None,
    ):
        self.vector_store = vector_store or CodeVectorStore()
        self.embedding_service = embedding_service or EmbeddingService()
        self.chunker = chunker or CodeChunker()

    def index_workspace(self, workspace_path: str, workspace_id: str) -> Dict[str, Any]:
        """Scan, chunk, embed, and index an entire workspace."""
        root = Path(workspace_path).resolve()
        files = scan_workspace_source_files(str(root))
        if not files:
            return {"indexed_files": 0, "indexed_chunks": 0}

        all_chunks: List[str] = []
        all_metadatas: List[Dict[str, Any]] = []

        for f in files:
            file_chunks = self.chunker.chunk_file(f, root)
            for c in file_chunks:
                all_chunks.append(c["text"])
                all_metadatas.append({
                    "file_path": c["file_path"],
                    "language": c.get("language", "unknown"),
                    "start_line": c.get("start_line", 1),
                    "end_line": c.get("end_line", 1),
                    "symbols": c.get("symbols", "general"),
                    "workspace_id": workspace_id,
                })

        if not all_chunks:
            return {"indexed_files": len(files), "indexed_chunks": 0}

        # Embed in batches
        embeddings = self.embedding_service.embed_chunks(all_chunks)
        collection_name = f"ws_{workspace_id}"
        self.vector_store.add_chunks(collection_name, all_chunks, embeddings, all_metadatas)

        logger.info(
            "Indexed workspace '%s': %d files, %d chunks",
            workspace_id,
            len(files),
            len(all_chunks),
        )
        return {
            "indexed_files": len(files),
            "indexed_chunks": len(all_chunks),
            "collection_name": collection_name,
        }

    def retrieve(
        self,
        query: str,
        workspace_id: str,
        top_k: int = settings.RAG_TOP_K,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant code snippets for a natural language or bug query."""
        if not query.strip():
            return []

        collection_name = f"ws_{workspace_id}"
        try:
            query_embedding = self.embedding_service.embed_text(query)
            search_res = self.vector_store.search(
                collection_name=collection_name,
                query_embedding=query_embedding,
                top_k=top_k,
            )
        except Exception as e:
            logger.error("RAG retrieval failed: %s", e)
            return []

        docs = search_res.get("documents", [[]])[0]
        metadatas = search_res.get("metadatas", [[]])[0]
        distances = search_res.get("distances", [[]])[0]

        results = []
        for i, text in enumerate(docs):
            meta = metadatas[i] if i < len(metadatas) else {}
            dist = distances[i] if i < len(distances) else None
            results.append({
                "text": text,
                "file_path": meta.get("file_path", "unknown"),
                "start_line": meta.get("start_line", 1),
                "end_line": meta.get("end_line", 1),
                "language": meta.get("language", ""),
                "symbols": meta.get("symbols", ""),
                "distance": dist,
            })

        return results
