"""
Embedding service for MathemaTest.

Uses sentence-transformers for local embedding generation
to avoid API costs while maintaining high quality.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Union

import numpy as np


logger = logging.getLogger(__name__)


class EmbeddingService:
    """Local embedding service using sentence-transformers.
    
    Uses all-mpnet-base-v2 by default for high-quality embeddings
    without API costs.
    
    Example:
        >>> embedder = EmbeddingService()
        >>> vectors = embedder.embed(["x^2 + y^2 = r^2"])
    """
    
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-mpnet-base-v2",
        device: Optional[str] = None,
    ):
        """Initialize embedding service.
        
        Args:
            model_name: HuggingFace model name.
            device: Device to run on ('cpu', 'cuda', or None for auto).
        """
        self.model_name = model_name
        self.device = device
        self._model = None
    
    @property
    def model(self):
        """Lazy load the sentence transformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name, device=self.device)
                logger.info(f"Loaded embedding model: {self.model_name}")
            except ImportError:
                logger.error("sentence-transformers not installed")
                raise
        return self._model
    
    def embed(
        self,
        texts: Union[str, List[str]],
        normalize: bool = True,
    ) -> np.ndarray:
        """Generate embeddings for texts.
        
        Args:
            texts: Single text or list of texts to embed.
            normalize: Whether to L2-normalize embeddings.
            
        Returns:
            Numpy array of embeddings (N x D).
        """
        if isinstance(texts, str):
            texts = [texts]
        
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=normalize,
            show_progress_bar=len(texts) > 10,
        )
        
        return embeddings
    
    def embed_latex(
        self,
        latex_strings: List[str],
        include_description: bool = True,
    ) -> np.ndarray:
        """Generate embeddings for LaTeX expressions.
        
        Preprocesses LaTeX to improve embedding quality by
        adding descriptive text context.
        
        Args:
            latex_strings: List of LaTeX expressions.
            include_description: Add natural language context.
            
        Returns:
            Numpy array of embeddings.
        """
        processed = []
        for latex in latex_strings:
            text = latex
            if include_description:
                # Add context for better semantic understanding
                text = f"Mathematical expression: {latex}"
            processed.append(text)
        
        return self.embed(processed)
    
    @property
    def embedding_dimension(self) -> int:
        """Get the dimension of embeddings."""
        return self.model.get_sentence_embedding_dimension()


class MockEmbeddingService:
    """Mock embedding service for testing."""
    
    def __init__(self, dimension: int = 768):
        self.dimension = dimension
    
    def embed(
        self,
        texts: Union[str, List[str]],
        normalize: bool = True,
    ) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        
        # Generate deterministic random embeddings based on text hash
        embeddings = []
        for text in texts:
            np.random.seed(hash(text) % (2**32))
            vec = np.random.randn(self.dimension).astype(np.float32)
            if normalize:
                vec = vec / np.linalg.norm(vec)
            embeddings.append(vec)
        
        return np.array(embeddings)
    
    def embed_latex(self, latex_strings: List[str], **kwargs) -> np.ndarray:
        return self.embed(latex_strings)
    
    @property
    def embedding_dimension(self) -> int:
        return self.dimension
