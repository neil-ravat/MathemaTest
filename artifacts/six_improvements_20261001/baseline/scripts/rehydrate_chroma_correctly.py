#!/usr/bin/env python3
"""
Re-Hydrate ChromaDB with Correct Embeddings.

Fixes embedding dimension mismatch by:
1. Wiping the existing collection (384-dim)
2. Re-generating embeddings with all-mpnet-base-v2 (768-dim)
3. Upserting with explicit embeddings

This uses the SAME embedding model as src/config/settings.py.
"""

import sys
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from src.config.settings import get_settings
from src.graph_store.neo4j_client import Neo4jClient


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
    
    if node.get("label"):
        parts.append(f"[{node['label']}]")
    
    if node.get("name"):
        parts.append(f"{node['name']}:")
    
    if node.get("description"):
        parts.append(node["description"])
    
    if node.get("statement") and node["statement"] != node.get("description"):
        parts.append(f"Statement: {node['statement']}")
    
    return " ".join(parts).strip()


def build_metadata(node: Dict[str, Any]) -> Dict[str, Any]:
    """Build ChromaDB metadata from node properties."""
    
    metadata = {
        "label": node.get("label", "Unknown"),
        "source": node.get("source", "OpenStax-Calculus"),
    }
    
    # Chapter MUST be int
    chapter = node.get("chapter")
    if chapter is not None:
        metadata["chapter"] = int(chapter)
    else:
        metadata["chapter"] = 0
    
    if node.get("name"):
        metadata["name"] = node["name"][:200]
    
    if node.get("section"):
        metadata["section"] = str(node["section"])
    
    if node.get("page_start"):
        metadata["page_start"] = int(node["page_start"])
    
    if node.get("page_end"):
        metadata["page_end"] = int(node["page_end"])
    
    return metadata


def rehydrate_chroma():
    """Main re-hydration function with correct embeddings."""
    
    print("=" * 60)
    print("CHROMADB RE-HYDRATION (768-dim)")
    print("=" * 60)
    
    settings = get_settings()
    
    # Step 1: Initialize Sentence Transformer with CORRECT model
    print(f"\n[1] Loading embedding model: {settings.embedding_model}")
    model = SentenceTransformer(settings.embedding_model)
    embedding_dim = model.get_sentence_embedding_dimension()
    print(f"    Embedding dimension: {embedding_dim}")
    
    if embedding_dim != 768:
        print(f"    ⚠️  Warning: Expected 768, got {embedding_dim}")
    
    # Step 2: Wipe existing collection
    print(f"\n[2] Wiping existing ChromaDB collection...")
    chroma_path = settings.get_chroma_path()
    client = chromadb.PersistentClient(path=str(chroma_path))
    
    try:
        client.delete_collection(settings.chroma_collection_name)
        print(f"    Deleted: {settings.chroma_collection_name}")
    except Exception as e:
        print(f"    No existing collection to delete: {e}")
    
    # Create fresh collection with explicit embedding function disabled
    collection = client.create_collection(
        name=settings.chroma_collection_name,
        metadata={"description": "MathemaTest content chunks (768-dim)"},
    )
    print(f"    Created fresh collection: {settings.chroma_collection_name}")
    
    # Step 3: Fetch data from Neo4j
    print(f"\n[3] Fetching nodes from Neo4j...")
    neo4j_client = Neo4jClient()
    nodes = fetch_all_nodes_with_text(neo4j_client)
    print(f"    Found {len(nodes)} nodes with text content")
    
    # Build text content
    valid_entries = []
    for i, node in enumerate(nodes):
        text = build_text_content(node)
        if len(text) > 20:
            label = node.get("label", "Node")
            base_id = node.get("node_id") or str(i)
            chapter = node.get("chapter", 0)
            unique_id = f"{label}_ch{chapter}_{base_id}_{i}"
            
            valid_entries.append({
                "id": unique_id,
                "text": text,
                "metadata": build_metadata(node),
            })
    
    print(f"    Valid entries: {len(valid_entries)}")
    
    # Step 4: Batch process with explicit embeddings
    print(f"\n[4] Generating embeddings and upserting...")
    
    batch_size = 100
    total_batches = (len(valid_entries) + batch_size - 1) // batch_size
    
    for i in tqdm(range(0, len(valid_entries), batch_size), total=total_batches, desc="Upserting"):
        batch = valid_entries[i:i+batch_size]
        
        # Extract batch data
        batch_ids = [e["id"] for e in batch]
        batch_texts = [e["text"] for e in batch]
        batch_metadatas = [e["metadata"] for e in batch]
        
        # Generate embeddings explicitly
        embeddings = model.encode(batch_texts, show_progress_bar=False)
        
        # Upsert with explicit embeddings (CRITICAL: this prevents Chroma from computing its own)
        collection.upsert(
            ids=batch_ids,
            documents=batch_texts,
            embeddings=embeddings.tolist(),
            metadatas=batch_metadatas,
        )
    
    # Step 5: Verify
    final_count = collection.count()
    
    print()
    print("=" * 60)
    print("RE-HYDRATION COMPLETE")
    print("=" * 60)
    print(f"Documents added: {len(valid_entries)}")
    print(f"ChromaDB final count: {final_count}")
    print(f"Embedding dimension: {embedding_dim}")
    
    # Sample verification
    print()
    print("[5] Sample verification (peek):")
    peek = collection.peek(3)
    for i, (doc_id, meta) in enumerate(zip(peek["ids"], peek["metadatas"]), 1):
        print(f"    [{i}] ID: {doc_id[:40]}...")
        print(f"        chapter: {meta.get('chapter')} (type: {type(meta.get('chapter')).__name__})")
        print(f"        label: {meta.get('label')}")
    
    # Cleanup
    neo4j_client.close()
    
    return final_count


if __name__ == "__main__":
    rehydrate_chroma()
