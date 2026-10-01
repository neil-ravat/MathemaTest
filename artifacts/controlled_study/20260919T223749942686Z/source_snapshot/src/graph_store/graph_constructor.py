"""
Graph Constructor Agent for MathemaTest.

Uses GPT-4o-mini to extract mathematical entities and relationships
from Phase 1 ingestion output, building a knowledge graph in Neo4j.
"""

from __future__ import annotations

import json
import logging
import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from openai import OpenAI

from src.config.settings import get_settings, Settings, BudgetTracker
from src.graph_store.neo4j_client import Neo4jClient, MockNeo4jClient


logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ExtractedEntity:
    """An entity extracted from mathematical content."""
    entity_type: str  # Concept, Formula, Theorem, Definition
    name: str
    description: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedRelationship:
    """A relationship extracted between entities."""
    from_entity: str
    to_entity: str
    relationship_type: str  # PREREQUISITE_OF, DERIVED_FROM, etc.
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedMisconception:
    """A common student misconception."""
    description: str
    related_concept: str
    common_error: str
    difficulty_level: str = "medium"


@dataclass
class ExtractionResult:
    """Complete extraction result from a content block."""
    entities: List[ExtractedEntity]
    relationships: List[ExtractedRelationship]
    misconceptions: List[ExtractedMisconception]
    raw_response: str
    tokens_used: Dict[str, int]


# =============================================================================
# PROMPTS
# =============================================================================

ENTITY_EXTRACTION_SYSTEM_PROMPT = """You are a mathematical knowledge extraction expert. Given mathematical content (LaTeX formulas, text descriptions), extract structured entities and relationships for a knowledge graph.

OUTPUT FORMAT (JSON):
{
  "entities": [
    {
      "entity_type": "Formula|Concept|Theorem|Definition",
      "name": "Brief descriptive name",
      "description": "One-line description of what this represents"
    }
  ],
  "relationships": [
    {
      "from_entity": "Entity name (subject)",
      "to_entity": "Entity name (object)", 
      "relationship_type": "PREREQUISITE_OF|DERIVED_FROM|GROUNDED_IN",
      "reason": "Why this relationship exists"
    }
  ],
  "misconceptions": [
    {
      "description": "What students commonly get wrong",
      "related_concept": "Which concept this relates to",
      "common_error": "The specific error pattern",
      "difficulty_level": "easy|medium|hard"
    }
  ]
}

ENTITY TYPES:
- Formula: A mathematical equation or expression (e.g., F = ma, ∫F·dx)
- Concept: An abstract mathematical idea (e.g., kinetic energy, derivative)
- Theorem: A proven mathematical statement (e.g., Work-Energy Theorem)
- Definition: A formal definition (e.g., "Work is the integral of force over displacement")

RELATIONSHIP TYPES:
- PREREQUISITE_OF: Entity A must be understood before Entity B
- DERIVED_FROM: Entity A is mathematically derived from Entity B
- GROUNDED_IN: Entity A is an application or instance of Entity B

MISCONCEPTION GUIDELINES:
Generate 2-3 common student misconceptions per formula. Focus on:
- Sign errors in equations
- Unit confusion
- Misapplication of conditions (e.g., using formula outside its valid domain)
- Confusing similar concepts
- Algebraic manipulation errors

Always respond with valid JSON only. No explanations outside the JSON."""


def create_extraction_prompt(content: Dict[str, Any]) -> str:
    """Create the user prompt for entity extraction.
    
    Args:
        content: Content block from stress test output.
        
    Returns:
        Formatted prompt string.
    """
    parts = [
        "Extract entities, relationships, and misconceptions from this mathematical content:\n",
    ]
    
    if content.get("source"):
        parts.append(f"SOURCE: {content['source']}")
    if content.get("description"):
        parts.append(f"DESCRIPTION: {content['description']}")
    if content.get("raw_latex"):
        parts.append(f"LATEX: {content['raw_latex']}")
    if content.get("normalized_latex"):
        parts.append(f"NORMALIZED: {content['normalized_latex']}")
    
    parts.append("\nProvide your extraction as JSON.")
    
    return "\n".join(parts)


# =============================================================================
# GRAPH CONSTRUCTOR AGENT
# =============================================================================

class GraphConstructorAgent:
    """Agent for constructing knowledge graph from mathematical content.
    
    Uses GPT-4o-mini to extract entities and relationships from Phase 1
    ingestion output, then populates Neo4j with the extracted knowledge.
    
    Example:
        >>> agent = GraphConstructorAgent()
        >>> agent.process_stress_test_results("stress_test_output/stress_test_results.json")
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        neo4j_client: Optional[Neo4jClient] = None,
        budget_tracker: Optional[BudgetTracker] = None,
    ):
        """Initialize the graph constructor agent.
        
        Args:
            settings: Configuration settings.
            neo4j_client: Neo4j client instance (creates new if None).
            budget_tracker: Budget tracker for API costs.
        """
        self.settings = settings or get_settings()
        self.neo4j = neo4j_client or Neo4jClient(self.settings)
        self.budget_tracker = budget_tracker or BudgetTracker(self.settings)
        
        # Initialize OpenAI client
        if self.settings.validate_openai_key():
            self.openai = self.settings.create_openai_client()
        else:
            self.openai = None
            logger.warning("OpenAI API key not configured - extraction disabled")
    
    def _generate_node_id(self, entity_type: str, name: str, source_id: str = "") -> str:
        """Generate a unique node ID.
        
        Args:
            entity_type: Type of entity.
            name: Entity name.
            source_id: Source document ID.
            
        Returns:
            Unique hash-based ID.
        """
        key = f"{entity_type}:{name}:{source_id}".lower()
        return hashlib.sha256(key.encode()).hexdigest()[:16]
    
    def extract_from_content(
        self,
        content: Dict[str, Any],
        source_id: str = "",
        page_number: int = 0,
    ) -> Optional[ExtractionResult]:
        """Extract entities and relationships from a content block.
        
        Args:
            content: Content block with latex, description, etc.
            source_id: Source document identifier.
            page_number: Page number in source.
            
        Returns:
            ExtractionResult or None if extraction failed.
        """
        if not self.openai:
            logger.error("OpenAI client not initialized")
            return None
        
        prompt = create_extraction_prompt(content)
        
        try:
            response = self.openai.chat.completions.create(
                model=self.settings.gpt4o_mini_model,
                messages=[
                    {"role": "system", "content": ENTITY_EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,  # Lower temperature for more consistent extraction
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            
            # Track costs
            usage = response.usage
            self.budget_tracker.record_call(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                model=self.settings.gpt4o_mini_model,
                purpose=f"Entity extraction: {content.get('name', 'unknown')}",
            )
            
            # Parse response
            raw_response = response.choices[0].message.content
            parsed = json.loads(raw_response)
            
            # Convert to dataclasses
            entities = [
                ExtractedEntity(
                    entity_type=e.get("entity_type", "Concept"),
                    name=e.get("name", "Unknown"),
                    description=e.get("description", ""),
                    properties={
                        "source_id": source_id,
                        "page_number": page_number,
                        "raw_latex": content.get("raw_latex", ""),
                        "normalized_latex": content.get("normalized_latex", ""),
                    },
                )
                for e in parsed.get("entities", [])
            ]
            
            relationships = [
                ExtractedRelationship(
                    from_entity=r.get("from_entity", ""),
                    to_entity=r.get("to_entity", ""),
                    relationship_type=r.get("relationship_type", "GROUNDED_IN"),
                    properties={"reason": r.get("reason", "")},
                )
                for r in parsed.get("relationships", [])
            ]
            
            misconceptions = [
                ExtractedMisconception(
                    description=m.get("description", ""),
                    related_concept=m.get("related_concept", ""),
                    common_error=m.get("common_error", ""),
                    difficulty_level=m.get("difficulty_level", "medium"),
                )
                for m in parsed.get("misconceptions", [])
            ]
            
            return ExtractionResult(
                entities=entities,
                relationships=relationships,
                misconceptions=misconceptions,
                raw_response=raw_response,
                tokens_used={
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                },
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction response: {e}")
            return None
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return None
    
    def persist_extraction(
        self,
        result: ExtractionResult,
        source_id: str = "",
    ) -> Dict[str, int]:
        """Persist extracted entities and relationships to Neo4j.
        
        Args:
            result: Extraction result to persist.
            source_id: Source identifier.
            
        Returns:
            Dict with counts of created nodes and relationships.
        """
        counts = {"nodes": 0, "relationships": 0, "misconceptions": 0}
        
        # Map entity names to IDs for relationship creation
        name_to_id: Dict[str, Tuple[str, str]] = {}  # name -> (id, type)
        
        # Create entity nodes
        for entity in result.entities:
            node_id = self._generate_node_id(entity.entity_type, entity.name, source_id)
            
            self.neo4j.create_node(
                node_type=entity.entity_type,
                node_id=node_id,
                properties={
                    "name": entity.name,
                    "description": entity.description,
                    **entity.properties,
                },
            )
            
            name_to_id[entity.name] = (node_id, entity.entity_type)
            counts["nodes"] += 1
            logger.debug(f"Created {entity.entity_type} node: {entity.name}")
        
        # Create relationships
        for rel in result.relationships:
            from_info = name_to_id.get(rel.from_entity)
            to_info = name_to_id.get(rel.to_entity)
            
            if from_info and to_info:
                self.neo4j.create_relationship(
                    from_id=from_info[0],
                    from_type=from_info[1],
                    to_id=to_info[0],
                    to_type=to_info[1],
                    rel_type=rel.relationship_type,
                    properties=rel.properties,
                )
                counts["relationships"] += 1
                logger.debug(f"Created relationship: {rel.from_entity} -{rel.relationship_type}-> {rel.to_entity}")
        
        # Create misconception nodes
        for misconception in result.misconceptions:
            misc_id = self._generate_node_id(
                "Misconception",
                misconception.description[:50],
                source_id,
            )
            
            self.neo4j.create_node(
                node_type="Misconception",
                node_id=misc_id,
                properties={
                    "description": misconception.description,
                    "related_concept": misconception.related_concept,
                    "common_error": misconception.common_error,
                    "difficulty_level": misconception.difficulty_level,
                    "source_id": source_id,
                },
            )
            
            # Link to related concept if it exists
            concept_info = name_to_id.get(misconception.related_concept)
            if concept_info:
                self.neo4j.create_relationship(
                    from_id=concept_info[0],
                    from_type=concept_info[1],
                    to_id=misc_id,
                    to_type="Misconception",
                    rel_type="HAS_MISCONCEPTION",
                    properties={"source_id": source_id},
                )
            
            counts["misconceptions"] += 1
        
        return counts
    
    def process_stress_test_results(
        self,
        results_path: Optional[Path] = None,
        max_items: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Process stress test results and build knowledge graph.
        
        Args:
            results_path: Path to stress_test_results.json.
            max_items: Maximum number of items to process (for testing).
            
        Returns:
            Processing summary.
        """
        if results_path is None:
            results_path = self.settings.stress_test_output / "stress_test_results.json"
        
        if not results_path.exists():
            raise FileNotFoundError(f"Results file not found: {results_path}")
        
        with open(results_path) as f:
            results = json.load(f)
        
        # Initialize schema
        self.neo4j.initialize_schema()
        
        # Process each case
        cases = results.get("cases", [])
        if max_items:
            cases = cases[:max_items]
        
        summary = {
            "total_processed": 0,
            "total_nodes": 0,
            "total_relationships": 0,
            "total_misconceptions": 0,
            "errors": [],
            "budget_used": 0.0,
        }
        
        for i, case in enumerate(cases):
            logger.info(f"Processing {i+1}/{len(cases)}: {case.get('name', 'unknown')}")
            
            try:
                # Extract entities
                extraction = self.extract_from_content(
                    content=case,
                    source_id=case.get("source", "unknown"),
                    page_number=i + 1,
                )
                
                if extraction:
                    # Persist to graph
                    counts = self.persist_extraction(
                        result=extraction,
                        source_id=case.get("source", "unknown"),
                    )
                    
                    summary["total_nodes"] += counts["nodes"]
                    summary["total_relationships"] += counts["relationships"]
                    summary["total_misconceptions"] += counts["misconceptions"]
                
                summary["total_processed"] += 1
                
            except Exception as e:
                logger.error(f"Error processing case {case.get('name')}: {e}")
                summary["errors"].append(str(e))
        
        summary["budget_used"] = self.budget_tracker.total_spent
        summary["budget_remaining"] = self.budget_tracker.remaining_budget
        
        return summary
    
    def close(self):
        """Close connections."""
        self.neo4j.close()


class MockGraphConstructorAgent:
    """Mock agent for testing without API calls."""
    
    def __init__(self):
        self.neo4j = MockNeo4jClient()
        self.extractions: List[ExtractionResult] = []
    
    def extract_from_content(
        self,
        content: Dict[str, Any],
        source_id: str = "",
        page_number: int = 0,
    ) -> ExtractionResult:
        """Return mock extraction result."""
        name = content.get("name", "Unknown")
        latex = content.get("normalized_latex", "")
        
        entity = ExtractedEntity(
            entity_type="Formula" if latex else "Concept",
            name=name,
            description=content.get("description", ""),
            properties={"source_id": source_id, "raw_latex": latex},
        )
        
        misconception = ExtractedMisconception(
            description=f"Common error when applying {name}",
            related_concept=name,
            common_error="Sign error or unit confusion",
            difficulty_level="medium",
        )
        
        return ExtractionResult(
            entities=[entity],
            relationships=[],
            misconceptions=[misconception],
            raw_response="{}",
            tokens_used={"prompt_tokens": 100, "completion_tokens": 150},
        )
    
    def persist_extraction(self, result: ExtractionResult, source_id: str = "") -> Dict[str, int]:
        """Persist to mock client."""
        for entity in result.entities:
            self.neo4j.create_node(entity.entity_type, entity.name, entity.properties)
        return {"nodes": len(result.entities), "relationships": 0, "misconceptions": len(result.misconceptions)}
    
    def close(self):
        pass
