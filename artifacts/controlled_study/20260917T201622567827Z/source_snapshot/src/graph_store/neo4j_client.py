"""
Neo4j client for MathemaTest knowledge graph.

Manages connection, schema initialization, and CRUD operations
for mathematical concept nodes and their relationships.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import ServiceUnavailable, AuthError

from src.config.settings import get_settings, Settings


logger = logging.getLogger(__name__)


class Neo4jClient:
    """Neo4j database client for knowledge graph operations.
    
    Handles connection management, schema initialization, and
    provides methods for node and relationship CRUD operations.
    
    Example:
        >>> client = Neo4jClient()
        >>> client.initialize_schema()
        >>> client.create_concept("Work-Energy Theorem", {...})
    """
    
    # Node type labels
    NODE_TYPES = ["Concept", "Formula", "Theorem", "Definition", "Figure", "Misconception"]
    
    # Relationship types with their properties
    EDGE_TYPES = {
        "PREREQUISITE_OF": ["weight", "source_id"],
        "DERIVED_FROM": ["proof_method", "source_id"],
        "GROUNDED_IN": ["application", "source_id"],
        "CONTRADICTS": ["reason", "source_id"],
        "HAS_MISCONCEPTION": ["frequency", "source_id"],
    }
    
    def __init__(self, settings: Optional[Settings] = None):
        """Initialize Neo4j client.
        
        Args:
            settings: Settings instance. Uses default if None.
        """
        self.settings = settings or get_settings()
        self._driver: Optional[Driver] = None
    
    @property
    def driver(self) -> Driver:
        """Get or create Neo4j driver connection."""
        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    self.settings.neo4j_uri,
                    auth=(self.settings.neo4j_user, self.settings.neo4j_password),
                )
                # Verify connectivity
                self._driver.verify_connectivity()
                logger.info(f"Connected to Neo4j at {self.settings.neo4j_uri}")
            except AuthError as e:
                logger.error(f"Neo4j authentication failed: {e}")
                raise
            except ServiceUnavailable as e:
                logger.error(f"Neo4j service unavailable: {e}")
                raise
        return self._driver
    
    def close(self):
        """Close the Neo4j driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")
    
    @contextmanager
    def session(self):
        """Context manager for Neo4j sessions.
        
        Yields:
            Neo4j session for executing queries.
        """
        session = self.driver.session(database=self.settings.neo4j_database)
        try:
            yield session
        finally:
            session.close()
    
    def initialize_schema(self) -> Dict[str, Any]:
        """Initialize Neo4j schema with constraints and indexes.
        
        Creates:
        - Unique constraints on node IDs
        - Indexes on commonly queried properties
        
        Returns:
            Dict with schema creation results.
        """
        results = {"constraints": [], "indexes": []}
        
        with self.session() as session:
            # Create unique constraints for each node type
            for node_type in self.NODE_TYPES:
                constraint_name = f"unique_{node_type.lower()}_id"
                try:
                    session.run(f"""
                        CREATE CONSTRAINT {constraint_name} IF NOT EXISTS
                        FOR (n:{node_type})
                        REQUIRE n.id IS UNIQUE
                    """)
                    results["constraints"].append(constraint_name)
                    logger.info(f"Created constraint: {constraint_name}")
                except Exception as e:
                    logger.warning(f"Constraint {constraint_name} may already exist: {e}")
            
            # Create indexes for common queries
            indexes = [
                ("Concept", "name"),
                ("Formula", "name"),
                ("Formula", "source_id"),
                ("Theorem", "name"),
                ("Misconception", "related_concept"),
            ]
            
            for node_type, prop in indexes:
                index_name = f"idx_{node_type.lower()}_{prop}"
                try:
                    session.run(f"""
                        CREATE INDEX {index_name} IF NOT EXISTS
                        FOR (n:{node_type})
                        ON (n.{prop})
                    """)
                    results["indexes"].append(index_name)
                    logger.info(f"Created index: {index_name}")
                except Exception as e:
                    logger.warning(f"Index {index_name} may already exist: {e}")
        
        return results
    
    def create_node(
        self,
        node_type: str,
        node_id: str,
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a node in the graph.
        
        Args:
            node_type: Type of node (Concept, Formula, etc.)
            node_id: Unique identifier for the node.
            properties: Node properties including source_id, page_number, etc.
            
        Returns:
            Created node properties.
            
        Raises:
            ValueError: If node_type is not valid.
        """
        if node_type not in self.NODE_TYPES:
            raise ValueError(f"Invalid node type: {node_type}. Must be one of {self.NODE_TYPES}")
        
        properties["id"] = node_id
        
        with self.session() as session:
            result = session.run(
                f"""
                MERGE (n:{node_type} {{id: $id}})
                SET n += $props
                RETURN n
                """,
                id=node_id,
                props=properties,
            )
            record = result.single()
            return dict(record["n"]) if record else {}
    
    def create_relationship(
        self,
        from_id: str,
        from_type: str,
        to_id: str,
        to_type: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create a relationship between two nodes.
        
        Args:
            from_id: Source node ID.
            from_type: Source node type.
            to_id: Target node ID.
            to_type: Target node type.
            rel_type: Relationship type.
            properties: Relationship properties.
            
        Returns:
            True if relationship was created.
        """
        if rel_type not in self.EDGE_TYPES:
            raise ValueError(f"Invalid relationship type: {rel_type}")
        
        properties = properties or {}
        
        with self.session() as session:
            result = session.run(
                f"""
                MATCH (a:{from_type} {{id: $from_id}})
                MATCH (b:{to_type} {{id: $to_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r += $props
                RETURN r
                """,
                from_id=from_id,
                to_id=to_id,
                props=properties,
            )
            return result.single() is not None
    
    def get_node(self, node_id: str, node_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a node by ID.
        
        Args:
            node_id: Node ID to find.
            node_type: Optional node type filter.
            
        Returns:
            Node properties or None if not found.
        """
        type_filter = f":{node_type}" if node_type else ""
        
        with self.session() as session:
            result = session.run(
                f"MATCH (n{type_filter} {{id: $id}}) RETURN n",
                id=node_id,
            )
            record = result.single()
            return dict(record["n"]) if record else None
    
    def get_prerequisites(
        self,
        concept_id: str,
        depth: int = 2,
        max_chapter: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get prerequisite concepts for a given concept.
        
        Args:
            concept_id: ID of the concept to find prerequisites for.
            depth: Maximum depth of prerequisite chain.
            max_chapter: If provided, only return prerequisites from chapters < max_chapter.
                        This is the "lobotomy" filter for preventing data leakage.
            
        Returns:
            List of prerequisite nodes with their relationships.
        """
        # Build query with optional chapter filter
        if max_chapter is not None:
            query = """
                MATCH path = (c {id: $id})-[:PREREQUISITE_OF*1..]->(prereq)
                WHERE length(path) <= $depth
                  AND prereq.chapter <= $max_chapter
                RETURN prereq, length(path) as distance
                ORDER BY distance
            """
            params = {"id": concept_id, "depth": depth, "max_chapter": max_chapter}
        else:
            query = """
                MATCH path = (c {id: $id})-[:PREREQUISITE_OF*1..]->(prereq)
                WHERE length(path) <= $depth
                RETURN prereq, length(path) as distance
                ORDER BY distance
            """
            params = {"id": concept_id, "depth": depth}
        
        with self.session() as session:
            result = session.run(query, **params)
            return [
                {"node": dict(r["prereq"]), "distance": r["distance"]}
                for r in result
            ]
    
    def get_misconceptions(self, concept_id: str) -> List[Dict[str, Any]]:
        """Get misconceptions related to a concept.
        
        Args:
            concept_id: ID of the concept.
            
        Returns:
            List of misconception nodes.
        """
        with self.session() as session:
            result = session.run(
                """
                MATCH (c {id: $id})-[:HAS_MISCONCEPTION]->(m:Misconception)
                RETURN m
                """,
                id=concept_id,
            )
            return [dict(r["m"]) for r in result]
    
    def search_by_latex(
        self,
        latex_pattern: str,
        max_chapter: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Search for nodes containing specific LaTeX.
        
        Args:
            latex_pattern: LaTeX string to search for.
            max_chapter: If provided, only return nodes from chapters < max_chapter.
                        This is the "lobotomy" filter for preventing data leakage.
            
        Returns:
            List of matching nodes.
        """
        # Build query with optional chapter filter
        if max_chapter is not None:
            query = """
                MATCH (n)
                WHERE (n.raw_latex CONTAINS $pattern
                   OR n.normalized_latex CONTAINS $pattern)
                  AND n.chapter <= $max_chapter
                RETURN n, labels(n) as types
            """
            params = {"pattern": latex_pattern, "max_chapter": max_chapter}
        else:
            query = """
                MATCH (n)
                WHERE n.raw_latex CONTAINS $pattern
                   OR n.normalized_latex CONTAINS $pattern
                RETURN n, labels(n) as types
            """
            params = {"pattern": latex_pattern}
        
        with self.session() as session:
            result = session.run(query, **params)
            return [
                {"node": dict(r["n"]), "types": r["types"]}
                for r in result
            ]
    
    def search_concepts(
        self,
        query: str,
        max_chapter: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search for concepts by name or description.
        
        Args:
            query: Search query text.
            max_chapter: If provided, only return nodes from chapters < max_chapter.
                        This is the "lobotomy" filter for preventing data leakage.
            limit: Maximum number of results.
            
        Returns:
            List of matching concept nodes.
        """
        query_lower = query.lower()
        
        # Build query with optional chapter filter
        # Note: Using $search_term to avoid conflict with session.run() kwargs
        if max_chapter is not None:
            cypher = """
                MATCH (n)
                WHERE (toLower(n.name) CONTAINS $search_term
                   OR toLower(n.description) CONTAINS $search_term
                   OR toLower(n.statement) CONTAINS $search_term)
                  AND n.chapter <= $max_chapter
                RETURN n, labels(n) as types
                LIMIT $limit
            """
            params = {"search_term": query_lower, "max_chapter": max_chapter, "limit": limit}
        else:
            cypher = """
                MATCH (n)
                WHERE toLower(n.name) CONTAINS $search_term
                   OR toLower(n.description) CONTAINS $search_term
                   OR toLower(n.statement) CONTAINS $search_term
                RETURN n, labels(n) as types
                LIMIT $limit
            """
            params = {"search_term": query_lower, "limit": limit}
        
        with self.session() as session:
            result = session.run(cypher, **params)
            return [
                {"node": dict(r["n"]), "types": r["types"]}
                for r in result
            ]
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """Get statistics about the knowledge graph.
        
        Returns:
            Dict with node counts, relationship counts, etc.
        """
        stats = {}
        
        with self.session() as session:
            # Count nodes by type
            for node_type in self.NODE_TYPES:
                result = session.run(f"MATCH (n:{node_type}) RETURN count(n) as count")
                stats[f"{node_type.lower()}_count"] = result.single()["count"]
            
            # Count relationships by type
            for rel_type in self.EDGE_TYPES:
                result = session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as count")
                stats[f"{rel_type.lower()}_count"] = result.single()["count"]
            
            # Total counts
            result = session.run("MATCH (n) RETURN count(n) as count")
            stats["total_nodes"] = result.single()["count"]
            
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
            stats["total_relationships"] = result.single()["count"]
        
        return stats
    
    def clear_graph(self, confirm: bool = False) -> int:
        """Clear all nodes and relationships from the graph.
        
        Args:
            confirm: Must be True to actually clear.
            
        Returns:
            Number of nodes deleted.
        """
        if not confirm:
            raise ValueError("Must pass confirm=True to clear graph")
        
        with self.session() as session:
            result = session.run("MATCH (n) DETACH DELETE n RETURN count(n) as count")
            count = result.single()["count"]
            logger.warning(f"Cleared {count} nodes from graph")
            return count


class MockNeo4jClient:
    """Mock Neo4j client for testing without database connection."""
    
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.relationships: List[Dict[str, Any]] = []
    
    def initialize_schema(self) -> Dict[str, Any]:
        return {"constraints": [], "indexes": []}
    
    def create_node(
        self,
        node_type: str,
        node_id: str,
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        properties["id"] = node_id
        properties["_type"] = node_type
        self.nodes[node_id] = properties
        return properties
    
    def create_relationship(
        self,
        from_id: str,
        from_type: str,
        to_id: str,
        to_type: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        self.relationships.append({
            "from_id": from_id,
            "to_id": to_id,
            "rel_type": rel_type,
            "properties": properties or {},
        })
        return True
    
    def get_node(self, node_id: str, node_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return self.nodes.get(node_id)
    
    def get_graph_stats(self) -> Dict[str, Any]:
        return {
            "total_nodes": len(self.nodes),
            "total_relationships": len(self.relationships),
        }
    
    def close(self):
        pass
