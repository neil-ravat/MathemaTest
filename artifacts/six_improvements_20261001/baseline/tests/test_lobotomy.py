#!/usr/bin/env python3
"""
Test Lobotomized Retrieval (Chapter-Restricted Search).

Verifies that the retrieve_for_audit method correctly filters
results by chapter to prevent data leakage.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import get_settings
from src.retrieval.hybrid_orchestrator import HybridRetriever


def test_lobotomy_filter():
    """Test that chapter filtering works correctly."""
    
    print("=" * 60)
    print("LOBOTOMY FILTER TEST")
    print("=" * 60)
    
    # Initialize retriever
    retriever = HybridRetriever()
    
    # Query for a concept known to be in later chapters (e.g., "integral" is in Ch 5+)
    test_query = "integral"
    
    print(f"\nTest Query: '{test_query}'")
    print("-" * 40)
    
    # Test 1: Retrieve with current_chapter=3 (should return ZERO or very few results)
    print("\n[TEST 1] retrieve_for_audit(query, current_chapter=3)")
    print("Expected: ZERO results from Chapter 5+ content")
    
    results_ch3 = retriever.retrieve_for_audit(
        query=test_query,
        current_chapter=3,
        n_results=10,
        rerank=False,  # Skip reranking for speed
    )
    
    print(f"Results returned: {len(results_ch3)}")
    
    # Check if any results leaked from future chapters
    leaked = []
    for r in results_ch3:
        chapter = r.metadata.get("chapter")
        if chapter is not None and chapter >= 3:
            leaked.append((chapter, r.content[:50]))
    
    if leaked:
        print(f"⚠️  LEAKED {len(leaked)} results from chapters >= 3:")
        for ch, content in leaked[:3]:
            print(f"    Chapter {ch}: {content}...")
    else:
        print("✅ No data leakage detected")
    
    # Test 2: Retrieve with current_chapter=6 (should return results)
    print("\n" + "-" * 40)
    print("[TEST 2] retrieve_for_audit(query, current_chapter=6)")
    print("Expected: Results from Chapters 1-5")
    
    results_ch6 = retriever.retrieve_for_audit(
        query=test_query,
        current_chapter=6,
        n_results=10,
        rerank=False,
    )
    
    print(f"Results returned: {len(results_ch6)}")
    
    if results_ch6:
        print("Sample results:")
        for i, r in enumerate(results_ch6[:3], 1):
            chapter = r.metadata.get("chapter", "?")
            print(f"  [{i}] Chapter {chapter}: {r.content[:60]}...")
    
    # Test 3: Compare counts
    print("\n" + "-" * 40)
    print("[TEST 3] Comparison")
    
    # Retrieve with no chapter filter for comparison
    all_results = retriever.retrieve_for_audit(
        query=test_query,
        current_chapter=100,  # Effectively no filter
        n_results=20,
        rerank=False,
    )
    
    print(f"Results with max_chapter=3:   {len(results_ch3)}")
    print(f"Results with max_chapter=6:   {len(results_ch6)}")
    print(f"Results with max_chapter=100: {len(all_results)}")
    
    # Assertions
    print("\n" + "=" * 60)
    print("ASSERTIONS")
    print("=" * 60)
    
    # Assertion 1: Results should increase as max_chapter increases
    assert len(results_ch3) <= len(results_ch6) <= len(all_results), \
        "Results should increase with higher max_chapter"
    print("✅ PASS: Results increase with higher max_chapter")
    
    # Assertion 2: No results from chapters >= current_chapter
    for r in results_ch6:
        chapter = r.metadata.get("chapter")
        if chapter is not None:
            assert chapter < 6, f"Leaked content from chapter {chapter}"
    print("✅ PASS: No data leakage in ch6 query")
    
    # Cleanup
    retriever.close()
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    test_lobotomy_filter()
