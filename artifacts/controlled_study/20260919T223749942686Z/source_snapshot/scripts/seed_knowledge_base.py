#!/usr/bin/env python3
"""
Data Seeding Script for MathemaTest Knowledge Base.

Seeds Neo4j and ChromaDB with Phase 1.5 stress test results
using GPT-4o-mini for entity extraction.
"""

import json
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import get_settings, BudgetTracker
from src.graph_store.neo4j_client import Neo4jClient, MockNeo4jClient
from src.graph_store.graph_constructor import GraphConstructorAgent, MockGraphConstructorAgent
from src.vector_store.chroma_client import ChromaVectorStore, MockChromaVectorStore
from src.vector_store.embeddings import EmbeddingService, MockEmbeddingService


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def seed_knowledge_base(
    use_mock: bool = False,
    max_items: int = None,
) -> dict:
    """Seed Neo4j and ChromaDB with stress test data.
    
    Args:
        use_mock: Use mock clients (no API calls).
        max_items: Limit items to process.
        
    Returns:
        Seeding summary.
    """
    settings = get_settings()
    budget = BudgetTracker(settings)
    
    # Load stress test results
    results_path = settings.stress_test_output / "stress_test_results.json"
    if not results_path.exists():
        raise FileNotFoundError(f"Stress test results not found: {results_path}")
    
    with open(results_path) as f:
        results = json.load(f)
    
    cases = results.get("cases", [])
    if max_items:
        cases = cases[:max_items]
    
    logger.info(f"Loaded {len(cases)} cases from stress test results")
    
    # Initialize clients
    if use_mock:
        logger.info("Using MOCK clients (no API calls)")
        graph_agent = MockGraphConstructorAgent()
        vector_store = MockChromaVectorStore()
    else:
        logger.info("Using REAL clients")
        graph_agent = GraphConstructorAgent(settings=settings, budget_tracker=budget)
        vector_store = ChromaVectorStore(settings=settings)
    
    summary = {
        "total_cases": len(cases),
        "graph_nodes": 0,
        "graph_relationships": 0,
        "graph_misconceptions": 0,
        "vector_documents": 0,
        "errors": [],
    }
    
    # === SEED NEO4J ===
    logger.info("=" * 50)
    logger.info("SEEDING NEO4J KNOWLEDGE GRAPH")
    logger.info("=" * 50)
    
    for i, case in enumerate(cases):
        logger.info(f"[{i+1}/{len(cases)}] Processing: {case.get('name', 'unknown')}")
        
        try:
            # Extract entities via GPT-4o-mini
            extraction = graph_agent.extract_from_content(
                content=case,
                source_id=case.get("source", "stress_test"),
                page_number=i + 1,
            )
            
            if extraction:
                # Persist to graph
                counts = graph_agent.persist_extraction(
                    result=extraction,
                    source_id=case.get("source", "stress_test"),
                )
                
                summary["graph_nodes"] += counts.get("nodes", 0)
                summary["graph_relationships"] += counts.get("relationships", 0)
                summary["graph_misconceptions"] += counts.get("misconceptions", 0)
                
                logger.info(f"  → Nodes: {counts.get('nodes', 0)}, "
                           f"Relationships: {counts.get('relationships', 0)}, "
                           f"Misconceptions: {counts.get('misconceptions', 0)}")
                
        except Exception as e:
            logger.error(f"  ERROR: {e}")
            summary["errors"].append({"case": case.get("name"), "error": str(e)})
    
    # === SEED CHROMADB ===
    logger.info("=" * 50)
    logger.info("SEEDING CHROMADB VECTOR STORE")
    logger.info("=" * 50)
    
    documents = []
    for case in cases:
        # Create document for each case
        doc = {
            "id": f"stress_test_{case.get('name', '')}",
            "content": f"{case.get('description', '')} | LaTeX: {case.get('normalized_latex', '')}",
            "source": case.get("source", "stress_test"),
            "name": case.get("name", ""),
            "raw_latex": case.get("raw_latex", ""),
            "normalized_latex": case.get("normalized_latex", ""),
            "sympy_compatible": case.get("sympy_compatible", False),
            "type": "formula",
        }
        documents.append(doc)
    
    try:
        count = vector_store.add_documents(documents)
        summary["vector_documents"] = count
        logger.info(f"Added {count} documents to vector store")
    except Exception as e:
        logger.error(f"Vector store error: {e}")
        summary["errors"].append({"component": "vector_store", "error": str(e)})
    
    # === SUMMARY ===
    logger.info("=" * 50)
    logger.info("SEEDING COMPLETE")
    logger.info("=" * 50)
    logger.info(f"Graph Nodes: {summary['graph_nodes']}")
    logger.info(f"Graph Relationships: {summary['graph_relationships']}")
    logger.info(f"Graph Misconceptions: {summary['graph_misconceptions']}")
    logger.info(f"Vector Documents: {summary['vector_documents']}")
    
    if not use_mock:
        logger.info(f"Budget Used: ${budget.total_spent:.4f}")
        logger.info(f"Budget Remaining: ${budget.remaining_budget:.4f}")
        summary["budget_used"] = budget.total_spent
    
    if summary["errors"]:
        logger.warning(f"Errors: {len(summary['errors'])}")
    
    # Close connections
    graph_agent.close()
    
    return summary


def verify_graph_query() -> dict:
    """Verify graph can answer prerequisite queries.
    
    Test query: "Retrieve prerequisites for Snowplough differential equation"
    """
    logger.info("=" * 50)
    logger.info("VERIFICATION: Graph Traversal Test")
    logger.info("=" * 50)
    
    settings = get_settings()
    
    try:
        neo4j = Neo4jClient(settings)
        
        # Search for Snowplough-related nodes
        results = neo4j.search_by_latex("frac{dm}{dt}")
        
        logger.info(f"Found {len(results)} nodes matching Snowplough pattern")
        
        if results:
            for r in results[:3]:
                node = r["node"]
                logger.info(f"  → {node.get('name', 'Unknown')}: {node.get('description', '')[:50]}...")
                
                # Get prerequisites
                prereqs = neo4j.get_prerequisites(node.get("id", ""))
                logger.info(f"    Prerequisites: {len(prereqs)}")
                
                # Get misconceptions
                misc = neo4j.get_misconceptions(node.get("id", ""))
                logger.info(f"    Misconceptions: {len(misc)}")
        
        stats = neo4j.get_graph_stats()
        logger.info(f"Graph Stats: {stats}")
        
        neo4j.close()
        return {"status": "success", "results": len(results), "stats": stats}
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return {"status": "error", "message": str(e)}


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Seed MathemaTest Knowledge Base")
    parser.add_argument("--mock", action="store_true", help="Use mock clients")
    parser.add_argument("--max-items", type=int, default=None, help="Limit items")
    parser.add_argument("--verify-only", action="store_true", help="Only run verification")
    
    args = parser.parse_args()
    
    if args.verify_only:
        result = verify_graph_query()
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "success" else 1
    
    summary = seed_knowledge_base(use_mock=args.mock, max_items=args.max_items)
    print(json.dumps(summary, indent=2))
    
    if not args.mock:
        verify_graph_query()
    
    return 0 if not summary["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
