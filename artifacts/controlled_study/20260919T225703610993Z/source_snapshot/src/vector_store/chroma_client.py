"""
ChromaDB vector store for MathemaTest.

Provides semantic search over mathematical content using
locally-generated embeddings.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.config.settings import get_settings, Settings
from src.vector_store.embeddings import EmbeddingService


logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """ChromaDB vector store for semantic search.
    
    Stores text and LaTeX chunks with their embeddings for
    similarity-based retrieval.
    
    Example:
        >>> store = ChromaVectorStore()
        >>> store.add_documents([{"id": "1", "content": "F = ma", "type": "formula"}])
        >>> results = store.search("force equals mass times acceleration")
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        embedding_service: Optional[EmbeddingService] = None,
        collection_name: Optional[str] = None,
    ):
        """Initialize ChromaDB vector store.
        
        Args:
            settings: Configuration settings.
            embedding_service: Embedding service instance.
            collection_name: Name of the ChromaDB collection.
        """
        self.settings = settings or get_settings()
        self.embedder = embedding_service or EmbeddingService(
            model_name=self.settings.embedding_model
        )
        self.collection_name = collection_name or self.settings.chroma_collection_name
        
        self._client = None
        self._collection = None
    
    @property
    def client(self):
        """Get or create ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
                
                persist_path = self.settings.get_chroma_path()
                
                # Use new ChromaDB API (v0.4+)
                self._client = chromadb.PersistentClient(path=str(persist_path))
                logger.info(f"ChromaDB initialized at {persist_path}")
            except ImportError:
                logger.error("chromadb not installed")
                raise
        return self._client
    
    @property
    def collection(self):
        """Get or create the main collection."""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "MathemaTest content chunks"},
            )
            logger.info(f"Using collection: {self.collection_name}")
        return self._collection
    
    def add_documents(
        self,
        documents: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> int:
        """Add documents to the vector store.
        
        Args:
            documents: List of dicts with 'id', 'content', and optional metadata.
            batch_size: Batch size for embedding generation.
            
        Returns:
            Number of documents added.
        """
        if not documents:
            return 0
        
        ids = []
        contents = []
        metadatas = []
        
        for doc in documents:
            doc_id = doc.get("id", str(hash(doc.get("content", ""))))
            content = doc.get("content", "")
            metadata = {k: v for k, v in doc.items() if k not in ("id", "content")}
            
            ids.append(doc_id)
            contents.append(content)
            metadatas.append(metadata)
        
        # Generate embeddings
        embeddings = self.embedder.embed(contents)
        
        # Add to collection
        self.collection.add(
            ids=ids,
            documents=contents,
            embeddings=embeddings.tolist(),
            metadatas=metadatas,
        )
        
        logger.info(f"Added {len(ids)} documents to vector store")
        return len(ids)
    
    def search(
        self,
        query: str,
        n_results: int = 10,
        where: Optional[Dict] = None,
        include_distances: bool = True,
        max_chapter: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar documents.
        
        Args:
            query: Search query text.
            n_results: Maximum number of results.
            where: Metadata filter.
            include_distances: Include similarity scores.
            max_chapter: If provided, only return documents from chapters < max_chapter.
                        This is the "lobotomy" filter for preventing data leakage.
            
        Returns:
            List of matching documents with scores.
        """
        query_embedding = self.embedder.embed(query)
        
        # Build the where clause with optional chapter filtering
        effective_where = where.copy() if where else None
        
        if max_chapter is not None:
            # Lobotomy filter: only include chapters strictly less than max_chapter
            chapter_filter = {"chapter": {"$lte": max_chapter}}
            
            if effective_where:
                # Combine with existing filter using $and
                effective_where = {"$and": [effective_where, chapter_filter]}
            else:
                effective_where = chapter_filter
        
        results = self.collection.query(
            query_embeddings=query_embedding.tolist(),
            n_results=n_results,
            where=effective_where,
            include=["documents", "metadatas", "distances"] if include_distances else ["documents", "metadatas"],
        )
        
        # Convert to list of dicts
        output = []
        for i in range(len(results["ids"][0])):
            item = {
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
            }
            if include_distances and results.get("distances"):
                item["distance"] = results["distances"][0][i]
                item["score"] = 1 - item["distance"]  # Convert distance to similarity
            output.append(item)
        
        return output
    
    def search_latex(
        self,
        latex_query: str,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search specifically for LaTeX expressions.
        
        Args:
            latex_query: LaTeX expression to search for.
            n_results: Maximum results.
            
        Returns:
            Matching formula documents.
        """
        return self.search(
            query=f"Mathematical expression: {latex_query}",
            n_results=n_results,
            where={"type": "formula"} if "type" in self.get_metadata_keys() else None,
        )
    
    def get_metadata_keys(self) -> set:
        """Get all metadata keys in the collection."""
        try:
            sample = self.collection.peek(limit=10)
            if sample["metadatas"]:
                keys = set()
                for m in sample["metadatas"]:
                    keys.update(m.keys())
                return keys
        except Exception:
            pass
        return set()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        return {
            "collection_name": self.collection_name,
            "document_count": self.collection.count(),
            "embedding_dimension": self.embedder.embedding_dimension,
        }
    
    def clear(self, confirm: bool = False) -> int:
        """Clear all documents from the collection.
        
        Args:
            confirm: Must be True to actually clear.
            
        Returns:
            Number of documents deleted.
        """
        if not confirm:
            raise ValueError("Must pass confirm=True to clear")
        
        count = self.collection.count()
        self.client.delete_collection(self.collection_name)
        self._collection = None
        logger.warning(f"Cleared {count} documents from {self.collection_name}")
        return count


class MockChromaVectorStore:
    """Mock vector store for testing."""
    
    def __init__(self):
        self.documents: List[Dict[str, Any]] = []
    
    def add_documents(self, documents: List[Dict[str, Any]], **kwargs) -> int:
        self.documents.extend(documents)
        return len(documents)
    
    def search(self, query: str, n_results: int = 10, **kwargs) -> List[Dict[str, Any]]:
        # Return first n_results as mock
        return [
            {**doc, "score": 0.9 - i * 0.1}
            for i, doc in enumerate(self.documents[:n_results])
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        return {"document_count": len(self.documents)}
