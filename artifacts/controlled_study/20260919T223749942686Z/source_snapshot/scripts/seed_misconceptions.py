#!/usr/bin/env python3
"""
Seed Misconception Nodes in Neo4j.

Phase C Task 5: Enforced Misconceptions for MCQ Distractors.

Creates :Misconception nodes linked to :Concept nodes via HAS_MISCONCEPTION.
Each misconception represents a common student error that can be used
to generate diagnostic distractors.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph_store.neo4j_client import Neo4jClient


logger = logging.getLogger(__name__)


# Common mathematical misconceptions by topic
# These are research-validated common student errors
MISCONCEPTIONS = [
    # Algebra misconceptions
    {
        "concept": "derivative",
        "description": "Forgetting the chain rule",
        "common_error": "d/dx(sin(x²)) = cos(x²) instead of 2x·cos(x²)",
        "topic": "calculus",
    },
    {
        "concept": "derivative",
        "description": "Product rule sign error",
        "common_error": "d/dx(fg) = f'g' instead of f'g + fg'",
        "topic": "calculus",
    },
    {
        "concept": "integration",
        "description": "Forgetting constant of integration",
        "common_error": "∫2x dx = x² instead of x² + C",
        "topic": "calculus",
    },
    {
        "concept": "limits",
        "description": "Substitution without checking continuity",
        "common_error": "lim(x→0) sin(x)/x = sin(0)/0 = undefined (should be 1)",
        "topic": "calculus",
    },
    {
        "concept": "exponents",
        "description": "Adding exponents when bases multiply",
        "common_error": "2³ × 3² = 6⁵ instead of 8 × 9 = 72",
        "topic": "algebra",
    },
    {
        "concept": "quadratic",
        "description": "Sign error in quadratic formula",
        "common_error": "x = (-b + √(b²-4ac))/2a instead of ±",
        "topic": "algebra",
    },
    {
        "concept": "logarithm",
        "description": "Log of a sum equals sum of logs",
        "common_error": "log(a+b) = log(a) + log(b) (incorrect)",
        "topic": "algebra",
    },
    {
        "concept": "trigonometry",
        "description": "Confusing radians and degrees",
        "common_error": "sin(90) = 1 instead of sin(π/2) = 1",
        "topic": "trigonometry",
    },
    {
        "concept": "trigonometry",
        "description": "Pythagorean identity sign error",
        "common_error": "sin²θ - cos²θ = 1 instead of sin²θ + cos²θ = 1",
        "topic": "trigonometry",
    },
    {
        "concept": "vectors",
        "description": "Adding magnitudes instead of components",
        "common_error": "|a + b| = |a| + |b| (only true if parallel)",
        "topic": "linear_algebra",
    },
    {
        "concept": "determinant",
        "description": "Incorrect 3x3 determinant expansion",
        "common_error": "Missing alternating signs in cofactor expansion",
        "topic": "linear_algebra",
    },
    {
        "concept": "probability",
        "description": "Multiplying probabilities for non-independent events",
        "common_error": "P(A∩B) = P(A)·P(B) when events are dependent",
        "topic": "probability",
    },
    {
        "concept": "combinatorics",
        "description": "Permutation vs combination confusion",
        "common_error": "Using nPr when order doesn't matter (should use nCr)",
        "topic": "combinatorics",
    },
    {
        "concept": "modular arithmetic",
        "description": "Dividing in modular arithmetic",
        "common_error": "6/2 ≡ 3 (mod 4) without checking multiplicative inverse",
        "topic": "number_theory",
    },
    {
        "concept": "complex numbers",
        "description": "Using absolute value instead of modulus",
        "common_error": "|3+4i| = 3 or 4 instead of √(3²+4²) = 5",
        "topic": "complex_analysis",
    },
    {
        "concept": "sets",
        "description": "Confusing subset and element",
        "common_error": "{1} ∈ {1,2,3} instead of {1} ⊂ {1,2,3}",
        "topic": "set_theory",
    },
    {
        "concept": "geometry",
        "description": "Inscribed angle equals central angle",
        "common_error": "Inscribed angle = arc measure (should be half)",
        "topic": "geometry",
    },
    {
        "concept": "motion",
        "description": "Confusing velocity and speed",
        "common_error": "Velocity is always positive (should be signed)",
        "topic": "physics",
    },
    {
        "concept": "acceleration",
        "description": "Zero velocity means zero acceleration",
        "common_error": "At peak of projectile, a = 0 (actually a = -g)",
        "topic": "physics",
    },
    {
        "concept": "series",
        "description": "Geometric series convergence",
        "common_error": "Summing geometric series with |r| ≥ 1",
        "topic": "analysis",
    },
]


class MisconceptionSeeder:
    """Seeds Misconception nodes in Neo4j."""
    
    def __init__(self):
        self.neo4j = Neo4jClient()
    
    def create_misconception(self, misconception: Dict[str, str]) -> bool:
        """Create a Misconception node and link to Concept.
        
        Args:
            misconception: Misconception dictionary.
            
        Returns:
            True if created successfully.
        """
        query = """
        // Find or create the concept
        MERGE (c:Concept {normalized_name: toLower($concept)})
        ON CREATE SET 
            c.name = $concept,
            c.source_ids = ['misconception_seed'],
            c.topic_tags = [$topic]
        
        // Create the misconception
        MERGE (m:Misconception {description: $description})
        ON CREATE SET
            m.common_error = $common_error,
            m.topic = $topic,
            m.created_at = datetime()
        
        // Link them
        MERGE (c)-[:HAS_MISCONCEPTION]->(m)
        
        RETURN c.name as concept, m.description as misconception
        """
        
        try:
            with self.neo4j.session() as session:
                result = session.run(query, misconception)
                record = result.single()
                if record:
                    logger.info(f"Created: {record['concept']} -> {record['misconception'][:50]}...")
                    return True
        except Exception as e:
            logger.error(f"Failed to create misconception: {e}")
        
        return False
    
    def seed_all(self, misconceptions: List[Dict[str, str]] = None) -> Dict[str, int]:
        """Seed all misconceptions.
        
        Args:
            misconceptions: List of misconception dicts. Uses MISCONCEPTIONS if None.
            
        Returns:
            Statistics dictionary.
        """
        if misconceptions is None:
            misconceptions = MISCONCEPTIONS
        
        stats = {"total": 0, "created": 0, "failed": 0}
        
        logger.info(f"Seeding {len(misconceptions)} misconceptions...")
        
        for misc in misconceptions:
            stats["total"] += 1
            if self.create_misconception(misc):
                stats["created"] += 1
            else:
                stats["failed"] += 1
        
        return stats
    
    def get_statistics(self) -> Dict[str, int]:
        """Get misconception statistics from Neo4j.
        
        Returns:
            Statistics dictionary.
        """
        stats = {}
        
        with self.neo4j.session() as session:
            # Count misconceptions
            result = session.run("MATCH (m:Misconception) RETURN count(m) as count")
            stats["misconception_nodes"] = result.single()["count"]
            
            # Count edges
            result = session.run("MATCH ()-[r:HAS_MISCONCEPTION]->() RETURN count(r) as count")
            stats["has_misconception_edges"] = result.single()["count"]
            
            # Count concepts with misconceptions
            result = session.run("""
                MATCH (c:Concept)-[:HAS_MISCONCEPTION]->()
                RETURN count(DISTINCT c) as count
            """)
            stats["concepts_with_misconceptions"] = result.single()["count"]
            
            # By topic
            result = session.run("""
                MATCH (m:Misconception)
                RETURN m.topic as topic, count(m) as count
                ORDER BY count DESC
            """)
            stats["by_topic"] = {r["topic"]: r["count"] for r in result}
        
        return stats
    
    def close(self):
        """Close connections."""
        self.neo4j.close()


def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    
    seeder = MisconceptionSeeder()
    
    try:
        # Seed misconceptions
        stats = seeder.seed_all()
        
        print("\n" + "=" * 60)
        print("MISCONCEPTION SEEDING COMPLETE")
        print("=" * 60)
        print(f"Total: {stats['total']}")
        print(f"Created: {stats['created']}")
        print(f"Failed: {stats['failed']}")
        
        # Get final statistics
        final_stats = seeder.get_statistics()
        
        print(f"\n=== Neo4j Statistics ===")
        print(f"Misconception nodes: {final_stats['misconception_nodes']}")
        print(f"HAS_MISCONCEPTION edges: {final_stats['has_misconception_edges']}")
        print(f"Concepts with misconceptions: {final_stats['concepts_with_misconceptions']}")
        
        print(f"\n=== By Topic ===")
        for topic, count in final_stats.get('by_topic', {}).items():
            print(f"  {topic}: {count}")
    
    finally:
        seeder.close()


if __name__ == "__main__":
    main()
