#!/usr/bin/env python3
"""
Hydrate ChromaDB from Neo4j Graph.

Transfers text content from Neo4j nodes to ChromaDB vector store
without re-running PDF ingestion (read-only access to Neo4j).

Properties used:
- description: Primary text content
- statement: Mathematical statement (combined with description)
- name: Node title for search context
- chapter: Integer chapter number (critical for filtering)
- source: Source identifier
"""

import sys
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm
from src.config.settings import get_settings
from src.graph_store.neo4j_client import Neo4jClient
from src.vector_store.chroma_client import ChromaVectorStore


def fetch_all_nodes_with_text(client: Neo4jClient) -> List[Dict[str, Any]]:
    """Fetch all nodes that have text content from Neo4j."""
    
    query = """
    MATCH (n)
    WHERE n.description IS NOT NULL OR n.statement IS NOT NULL
    RETURN 
        n.node_id as node_id,
        labels(n)[0] as label,
        n.name as name,
        n.description as description,
        n.statement as statement,
        n.chapter as chapter,
        n.source as source,
        n.section as section,
        n.page_start as page_start,
        n.page_end as page_end
    """
    
    nodes = []
    with client.session() as session:
        result = session.run(query)
        for record in result:
            nodes.append({
                "node_id": record["node_id"],
                "label": record["label"],
                "name": record["name"],
                "description": record["description"],
                "statement": record["statement"],
                "chapter": record["chapter"],
                "source": record["source"],
                "section": record["section"],
                "page_start": record["page_start"],
                "page_end": record["page_end"],
            })
    
    return nodes


def build_text_content(node: Dict[str, Any]) -> str:
    """Build searchable text content from node properties."""
    
    parts = []
    
    # Add label as context
    if node.get("label"):
        parts.append(f"[{node['label']}]")
    
    # Add name/title
    if node.get("name"):
        parts.append(f"{node['name']}:")
    
    # Add description (primary content)
    if node.get("description"):
        parts.append(node["description"])
    
    # Add statement (mathematical content)
    if node.get("statement") and node["statement"] != node.get("description"):
        parts.append(f"Statement: {node['statement']}")
    
    return " ".join(parts).strip()


def build_metadata(node: Dict[str, Any]) -> Dict[str, Any]:
    """Build ChromaDB metadata from node properties.
    
    CRITICAL: chapter must be an int for lobotomy filtering.
    """
    
    metadata = {
        "label": node.get("label", "Unknown"),
        "source": node.get("source", "OpenStax-Calculus"),
    }
    
    # Chapter MUST be int
    chapter = node.get("chapter")
    if chapter is not None:
        metadata["chapter"] = int(chapter)
    else:
        metadata["chapter"] = 0  # Default to 0 if missing
    
    # Optional fields
    if node.get("name"):
        metadata["name"] = node["name"][:200]  # Truncate for ChromaDB limits
    
    if node.get("section"):
        metadata["section"] = str(node["section"])
    
    if node.get("page_start"):
        metadata["page_start"] = int(node["page_start"])
    
    if node.get("page_end"):
        metadata["page_end"] = int(node["page_end"])
    
    return metadata


def hydrate_chroma():
    """Main hydration function."""
    
    print("=" * 60)
    print("CHROMADB HYDRATION FROM NEO4J")
    print("=" * 60)
    
    # Initialize clients
    settings = get_settings()
    neo4j_client = Neo4jClient()
    chroma_store = ChromaVectorStore()
    
    print(f"Neo4j: {settings.neo4j_uri}")
    print(f"ChromaDB: {settings.chroma_persist_directory}")
    print()
    
    # Fetch all nodes
    print("[1] Fetching nodes from Neo4j...")
    nodes = fetch_all_nodes_with_text(neo4j_client)
    print(f"    Found {len(nodes)} nodes with text content")
    print()
    
    # Filter nodes with actual content
    valid_nodes = []
    for node in nodes:
        text = build_text_content(node)
        if len(text) > 20:  # Skip very short content
            valid_nodes.append((node, text))
    
    print(f"    Valid nodes (>20 chars): {len(valid_nodes)}")
    print()
    
    # Prepare data for ChromaDB
    print("[2] Preparing ChromaDB documents...")
    
    ids = []
    documents = []
    metadatas = []
    
    for i, (node, text) in enumerate(valid_nodes):
        # Generate UNIQUE compound ID: label + node_id + index
        label = node.get("label", "Node")
        base_id = node.get("node_id") or str(i)
        chapter = node.get("chapter", 0)
        # Create unique ID by combining label, chapter, base_id, and index
        unique_id = f"{label}_ch{chapter}_{base_id}_{i}"
        
        ids.append(unique_id)
        documents.append(text)
        metadatas.append(build_metadata(node))
    
    # Batch upsert to ChromaDB
    print(f"[3] Upserting {len(documents)} documents to ChromaDB...")
    
    batch_size = 100
    total_batches = (len(documents) + batch_size - 1) // batch_size
    
    for i in tqdm(range(0, len(documents), batch_size), total=total_batches, desc="Upserting"):
        batch_ids = ids[i:i+batch_size]
        batch_docs = documents[i:i+batch_size]
        batch_meta = metadatas[i:i+batch_size]
        
        try:
            chroma_store.collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                metadatas=batch_meta,
            )
        except Exception as e:
            print(f"    ⚠️ Batch {i//batch_size + 1} failed: {e}")
    
    # Verify final count
    final_count = chroma_store.collection.count()
    
    print()
    print("=" * 60)
    print("HYDRATION COMPLETE")
    print("=" * 60)
    print(f"Nodes processed: {len(valid_nodes)}")
    print(f"ChromaDB final count: {final_count}")
    
    # Sample verification
    print()
    print("[4] Sample verification (peek):")
    peek = chroma_store.collection.peek(3)
    for i, (doc_id, meta) in enumerate(zip(peek["ids"], peek["metadatas"]), 1):
        print(f"    [{i}] ID: {doc_id[:40]}...")
        print(f"        chapter: {meta.get('chapter')} (type: {type(meta.get('chapter')).__name__})")
        print(f"        label: {meta.get('label')}")
        print(f"        source: {meta.get('source')}")
    
    # Cleanup
    neo4j_client.close()
    
    return final_count


if __name__ == "__main__":
    hydrate_chroma()
