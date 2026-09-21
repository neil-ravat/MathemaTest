#!/usr/bin/env python3
"""
Cross-Source Relationship Extraction for MathemaTest Phase A.

Extracts logical relationships between concepts across different sources:
- PREREQUISITE_OF: MIT Calculus → Physics applications
- GROUNDED_IN: AIME problems → foundational definitions
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI
from tqdm import tqdm
import json

from src.config.settings import get_settings, BudgetTracker
from src.graph_store.neo4j_client import Neo4jClient
from src.vector_store.chroma_client import ChromaVectorStore


logger = logging.getLogger(__name__)


CROSS_SOURCE_EXTRACTION_PROMPT = """You are analyzing mathematical concepts from different educational sources. Given two concepts from different sources, determine if they have a logical relationship.

CONCEPT A (from {source_a}):
Name: {name_a}
Topic: {topic_a}

CONCEPT B (from {source_b}):
Name: {name_b}
Topic: {topic_b}

RELATIONSHIP TYPES:
- PREREQUISITE_OF: Concept A must be understood before Concept B (e.g., derivatives before integrals)
- GROUNDED_IN: Concept B is an application or instance of Concept A (e.g., physics problem using calculus)
- SAME_AS: Both concepts refer to the same mathematical idea
- NONE: No significant relationship

Respond with JSON only:
{{
    "relationship_type": "PREREQUISITE_OF|GROUNDED_IN|SAME_AS|NONE",
    "direction": "A_TO_B|B_TO_A|BIDIRECTIONAL",
    "confidence": 0.0-1.0,
    "reason": "Brief explanation"
}}
"""


class CrossSourceRelationshipExtractor:
    """Extract relationships between concepts from different sources."""
    
    def __init__(self):
        self.settings = get_settings()
        self.neo4j = Neo4jClient()
        self.openai = self.settings.create_openai_client()
        self.budget = BudgetTracker(self.settings)
    
    def get_concepts_by_source(self, source_pattern: str = None) -> List[Dict[str, Any]]:
        """Get all concepts from Neo4j, optionally filtered by source."""
        if source_pattern:
            query = """
            MATCH (c:Concept)
            WHERE any(s IN c.source_ids WHERE s CONTAINS $pattern)
            RETURN c.name AS name, c.normalized_name AS normalized_name, 
                   c.source_ids AS sources, c.topic_tags AS topics
            LIMIT 100
            """
            with self.neo4j.session() as session:
                result = session.run(query, {"pattern": source_pattern})
                return [dict(r) for r in result]
        else:
            query = """
            MATCH (c:Concept)
            RETURN c.name AS name, c.normalized_name AS normalized_name, 
                   c.source_ids AS sources, c.topic_tags AS topics
            LIMIT 200
            """
            with self.neo4j.session() as session:
                result = session.run(query)
                return [dict(r) for r in result]
    
    def find_cross_source_pairs(self) -> List[Dict[str, Any]]:
        """Find pairs of concepts that appear in multiple sources."""
        # First, get concepts from each source category
        physics_concepts = self.get_concepts_by_source("Physics")
        mit_concepts = self.get_concepts_by_source("mit_calculus")
        aime_concepts = self.get_concepts_by_source("AIME")
        
        logger.info(f"Found concepts: Physics={len(physics_concepts)}, MIT={len(mit_concepts)}, AIME={len(aime_concepts)}")
        
        # Create pairs for relationship detection
        pairs = []
        
        # MIT → Physics pairs
        for mit in mit_concepts[:20]:  # Limit to avoid excessive API calls
            for phys in physics_concepts[:30]:
                pairs.append({
                    "a": {"name": mit["name"], "source": "MIT Calculus", "topic": mit.get("topics", ["calculus"])[0] if mit.get("topics") else "calculus"},
                    "b": {"name": phys["name"], "source": "OpenStax Physics", "topic": phys.get("topics", ["physics"])[0] if phys.get("topics") else "physics"},
                })
        
        # MIT → AIME pairs
        for mit in mit_concepts[:10]:
            for aime in aime_concepts[:5]:
                pairs.append({
                    "a": {"name": mit["name"], "source": "MIT Calculus", "topic": mit.get("topics", ["calculus"])[0] if mit.get("topics") else "calculus"},
                    "b": {"name": aime["name"], "source": "AIME Competition", "topic": aime.get("topics", ["competition"])[0] if aime.get("topics") else "competition"},
                })
        
        return pairs
    
    def analyze_pair(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a pair of concepts for relationships."""
        prompt = CROSS_SOURCE_EXTRACTION_PROMPT.format(
            source_a=pair["a"]["source"],
            name_a=pair["a"]["name"],
            topic_a=pair["a"]["topic"],
            source_b=pair["b"]["source"],
            name_b=pair["b"]["name"],
            topic_b=pair["b"]["topic"],
        )
        
        try:
            response = self.openai.chat.completions.create(
                model=self.settings.default_model,
                messages=[
                    {"role": "system", "content": "You analyze mathematical concept relationships. Respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=200,
                temperature=0.3,
            )
            
            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            return json.loads(content)
        except Exception as e:
            logger.warning(f"Failed to analyze pair: {e}")
            return {"relationship_type": "NONE", "confidence": 0, "reason": str(e)}
    
    def create_relationship_in_neo4j(
        self,
        from_concept: str,
        to_concept: str,
        rel_type: str,
        properties: Dict[str, Any],
    ) -> bool:
        """Create a relationship between concepts in Neo4j."""
        query = """
        MATCH (a:Concept {normalized_name: $from_name})
        MATCH (b:Concept {normalized_name: $to_name})
        MERGE (a)-[r:""" + rel_type + """]->(b)
        SET r.confidence = $confidence,
            r.reason = $reason,
            r.created_at = datetime()
        RETURN count(r) as count
        """
        
        try:
            with self.neo4j.session() as session:
                result = session.run(query, {
                    "from_name": from_concept.lower().strip(),
                    "to_name": to_concept.lower().strip(),
                    "confidence": properties.get("confidence", 0.5),
                    "reason": properties.get("reason", ""),
                })
                return result.single()["count"] > 0
        except Exception as e:
            logger.error(f"Failed to create relationship: {e}")
            return False
    
    def extract_all_relationships(self, max_pairs: int = 50) -> Dict[str, Any]:
        """Extract all cross-source relationships.
        
        Args:
            max_pairs: Maximum pairs to analyze (for budget control).
            
        Returns:
            Extraction statistics.
        """
        pairs = self.find_cross_source_pairs()[:max_pairs]
        
        logger.info(f"Analyzing {len(pairs)} concept pairs...")
        
        stats = {
            "pairs_analyzed": 0,
            "relationships_found": 0,
            "prerequisite_of": 0,
            "grounded_in": 0,
            "same_as": 0,
        }
        
        for pair in tqdm(pairs, desc="Analyzing pairs"):
            result = self.analyze_pair(pair)
            stats["pairs_analyzed"] += 1
            
            if result["relationship_type"] != "NONE" and result.get("confidence", 0) > 0.5:
                # Determine direction
                if result.get("direction") == "B_TO_A":
                    from_concept = pair["b"]["name"]
                    to_concept = pair["a"]["name"]
                else:
                    from_concept = pair["a"]["name"]
                    to_concept = pair["b"]["name"]
                
                rel_type = result["relationship_type"]
                
                if self.create_relationship_in_neo4j(
                    from_concept,
                    to_concept,
                    rel_type,
                    {"confidence": result.get("confidence", 0.5), "reason": result.get("reason", "")},
                ):
                    stats["relationships_found"] += 1
                    stats[rel_type.lower()] = stats.get(rel_type.lower(), 0) + 1
                    logger.info(f"Created: {from_concept} -{rel_type}-> {to_concept}")
        
        return stats
    
    def create_formula_based_links(self) -> int:
        """Create links based on formula matching using LaTeX normalization."""
        from src.ingestion.latex_normalizer import LaTeXNormalizer
        
        normalizer = LaTeXNormalizer()
        
        # Get all formula-related concepts
        query = """
        MATCH (c:Concept)
        WHERE c.name CONTAINS 'formula' OR c.name CONTAINS 'equation' 
              OR c.name CONTAINS 'theorem' OR c.name CONTAINS 'identity'
        RETURN c.name AS name, c.normalized_name AS norm_name, c.source_ids AS sources
        """
        
        with self.neo4j.session() as session:
            result = session.run(query)
            concepts = [dict(r) for r in result]
        
        # Find matching concepts by normalized name
        links_created = 0
        seen_pairs = set()
        
        for i, c1 in enumerate(concepts):
            for c2 in concepts[i+1:]:
                # Skip if same source
                if c1.get("sources") == c2.get("sources"):
                    continue
                
                pair_key = tuple(sorted([c1["norm_name"], c2["norm_name"]]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                
                # Check for normalized name match
                if c1["norm_name"] == c2["norm_name"]:
                    if self.create_relationship_in_neo4j(
                        c1["name"], c2["name"], "SAME_AS",
                        {"confidence": 1.0, "reason": "Identical normalized name"}
                    ):
                        links_created += 1
                        logger.info(f"Formula match: {c1['name']} == {c2['name']}")
        
        return links_created
    
    def close(self):
        """Close connections."""
        self.neo4j.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Extract cross-source relationships")
    parser.add_argument("--max-pairs", type=int, default=30, help="Max pairs to analyze")
    parser.add_argument("--formula-links-only", action="store_true", help="Only create formula-based links")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    
    extractor = CrossSourceRelationshipExtractor()
    
    try:
        if args.formula_links_only:
            links = extractor.create_formula_based_links()
            print(f"\n=== FORMULA LINKS CREATED: {links} ===")
        else:
            # First, create formula-based links
            formula_links = extractor.create_formula_based_links()
            logger.info(f"Created {formula_links} formula-based links")
            
            # Then, extract semantic relationships
            stats = extractor.extract_all_relationships(max_pairs=args.max_pairs)
            
            print("\n" + "=" * 60)
            print("CROSS-SOURCE RELATIONSHIP EXTRACTION COMPLETE")
            print("=" * 60)
            print(f"Pairs Analyzed: {stats['pairs_analyzed']}")
            print(f"Relationships Found: {stats['relationships_found']}")
            print(f"  - PREREQUISITE_OF: {stats.get('prerequisite_of', 0)}")
            print(f"  - GROUNDED_IN: {stats.get('grounded_in', 0)}")
            print(f"  - SAME_AS: {stats.get('same_as', 0) + formula_links}")
    
    finally:
        extractor.close()


if __name__ == "__main__":
    main()
