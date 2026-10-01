"""
Hybrid Retrieval Orchestrator for MathemaTest.

Uses LangGraph to orchestrate parallel vector and graph searches,
then merges and re-ranks results using a cross-encoder model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypedDict

from src.config.settings import get_settings, Settings
from src.graph_store.neo4j_client import Neo4jClient, MockNeo4jClient
from src.vector_store.chroma_client import ChromaVectorStore, MockChromaVectorStore
from src.retrieval.query_refiner import QueryRefiner, RefinedQuery, MockQueryRefiner


logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class RetrievalResult:
    """A single retrieval result from any source."""
    id: str
    content: str
    source: str  # "vector" or "graph"
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningPacket:
    """Final merged retrieval results for generation."""
    query: str
    refined_query: str
    results: List[RetrievalResult]
    graph_context: Dict[str, Any]
    total_results: int
    vector_count: int
    graph_count: int


class OrchestratorState(TypedDict):
    """State for LangGraph orchestration."""
    query: str
    refined_query: Optional[RefinedQuery]
    vector_results: List[Dict]
    graph_results: List[Dict]
    merged_results: List[RetrievalResult]
    reasoning_packet: Optional[ReasoningPacket]


# =============================================================================
# CROSS-ENCODER RE-RANKER
# =============================================================================

class CrossEncoderReranker:
    """Re-ranks results using a cross-encoder model.
    
    Uses ms-marco-MiniLM for relevance scoring between
    query and retrieved documents.
    """
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """Initialize cross-encoder.
        
        Args:
            model_name: HuggingFace cross-encoder model.
        """
        self.model_name = model_name
        self._model = None
    
    @property
    def model(self):
        """Lazy load the cross-encoder model."""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(self.model_name)
                logger.info(f"Loaded cross-encoder: {self.model_name}")
            except ImportError:
                logger.error("sentence-transformers not installed")
                raise
        return self._model
    
    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """Re-rank results by relevance to query.
        
        Args:
            query: The search query.
            results: Results to re-rank.
            top_k: Return only top K results.
            
        Returns:
            Re-ranked results with updated scores.
        """
        if not results:
            return []
        
        # Create query-document pairs
        pairs = [(query, r.content) for r in results]
        
        # Score with cross-encoder
        scores = self.model.predict(pairs)
        
        # Update scores and sort
        for result, score in zip(results, scores):
            result.score = float(score)
        
        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
        
        if top_k:
            sorted_results = sorted_results[:top_k]
        
        return sorted_results


class MockCrossEncoderReranker:
    """Mock reranker for testing."""
    
    def rerank(
        self,
        query: str,
        results: List[RetrievalResult],
        top_k: Optional[int] = None,
    ) -> List[RetrievalResult]:
        # Just sort by existing score
        sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
        if top_k:
            sorted_results = sorted_results[:top_k]
        return sorted_results


# =============================================================================
# HYBRID RETRIEVER
# =============================================================================

class HybridRetriever:
    """Orchestrates hybrid vector + graph retrieval.
    
    Executes parallel queries against ChromaDB (semantic) and
    Neo4j (logical), then merges and re-ranks the results.
    
    Example:
        >>> retriever = HybridRetriever()
        >>> packet = retriever.retrieve("What is the work-energy theorem?")
        >>> for result in packet.results:
        ...     print(result.content, result.score)
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        vector_store: Optional[ChromaVectorStore] = None,
        graph_client: Optional[Neo4jClient] = None,
        query_refiner: Optional[QueryRefiner] = None,
        reranker: Optional[CrossEncoderReranker] = None,
    ):
        """Initialize hybrid retriever.
        
        Args:
            settings: Configuration settings.
            vector_store: ChromaDB vector store.
            graph_client: Neo4j graph client.
            query_refiner: Query refinement service.
            reranker: Cross-encoder for re-ranking.
        """
        self.settings = settings or get_settings()
        self.vector_store = vector_store or ChromaVectorStore(self.settings)
        self.graph_client = graph_client or Neo4jClient(self.settings)
        self.query_refiner = query_refiner or QueryRefiner(self.settings)
        self.reranker = reranker or CrossEncoderReranker(
            self.settings.cross_encoder_model
        )
    
    def _vector_search(
        self,
        query: str,
        n_results: int = 10,
    ) -> List[RetrievalResult]:
        """Execute vector similarity search.
        
        Args:
            query: Search query.
            n_results: Max results.
            
        Returns:
            List of retrieval results.
        """
        try:
            results = self.vector_store.search(query, n_results=n_results)
            
            return [
                RetrievalResult(
                    id=r["id"],
                    content=r["content"],
                    source="vector",
                    score=r.get("score", 0.5),
                    metadata=r.get("metadata", {}),
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def _graph_search(
        self,
        query: str,
        n_results: int = 10,
    ) -> List[RetrievalResult]:
        """Execute graph traversal search.
        
        Searches for concepts matching the query and retrieves
        their prerequisites and related misconceptions.
        
        Args:
            query: Search query.
            n_results: Max results.
            
        Returns:
            List of retrieval results.
        """
        results = []
        
        try:
            # Search by LaTeX if query contains math
            if "\\" in query or "=" in query:
                latex_results = self.graph_client.search_by_latex(query)
                for r in latex_results[:n_results]:
                    node = r["node"]
                    results.append(RetrievalResult(
                        id=node.get("id", ""),
                        content=f"{node.get('name', '')}: {node.get('description', '')} | LaTeX: {node.get('raw_latex', '')}",
                        source="graph",
                        score=0.8,  # Default graph match score
                        metadata={"types": r.get("types", []), **node},
                    ))
            
            # Get prerequisites for any concepts found
            for result in results[:3]:  # Limit prerequisite expansion
                concept_id = result.id
                prereqs = self.graph_client.get_prerequisites(concept_id, depth=2)
                for prereq in prereqs[:5]:
                    node = prereq["node"]
                    distance = prereq["distance"]
                    results.append(RetrievalResult(
                        id=node.get("id", ""),
                        content=f"[Prerequisite] {node.get('name', '')}: {node.get('description', '')}",
                        source="graph",
                        score=0.7 - (distance * 0.1),  # Decrease score with distance
                        metadata={"distance": distance, "type": "prerequisite"},
                    ))
                
                # Get related misconceptions
                misconceptions = self.graph_client.get_misconceptions(concept_id)
                for misc in misconceptions[:3]:
                    results.append(RetrievalResult(
                        id=misc.get("id", ""),
                        content=f"[Misconception] {misc.get('description', '')} | Common Error: {misc.get('common_error', '')}",
                        source="graph",
                        score=0.6,
                        metadata={"type": "misconception"},
                    ))
                    
        except Exception as e:
            logger.error(f"Graph search failed: {e}")
        
        return results[:n_results]
    
    def _merge_results(
        self,
        vector_results: List[RetrievalResult],
        graph_results: List[RetrievalResult],
    ) -> List[RetrievalResult]:
        """Merge and deduplicate results from both sources.
        
        Args:
            vector_results: Results from vector search.
            graph_results: Results from graph search.
            
        Returns:
            Merged list with duplicates removed.
        """
        seen_ids = set()
        merged = []
        
        # Combine all results
        all_results = vector_results + graph_results
        
        for result in all_results:
            if result.id not in seen_ids:
                seen_ids.add(result.id)
                merged.append(result)
        
        return merged
    
    def retrieve(
        self,
        query: str,
        use_refinement: bool = True,
        n_results: int = 10,
        rerank: bool = True,
    ) -> ReasoningPacket:
        """Execute hybrid retrieval pipeline.
        
        1. Optionally refine query (HyDE/Step-Back via GPT-4o)
        2. Execute parallel vector + graph searches
        3. Merge and deduplicate results
        4. Re-rank with cross-encoder
        5. Package into ReasoningPacket
        
        Args:
            query: User's query.
            use_refinement: Apply query refinement.
            n_results: Max final results.
            rerank: Apply cross-encoder re-ranking.
            
        Returns:
            ReasoningPacket with ranked results.
        """
        logger.info(f"Hybrid retrieval for: {query[:50]}...")
        
        # Step 1: Query refinement
        if use_refinement:
            refined = self.query_refiner.auto_refine(query)
            search_query = refined.refined_query
        else:
            refined = RefinedQuery(original_query=query, refined_query=query)
            search_query = query
        
        # Step 2: Parallel searches (in practice, use asyncio or threading)
        vector_results = self._vector_search(search_query, n_results=n_results * 2)
        graph_results = self._graph_search(query, n_results=n_results)  # Original query for graph
        
        logger.info(f"Vector: {len(vector_results)} | Graph: {len(graph_results)}")
        
        # Step 3: Merge
        merged = self._merge_results(vector_results, graph_results)
        
        # Step 4: Re-rank
        if rerank and merged:
            merged = self.reranker.rerank(query, merged, top_k=n_results)
        else:
            merged = merged[:n_results]
        
        # Step 5: Build reasoning packet
        graph_context = {
            "step_back_questions": refined.step_back_questions or [],
            "query_type": refined.query_type,
        }
        
        packet = ReasoningPacket(
            query=query,
            refined_query=search_query,
            results=merged,
            graph_context=graph_context,
            total_results=len(merged),
            vector_count=len(vector_results),
            graph_count=len(graph_results),
        )
        
        logger.info(f"Returning {len(merged)} results")
        return packet
    
    def retrieve_for_audit(
        self,
        query: str,
        current_chapter: int,
        n_results: int = 10,
        rerank: bool = True,
    ) -> List[RetrievalResult]:
        """Retrieve context with chapter-based lobotomy filter.
        
        This is the strict entry point for the Textbook Auditor. It ensures
        no data leakage by only returning content from chapters BEFORE
        the current chapter being audited.
        
        Args:
            query: Search query text.
            current_chapter: The chapter being audited. Only content from
                            chapters < current_chapter will be returned.
            n_results: Maximum number of results.
            rerank: Whether to apply cross-encoder re-ranking.
            
        Returns:
            List of RetrievalResult objects from allowed chapters only.
        """
        logger.info(f"Lobotomized retrieval: query='{query[:50]}...', max_chapter={current_chapter}")
        
        # Vector search with chapter filter
        vector_results = []
        try:
            raw_results = self.vector_store.search(
                query=query,
                n_results=n_results * 2,
                max_chapter=current_chapter,
            )
            for r in raw_results:
                vector_results.append(RetrievalResult(
                    id=r.get("id", ""),
                    content=r.get("content", ""),
                    source="vector",
                    score=r.get("score", 0.5),
                    metadata=r.get("metadata", {}),
                ))
        except Exception as e:
            logger.error(f"Lobotomized vector search failed: {e}")
        
        # Graph search with chapter filter
        graph_results = []
        try:
            raw_graph = self.graph_client.search_concepts(
                query=query,
                max_chapter=current_chapter,
                limit=n_results,
            )
            for r in raw_graph:
                node = r.get("node", {})
                graph_results.append(RetrievalResult(
                    id=node.get("node_id", node.get("id", "")),
                    content=f"[{r.get('types', ['Node'])[0]}] {node.get('name', '')}: {node.get('description', '')}",
                    source="graph",
                    score=0.7,
                    metadata={"chapter": node.get("chapter"), "types": r.get("types", [])},
                ))
        except Exception as e:
            logger.error(f"Lobotomized graph search failed: {e}")
        
        logger.info(f"Lobotomized results: vector={len(vector_results)}, graph={len(graph_results)}")
        
        # Merge and deduplicate
        merged = self._merge_results(vector_results, graph_results)
        
        # Re-rank
        if rerank and merged:
            merged = self.reranker.rerank(query, merged, top_k=n_results)
        else:
            merged = merged[:n_results]
        
        return merged
    
    def close(self):
        """Close all connections."""
        self.graph_client.close()



class MockHybridRetriever:
    """Mock retriever for testing."""
    
    def __init__(self):
        self.vector_store = MockChromaVectorStore()
        self.graph_client = MockNeo4jClient()
        self.query_refiner = MockQueryRefiner()
        self.reranker = MockCrossEncoderReranker()
    
    def retrieve(
        self,
        query: str,
        use_refinement: bool = True,
        n_results: int = 10,
        **kwargs,
    ) -> ReasoningPacket:
        return ReasoningPacket(
            query=query,
            refined_query=query,
            results=[
                RetrievalResult(
                    id="mock_1",
                    content="Mock result for testing",
                    source="vector",
                    score=0.95,
                ),
            ],
            graph_context={},
            total_results=1,
            vector_count=1,
            graph_count=0,
        )
    
    def close(self):
        pass
