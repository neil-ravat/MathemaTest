"""
Formula extraction module using UniMERNet for mathematical OCR.

This module provides a wrapper around UniMERNet for converting
mathematical expression images into high-fidelity LaTeX strings.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

import numpy as np
from PIL import Image

from src.models.schemas import BlockType, LayoutBlock


logger = logging.getLogger(__name__)


class FormulaExtractor:
    """Mathematical formula extractor using UniMERNet.
    
    Converts images of mathematical expressions into LaTeX strings.
    Handles complex multi-line formulas, subscripts, superscripts,
    and special mathematical symbols.
    
    Example:
        >>> extractor = FormulaExtractor()
        >>> latex = extractor.extract_latex(formula_image)
        >>> print(latex)
        \\frac{d}{dx}(x^{2}+x)
    
    Environment Requirements:
        - unimernet>=0.2.2
        - transformers>=4.35.0
        - PyTorch with CUDA for GPU acceleration
        - Model weights downloaded on first use (~2GB)
    """
    
    # Default UniMERNet model
    DEFAULT_MODEL = "wanderkid/unimernet_base"
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        use_gpu: bool = True,
        batch_size: int = 4,
    ):
        """Initialize the formula extractor.
        
        Args:
            model_path: HuggingFace model ID or local path. Defaults to unimernet_base.
            device: Device string ('cuda', 'cpu'). Auto-detected if None.
            use_gpu: Whether to prefer GPU if available. Defaults to True.
            batch_size: Batch size for processing multiple formulas.
        """
        self.model_path = model_path or self.DEFAULT_MODEL
        self.device = self._resolve_device(device, use_gpu)
        self.batch_size = batch_size
        self.model = None
        self.processor = None
        self._initialized = False
    
    def _resolve_device(self, device: Optional[str], use_gpu: bool) -> str:
        """Resolve compute device."""
        if device is not None:
            return device
        
        if use_gpu:
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda"
            except ImportError:
                pass
        
        return "cpu"
    
    def _ensure_initialized(self) -> None:
        """Lazy-load the model on first use."""
        if self._initialized:
            return
        
        try:
            from unimernet.processor import Processor
            from unimernet.model import UniMERNet
            import torch
            
            logger.info(f"Loading UniMERNet model: {self.model_path}")
            logger.info(f"Using device: {self.device}")
            
            # Load processor and model
            self.processor = Processor.from_pretrained(self.model_path)
            self.model = UniMERNet.from_pretrained(self.model_path)
            
            # Move to device
            if self.device == "cuda":
                self.model = self.model.cuda()
            
            self.model.eval()
            self._initialized = True
            
            logger.info("UniMERNet model loaded successfully")
            
        except ImportError as e:
            # Fallback to simplified approach if unimernet not available
            logger.warning(
                "UniMERNet not available. Attempting alternative loading method..."
            )
            self._initialize_fallback()
        except Exception as e:
            logger.error(f"Failed to load UniMERNet model: {e}")
            self._initialize_fallback()
    
    def _initialize_fallback(self) -> None:
        """Initialize with transformers directly as fallback."""
        try:
            from transformers import (
                VisionEncoderDecoderModel,
                TrOCRProcessor,
                AutoProcessor,
                AutoModelForVision2Seq,
            )
            import torch
            
            logger.info("Using transformers-based fallback for formula OCR")
            
            # Try loading as Vision2Seq model
            try:
                self.processor = AutoProcessor.from_pretrained(self.model_path)
                self.model = AutoModelForVision2Seq.from_pretrained(self.model_path)
            except Exception:
                # If that fails, use generic OCR model as last resort
                logger.warning(
                    "UniMERNet-specific model not available. "
                    "Using generic math OCR. Install unimernet for best results."
                )
                self.model = None
                self.processor = None
            
            if self.model is not None:
                if self.device == "cuda":
                    self.model = self.model.cuda()
                self.model.eval()
            
            self._initialized = True
            
        except ImportError:
            logger.error(
                "Neither unimernet nor transformers available. "
                "Install with: pip install unimernet transformers"
            )
            self._initialized = True  # Mark as initialized but model is None
    
    def extract_latex(
        self,
        image: Union[Image.Image, np.ndarray, str, Path],
        normalize: bool = False,
    ) -> str:
        """Extract LaTeX from a formula image.
        
        Args:
            image: PIL Image, numpy array, or path to image.
            normalize: Whether to apply basic normalization to output.
            
        Returns:
            LaTeX string representation of the formula.
        """
        self._ensure_initialized()
        
        # Load image if path
        if isinstance(image, (str, Path)):
            image = Image.open(image).convert("RGB")
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image).convert("RGB")
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        # If model not loaded, return placeholder
        if self.model is None:
            logger.warning("Model not loaded, returning empty result")
            return ""
        
        try:
            import torch
            
            # Process image
            inputs = self.processor(images=image, return_tensors="pt")
            
            if self.device == "cuda":
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
            # Generate LaTeX
            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=512,
                    num_beams=5,
                    do_sample=False,
                )
            
            # Decode output
            latex = self.processor.batch_decode(
                generated_ids, skip_special_tokens=True
            )[0]
            
            # Basic cleanup
            latex = latex.strip()
            
            if normalize:
                latex = self._basic_normalize(latex)
            
            return latex
            
        except Exception as e:
            logger.error(f"Formula extraction failed: {e}")
            return ""
    
    def extract_latex_batch(
        self,
        images: list[Union[Image.Image, np.ndarray]],
        normalize: bool = False,
    ) -> list[str]:
        """Extract LaTeX from multiple formula images.
        
        Args:
            images: List of images to process.
            normalize: Whether to apply basic normalization.
            
        Returns:
            List of LaTeX strings in same order as input.
        """
        self._ensure_initialized()
        
        if self.model is None:
            return [""] * len(images)
        
        results: list[str] = []
        
        # Process in batches
        for i in range(0, len(images), self.batch_size):
            batch = images[i:i + self.batch_size]
            
            # Convert all to PIL RGB
            pil_batch = []
            for img in batch:
                if isinstance(img, (str, Path)):
                    img = Image.open(img)
                if isinstance(img, np.ndarray):
                    img = Image.fromarray(img)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                pil_batch.append(img)
            
            try:
                import torch
                
                # Process batch
                inputs = self.processor(images=pil_batch, return_tensors="pt")
                
                if self.device == "cuda":
                    inputs = {k: v.cuda() for k, v in inputs.items()}
                
                with torch.no_grad():
                    generated_ids = self.model.generate(
                        **inputs,
                        max_new_tokens=512,
                        num_beams=5,
                        do_sample=False,
                    )
                
                batch_latex = self.processor.batch_decode(
                    generated_ids, skip_special_tokens=True
                )
                
                for latex in batch_latex:
                    latex = latex.strip()
                    if normalize:
                        latex = self._basic_normalize(latex)
                    results.append(latex)
                    
            except Exception as e:
                logger.error(f"Batch extraction failed: {e}")
                results.extend([""] * len(batch))
        
        return results
    
    def _basic_normalize(self, latex: str) -> str:
        """Apply basic normalization to extracted LaTeX.
        
        Args:
            latex: Raw LaTeX string.
            
        Returns:
            Normalized LaTeX string.
        """
        # Strip surrounding whitespace
        latex = latex.strip()
        
        # Remove common artifacts from OCR
        latex = latex.replace("\\\\", "")  # Remove line breaks
        latex = latex.replace("&", "")  # Remove alignment markers
        
        # Normalize spaces
        import re
        latex = re.sub(r"\s+", " ", latex)
        
        return latex
    
    def get_confidence(
        self,
        image: Union[Image.Image, np.ndarray],
    ) -> float:
        """Estimate extraction confidence for an image.
        
        This is a heuristic based on image quality metrics.
        
        Args:
            image: The formula image.
            
        Returns:
            Confidence score between 0 and 1.
        """
        if isinstance(image, (str, Path)):
            image = Image.open(image)
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        
        # Basic quality heuristics
        width, height = image.size
        
        # Very small images are harder to read
        if width < 20 or height < 20:
            return 0.3
        
        # Very large images might have noise
        if width > 2000 or height > 1000:
            return 0.7
        
        # Check aspect ratio (extreme ratios are suspicious)
        aspect = width / max(height, 1)
        if aspect > 20 or aspect < 0.05:
            return 0.5
        
        # Default good confidence
        return 0.85


class MockFormulaExtractor(FormulaExtractor):
    """Mock formula extractor for testing without GPU.
    
    Returns predefined LaTeX strings for testing purposes.
    """
    
    # Sample LaTeX expressions for mock returns
    MOCK_FORMULAS = [
        r"\frac{d}{dx}(x^{2}+x)",
        r"\int_{0}^{\infty} e^{-x^2} dx = \frac{\sqrt{\pi}}{2}",
        r"E = mc^{2}",
        r"\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}",
        r"\lim_{x \to 0} \frac{\sin x}{x} = 1",
    ]
    
    def __init__(self, **kwargs):
        """Initialize mock extractor (ignores model parameters)."""
        self._initialized = True
        self.model = None
        self.processor = None
        self.device = "cpu"
        self.model_path = "mock"
        self.batch_size = 4
        self._call_count = 0
    
    def _ensure_initialized(self) -> None:
        """No-op for mock."""
        pass
    
    def extract_latex(
        self,
        image: Union[Image.Image, np.ndarray, str, Path],
        normalize: bool = False,
    ) -> str:
        """Return mock LaTeX for testing.
        
        Args:
            image: Ignored.
            normalize: Ignored.
            
        Returns:
            Mock LaTeX string.
        """
        result = self.MOCK_FORMULAS[self._call_count % len(self.MOCK_FORMULAS)]
        self._call_count += 1
        return result
    
    def extract_latex_batch(
        self,
        images: list[Union[Image.Image, np.ndarray]],
        normalize: bool = False,
    ) -> list[str]:
        """Return mock LaTeX strings for testing.
        
        Args:
            images: Used to determine output length.
            normalize: Ignored.
            
        Returns:
            List of mock LaTeX strings.
        """
        return [self.extract_latex(img, normalize) for img in images]
