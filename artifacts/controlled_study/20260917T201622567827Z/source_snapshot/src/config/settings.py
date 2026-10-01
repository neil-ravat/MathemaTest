"""
Centralized configuration management for MathemaTest.

Loads settings from environment variables and .env file.
Manages API keys, database connections, and model settings.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables.
    
    All settings can be overridden via environment variables or .env file.
    
    Example .env file:
        OPENAI_API_KEY=sk-...
        NEO4J_URI=bolt://localhost:7687
        NEO4J_USER=neo4j
        NEO4J_PASSWORD=password
    """
    
    # === OpenAI Configuration ===
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for GPT-4o and GPT-4o-mini",
    )
    openai_base_url: Optional[str] = Field(
        default=None, description="OpenAI-compatible endpoint; set to local Ollama for offline inference",
    )
    lean_binary: Optional[str] = None
    lake_binary: Optional[str] = None

    def create_openai_client(self):
        from openai import OpenAI
        return OpenAI(
            api_key=self.openai_api_key,
            base_url=self.openai_base_url,
            timeout=self.openai_timeout,
            max_retries=self.openai_max_retries,
        )
    
    # Model selection - STANDARDIZED TO GPT-4o-mini for cost efficiency
    # All tasks now use gpt-4o-mini to preserve $5 budget
    gpt4o_mini_model: str = Field(
        default="gpt-4o-mini",
        description="Model for ALL tasks (extraction, generation, refinement)",
    )
    gpt4o_model: str = Field(
        default="gpt-4o-mini",  # CHANGED: Now defaults to mini for budget
        description="Previously reserved for complex tasks, now uses mini",
    )
    
    # Default model for all operations
    default_model: str = Field(
        default="gpt-4o-mini",
        description="Default model for all LLM operations",
    )
    
    # Rate limiting
    openai_max_retries: int = Field(default=3, description="Max retries for API calls")
    openai_timeout: int = Field(default=60, description="Request timeout in seconds")
    
    # === Neo4j Configuration ===
    neo4j_uri: str = Field(
        default="bolt://localhost:7687",
        description="Neo4j connection URI",
    )
    neo4j_user: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="password", description="Neo4j password")
    neo4j_database: str = Field(default="neo4j", description="Neo4j database name")
    
    # === ChromaDB Configuration ===
    chroma_persist_directory: str = Field(
        default="./data/chroma_db",
        description="Directory for ChromaDB persistence",
    )
    chroma_collection_name: str = Field(
        default="mathematest_chunks",
        description="Default ChromaDB collection name",
    )
    
    # === Embedding Configuration ===
    embedding_model: str = Field(
        default="sentence-transformers/all-mpnet-base-v2",
        description="Local embedding model (no API cost)",
    )
    cross_encoder_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Cross-encoder for re-ranking",
    )
    
    # === Processing Settings ===
    batch_size: int = Field(default=10, description="Batch size for processing")
    misconceptions_per_formula: int = Field(
        default=3,
        description="Number of misconceptions to generate per formula",
    )
    
    # === Budget Tracking ===
    budget_limit_usd: float = Field(
        default=5.0,
        description="Maximum budget for OpenAI API calls in USD",
    )
    
    # Approximate costs per 1K tokens (as of late 2024)
    gpt4o_mini_input_cost_per_1k: float = 0.00015  # $0.15 per 1M input
    gpt4o_mini_output_cost_per_1k: float = 0.0006   # $0.60 per 1M output
    gpt4o_input_cost_per_1k: float = 0.0025         # $2.50 per 1M input
    gpt4o_output_cost_per_1k: float = 0.01          # $10 per 1M output
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    @property
    def project_root(self) -> Path:
        """Get the project root directory."""
        return Path(__file__).parent.parent.parent
    
    @property
    def data_dir(self) -> Path:
        """Get the data directory."""
        return self.project_root / "data"
    
    @property
    def stress_test_output(self) -> Path:
        """Get the stress test output directory."""
        return self.project_root / "stress_test_output"
    
    def get_chroma_path(self) -> Path:
        """Get the absolute ChromaDB directory path."""
        path = Path(self.chroma_persist_directory)
        if not path.is_absolute():
            path = self.project_root / path
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def validate_openai_key(self) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(self.openai_api_key and self.openai_api_key.startswith("sk-"))
    
    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str = "gpt-4o-mini",
    ) -> float:
        """Estimate cost for an API call.
        
        Args:
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            model: Model name.
            
        Returns:
            Estimated cost in USD.
        """
        if "4o-mini" in model:
            input_cost = (input_tokens / 1000) * self.gpt4o_mini_input_cost_per_1k
            output_cost = (output_tokens / 1000) * self.gpt4o_mini_output_cost_per_1k
        else:
            input_cost = (input_tokens / 1000) * self.gpt4o_input_cost_per_1k
            output_cost = (output_tokens / 1000) * self.gpt4o_output_cost_per_1k
        
        return input_cost + output_cost


class BudgetTracker:
    """Tracks API usage costs to stay within budget."""
    
    def __init__(self, settings: Settings, log_file: str = "logs/api_usage.log"):
        self.settings = settings
        self.total_spent: float = 0.0
        self.calls: list[dict] = []
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(exist_ok=True)
    
    def record_call(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str,
        purpose: str = "",
    ) -> float:
        """Record an API call and its cost.
        
        Args:
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            model: Model used.
            purpose: Description of the call.
            
        Returns:
            Cost of this call.
            
        Raises:
            ValueError: If budget would be exceeded.
        """
        from datetime import datetime
        
        cost = self.settings.estimate_cost(input_tokens, output_tokens, model)
        total_tokens = input_tokens + output_tokens
        
        if self.total_spent + cost > self.settings.budget_limit_usd:
            raise ValueError(
                f"Budget limit of ${self.settings.budget_limit_usd:.2f} would be exceeded. "
                f"Current: ${self.total_spent:.4f}, New call: ${cost:.4f}"
            )
        
        self.total_spent += cost
        self.calls.append({
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": model,
            "cost": cost,
            "purpose": purpose,
        })
        
        # Log to file
        try:
            with open(self.log_file, "a") as f:
                f.write(f"{datetime.now().isoformat()} | {purpose[:30]:30} | "
                       f"model={model} | "
                       f"tokens={total_tokens} | "
                       f"cost=${cost:.6f} | "
                       f"total=${self.total_spent:.6f}\n")
        except Exception:
            pass  # Don't fail on logging errors
        
        return cost
    
    @property
    def remaining_budget(self) -> float:
        """Get remaining budget in USD."""
        return max(0, self.settings.budget_limit_usd - self.total_spent)
    
    def summary(self) -> str:
        """Get a summary of API usage."""
        return (
            f"Budget: ${self.settings.budget_limit_usd:.2f}\n"
            f"Spent: ${self.total_spent:.4f}\n"
            f"Remaining: ${self.remaining_budget:.4f}\n"
            f"Calls: {len(self.calls)}"
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance.
    
    Returns:
        Settings instance loaded from environment.
    """
    return Settings()


def get_budget_tracker() -> BudgetTracker:
    """Get a new budget tracker instance.
    
    Returns:
        BudgetTracker initialized with current settings.
    """
    return BudgetTracker(get_settings())
