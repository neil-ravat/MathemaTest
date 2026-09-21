#!/usr/bin/env python3
"""
Deep Relationship Extractor for MathemaTest Graph Hardening.

Resolves graph sparsity by extracting cross-source relationships
for every concept node using GPT-4o-mini batch processing.

Target: 150+ cross-source edges (GROUNDED_IN, REQUIRES, SAME_AS)
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
import json
import time

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI
from tqdm import tqdm

from src.config.settings import get_settings
from src.graph_store.neo4j_client import Neo4jClient


logger = logging.getLogger(__name__)


RELATIONSHIP_PROMPT = """You are analyzing mathematical concepts from different educational sources to build a knowledge graph.

Given a SOURCE CONCEPT and a list of TARGET CONCEPTS from other sources, identify the top 3 most logically related targets.

SOURCE CONCEPT:
Name: {source_name}
Source: {source_origin}
Topics: {source_topics}

TARGET CONCEPTS (from other sources):
{target_list}

For each relationship you identify, specify:
1. The target concept name (exactly as listed)
2. The relationship type:
   - REQUIRES: Source requires understanding of Target first (Target is prerequisite)
   - GROUNDED_IN: Source is an application or instance of Target
   - SAME_AS: Source and Target refer to the same mathematical idea

Respond with JSON only:
{{
    "relationships": [
        {{
            "target_name": "exact name from list",
            "relationship_type": "REQUIRES|GROUNDED_IN|SAME_AS",
            "confidence": 0.0-1.0,
            "reason": "brief explanation"
        }}
    ]
}}

Return up to 3 relationships. If no meaningful relationships exist, return empty array.
"""


class DeepRelationshipExtractor:
    """Extract dense cross-source relationships for graph hardening."""
    
    def __init__(self):
        self.settings = get_settings()
        self.neo4j = Neo4jClient()
        self.openai = self.settings.create_openai_client()
        self.stats = {
            "concepts_processed": 0,
            "relationships_created": 0,
            "api_calls": 0,
            "errors": 0,
        }
    
    def get_all_concepts_by_source(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all concepts grouped by source."""
        query = """
        MATCH (c:Concept)
        WHERE c.source_ids IS NOT NULL
        RETURN c.name AS name, c.normalized_name AS norm_name, 
               c.source_ids AS sources, c.topic_tags AS topics
        """
        
        with self.neo4j.session() as session:
            result = session.run(query)
            all_concepts = [dict(r) for r in result]
        
        # Group by primary source
        by_source = {"physics": [], "mit": [], "aime": [], "other": []}
        
        for c in all_concepts:
            sources = c.get("sources", [])
            if not sources:
                by_source["other"].append(c)
                continue
            
            primary = sources[0].lower() if sources else ""
            if "physics" in primary:
                by_source["physics"].append(c)
            elif "mit" in primary or "calculus" in primary:
                by_source["mit"].append(c)
            elif "aime" in primary or "ziml" in primary:
                by_source["aime"].append(c)
            else:
                by_source["other"].append(c)
        
        logger.info(f"Concepts by source: Physics={len(by_source['physics'])}, MIT={len(by_source['mit'])}, AIME={len(by_source['aime'])}")
        return by_source
    
    def find_relationships_for_concept(
        self,
        source_concept: Dict[str, Any],
        target_concepts: List[Dict[str, Any]],
        max_targets: int = 30,
    ) -> List[Dict[str, Any]]:
        """Find relationships from source to targets using GPT-4o-mini."""
        if not target_concepts:
            return []
        
        # Sample targets if too many
        targets = target_concepts[:max_targets]
        
        # Format target list
        target_list = "\n".join([
            f"- {t['name']} (topics: {', '.join(t.get('topics', ['unknown'])[:3])})"
            for t in targets
        ])
        
        prompt = RELATIONSHIP_PROMPT.format(
            source_name=source_concept["name"],
            source_origin=source_concept.get("sources", ["unknown"])[0] if source_concept.get("sources") else "unknown",
            source_topics=", ".join(source_concept.get("topics", ["unknown"])[:5]),
            target_list=target_list,
        )
        
        try:
            response = self.openai.chat.completions.create(
                model=self.settings.default_model,
                messages=[
                    {"role": "system", "content": "You identify mathematical concept relationships. Respond with valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.3,
            )
            
            self.stats["api_calls"] += 1
            
            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            parsed = json.loads(content)
            return parsed.get("relationships", [])
            
        except Exception as e:
            logger.warning(f"Relationship extraction failed: {e}")
            self.stats["errors"] += 1
            return []
    
    def create_relationship(
        self,
        from_name: str,
        to_name: str,
        rel_type: str,
        confidence: float,
        reason: str,
    ) -> bool:
        """Create a relationship in Neo4j."""
        # Validate relationship type
        valid_types = ["REQUIRES", "GROUNDED_IN", "SAME_AS"]
        if rel_type not in valid_types:
            rel_type = "GROUNDED_IN"
        
        query = f"""
        MATCH (a:Concept)
        WHERE toLower(a.name) = toLower($from_name)
        MATCH (b:Concept)
        WHERE toLower(b.name) = toLower($to_name)
        MERGE (a)-[r:{rel_type}]->(b)
        SET r.confidence = $confidence,
            r.reason = $reason,
            r.created_at = datetime()
        RETURN count(r) as count
        """
        
        try:
            with self.neo4j.session() as session:
                result = session.run(query, {
                    "from_name": from_name,
                    "to_name": to_name,
                    "confidence": confidence,
                    "reason": reason,
                })
                count = result.single()["count"]
                return count > 0
        except Exception as e:
            logger.error(f"Failed to create relationship: {e}")
            return False
    
    def process_source_to_targets(
        self,
        source_concepts: List[Dict[str, Any]],
        target_concepts: List[Dict[str, Any]],
        source_name: str,
        target_name: str,
        max_source_concepts: int = 100,
    ) -> int:
        """Process relationships from one source to another."""
        logger.info(f"Processing {source_name} -> {target_name}: {len(source_concepts)} -> {len(target_concepts)}")
        
        relationships_created = 0
        concepts_to_process = source_concepts[:max_source_concepts]
        
        for concept in tqdm(concepts_to_process, desc=f"{source_name}->{target_name}"):
            relationships = self.find_relationships_for_concept(concept, target_concepts)
            
            for rel in relationships:
                if rel.get("confidence", 0) >= 0.5:
                    if self.create_relationship(
                        from_name=concept["name"],
                        to_name=rel["target_name"],
                        rel_type=rel["relationship_type"],
                        confidence=rel.get("confidence", 0.7),
                        reason=rel.get("reason", ""),
                    ):
                        relationships_created += 1
                        self.stats["relationships_created"] += 1
            
            self.stats["concepts_processed"] += 1
            
            # Rate limiting
            time.sleep(0.1)
        
        return relationships_created
    
    def run_full_extraction(self, target_relationships: int = 150) -> Dict[str, Any]:
        """Run full deep relationship extraction.
        
        Args:
            target_relationships: Target number of relationships to create.
            
        Returns:
            Extraction statistics.
        """
        concepts = self.get_all_concepts_by_source()
        
        # Strategy: Cross-pollinate all sources
        # 1. Physics -> MIT (Physics concepts grounded in calculus)
        # 2. MIT -> Physics (Calculus concepts applied in physics)
        # 3. Physics high-level -> Physics basics (internal prerequisites)
        
        pairs = [
            ("physics", "mit", 50),   # Physics grounded in MIT Calculus
            ("mit", "physics", 30),   # MIT Calculus applied to Physics
            ("physics", "physics", 40),  # Internal Physics prerequisites
            ("mit", "mit", 20),       # Internal MIT prerequisites
        ]
        
        for source_key, target_key, max_concepts in pairs:
            if self.stats["relationships_created"] >= target_relationships:
                logger.info(f"Reached target of {target_relationships} relationships")
                break
            
            source = concepts.get(source_key, [])
            target = concepts.get(target_key, [])
            
            if source_key == target_key:
                # For internal relationships, split into two halves
                mid = len(source) // 2
                self.process_source_to_targets(
                    source[:mid],
                    source[mid:],
                    f"{source_key}_A",
                    f"{target_key}_B",
                    max_source_concepts=max_concepts,
                )
            else:
                self.process_source_to_targets(
                    source,
                    target,
                    source_key,
                    target_key,
                    max_source_concepts=max_concepts,
                )
        
        return self.stats
    
    def get_current_edge_count(self) -> Dict[str, int]:
        """Get current edge counts from Neo4j."""
        query = """
        MATCH ()-[r]->()
        RETURN type(r) as rel_type, count(r) as count
        ORDER BY count DESC
        """
        
        with self.neo4j.session() as session:
            result = session.run(query)
            return {r["rel_type"]: r["count"] for r in result}
    
    def close(self):
        """Close connections."""
        self.neo4j.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Deep relationship extraction for graph hardening")
    parser.add_argument("--target", type=int, default=150, help="Target relationship count")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    
    extractor = DeepRelationshipExtractor()
    
    try:
        # Get initial counts
        initial_edges = extractor.get_current_edge_count()
        logger.info(f"Initial edge counts: {initial_edges}")
        
        # Run extraction
        stats = extractor.run_full_extraction(target_relationships=args.target)
        
        # Get final counts
        final_edges = extractor.get_current_edge_count()
        
        print("\n" + "=" * 60)
        print("DEEP RELATIONSHIP EXTRACTION COMPLETE")
        print("=" * 60)
        print(f"Concepts Processed: {stats['concepts_processed']}")
        print(f"API Calls: {stats['api_calls']}")
        print(f"Errors: {stats['errors']}")
        print(f"\nRelationships Created: {stats['relationships_created']}")
        print(f"\nFinal Edge Counts:")
        for rel_type, count in sorted(final_edges.items(), key=lambda x: -x[1]):
            print(f"  {rel_type}: {count}")
        print(f"\nTotal Edges: {sum(final_edges.values())}")
    
    finally:
        extractor.close()


if __name__ == "__main__":
    main()
