"""
Query refinement for MathemaTest hybrid retrieval.

Uses GPT-4o for sophisticated query understanding via:
- HyDE (Hypothetical Document Embeddings)
- Step-Back Prompting for complex queries
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from openai import OpenAI

from src.config.settings import get_settings, Settings, BudgetTracker


logger = logging.getLogger(__name__)


@dataclass
class RefinedQuery:
    """Result of query refinement."""
    original_query: str
    refined_query: str
    hypothetical_answer: Optional[str] = None
    step_back_questions: List[str] = None
    query_type: str = "direct"  # direct, conceptual, procedural, multi-hop
    tokens_used: int = 0


HYDE_SYSTEM_PROMPT = """You are an expert mathematics educator. Given a student's question about STEM concepts, generate a hypothetical ideal answer that would appear in a high-quality textbook or reference material.

The hypothetical answer should:
1. Be detailed and technically accurate
2. Include relevant mathematical notation (LaTeX)
3. Reference prerequisite concepts
4. Be suitable for semantic search matching

Respond with only the hypothetical answer, no preamble."""


STEP_BACK_SYSTEM_PROMPT = """You are an expert at breaking down complex mathematical questions into foundational concepts.

Given a student's question:
1. Identify if this is a direct, conceptual, procedural, or multi-hop question
2. Generate 2-3 "step-back" questions that address underlying prerequisites
3. Reformulate the query for better retrieval

Respond in JSON format:
{
  "query_type": "direct|conceptual|procedural|multi-hop",
  "step_back_questions": ["question1", "question2"],
  "refined_query": "improved query for retrieval"
}"""


class QueryRefiner:
    """Refines user queries for improved retrieval.
    
    Uses GPT-4o (reserved for complex tasks) to:
    - Generate hypothetical documents (HyDE)
    - Create step-back questions for multi-hop reasoning
    - Classify query types
    
    Example:
        >>> refiner = QueryRefiner()
        >>> result = refiner.refine("What are the prerequisites for understanding work-energy theorem?")
    """
    
    def __init__(
        self,
        settings: Optional[Settings] = None,
        budget_tracker: Optional[BudgetTracker] = None,
    ):
        """Initialize query refiner.
        
        Args:
            settings: Configuration settings.
            budget_tracker: Budget tracker for GPT-4o usage.
        """
        self.settings = settings or get_settings()
        self.budget_tracker = budget_tracker or BudgetTracker(self.settings)
        
        if self.settings.validate_openai_key():
            self.openai = self.settings.create_openai_client()
        else:
            self.openai = None
            logger.warning("OpenAI API key not configured")
    
    def refine_with_hyde(self, query: str) -> RefinedQuery:
        """Refine query using Hypothetical Document Embeddings.
        
        Generates a hypothetical ideal answer that can be used
        for similarity search instead of the raw query.
        
        Args:
            query: User's original query.
            
        Returns:
            RefinedQuery with hypothetical answer.
        """
        if not self.openai:
            return RefinedQuery(
                original_query=query,
                refined_query=query,
                query_type="direct",
            )
        
        try:
            response = self.openai.chat.completions.create(
                model=self.settings.gpt4o_model,  # Using GPT-4o for quality
                messages=[
                    {"role": "system", "content": HYDE_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                temperature=0.7,
                max_tokens=500,
            )
            
            usage = response.usage
            self.budget_tracker.record_call(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                model=self.settings.gpt4o_model,
                purpose=f"HyDE refinement",
            )
            
            hypothetical = response.choices[0].message.content
            
            return RefinedQuery(
                original_query=query,
                refined_query=hypothetical,  # Use hypothetical for embedding
                hypothetical_answer=hypothetical,
                query_type="hyde",
                tokens_used=usage.total_tokens,
            )
            
        except Exception as e:
            logger.error(f"HyDE refinement failed: {e}")
            return RefinedQuery(original_query=query, refined_query=query)
    
    def refine_with_step_back(self, query: str) -> RefinedQuery:
        """Refine query using Step-Back Prompting.
        
        Breaks complex queries into foundational questions
        for better multi-hop retrieval.
        
        Args:
            query: User's original query.
            
        Returns:
            RefinedQuery with step-back questions.
        """
        if not self.openai:
            return RefinedQuery(
                original_query=query,
                refined_query=query,
                query_type="direct",
            )
        
        try:
            response = self.openai.chat.completions.create(
                model=self.settings.gpt4o_model,
                messages=[
                    {"role": "system", "content": STEP_BACK_SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                temperature=0.5,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            
            usage = response.usage
            self.budget_tracker.record_call(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                model=self.settings.gpt4o_model,
                purpose="Step-back refinement",
            )
            
            import json
            parsed = json.loads(response.choices[0].message.content)
            
            return RefinedQuery(
                original_query=query,
                refined_query=parsed.get("refined_query", query),
                step_back_questions=parsed.get("step_back_questions", []),
                query_type=parsed.get("query_type", "direct"),
                tokens_used=usage.total_tokens,
            )
            
        except Exception as e:
            logger.error(f"Step-back refinement failed: {e}")
            return RefinedQuery(original_query=query, refined_query=query)
    
    def auto_refine(self, query: str) -> RefinedQuery:
        """Automatically choose refinement strategy.
        
        Uses step-back for complex queries, HyDE for conceptual ones,
        and passes through simple queries directly.
        
        Args:
            query: User's query.
            
        Returns:
            Appropriately refined query.
        """
        # Heuristics for complexity
        word_count = len(query.split())
        has_prerequisites = "prerequisite" in query.lower() or "require" in query.lower()
        has_comparison = "difference" in query.lower() or "compare" in query.lower()
        
        if has_prerequisites or word_count > 15:
            return self.refine_with_step_back(query)
        elif has_comparison or "explain" in query.lower():
            return self.refine_with_hyde(query)
        else:
            return RefinedQuery(
                original_query=query,
                refined_query=query,
                query_type="direct",
            )


class MockQueryRefiner:
    """Mock query refiner for testing."""
    
    def refine_with_hyde(self, query: str) -> RefinedQuery:
        return RefinedQuery(
            original_query=query,
            refined_query=f"Hypothetical: {query}",
            hypothetical_answer=f"A detailed answer about {query}",
            query_type="hyde",
        )
    
    def refine_with_step_back(self, query: str) -> RefinedQuery:
        return RefinedQuery(
            original_query=query,
            refined_query=query,
            step_back_questions=[f"What is the foundation of {query}?"],
            query_type="multi-hop",
        )
    
    def auto_refine(self, query: str) -> RefinedQuery:
        return self.refine_with_hyde(query)
