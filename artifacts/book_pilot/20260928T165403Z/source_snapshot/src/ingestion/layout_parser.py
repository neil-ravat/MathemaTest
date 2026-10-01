"""
Layout parsing module using DocLayout-YOLO for document segmentation.

This module provides a wrapper around DocLayout-YOLO for detecting
and classifying document regions (text, formula, figure, table).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional, Union

import numpy as np
from PIL import Image

from src.models.schemas import BlockType, BoundingBox, LayoutBlock


logger = logging.getLogger(__name__)


# DocLayout-YOLO class mapping to our BlockType enum
DOCLAYOUT_CLASS_MAP = {
    "title": BlockType.TITLE,
    "text": BlockType.TEXT,
    "abandon": BlockType.UNKNOWN,
    "figure": BlockType.FIGURE,
    "figure_caption": BlockType.CAPTION,
    "table": BlockType.TABLE,
    "table_caption": BlockType.CAPTION,
    "table_footnote": BlockType.TEXT,
    "isolate_formula": BlockType.FORMULA,
    "formula_caption": BlockType.CAPTION,
    "list": BlockType.LIST,
    # Default fallbacks
    "formula": BlockType.FORMULA,
    "equation": BlockType.FORMULA,
}


class LayoutAnalyzer:
    """Document layout analyzer using DocLayout-YOLO.
    
    Detects and classifies document regions for downstream processing.
    Supports both GPU and CPU inference with configurable confidence thresholds.
    
    Example:
        >>> analyzer = LayoutAnalyzer()
        >>> image = Image.open("page.png")
        >>> blocks = analyzer.detect_blocks(image, page_number=1)
        >>> for block in blocks:
        ...     print(f"{block.block_type}: {block.confidence:.2%}")
    
    Environment Requirements:
        - doclayout-yolo>=0.0.2
        - PyTorch with CUDA for GPU acceleration
        - Model weights are downloaded automatically on first use
    """
    
    # Default model for DocLayout-YOLO
    DEFAULT_MODEL = "juliozhao/DocLayout-YOLO-DocStructBench"
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        confidence_threshold: float = 0.25,
        device: Optional[str] = None,
        use_gpu: bool = True,
    ):
        """Initialize the layout analyzer.
        
        Args:
            model_path: Path or HuggingFace model ID. Defaults to DocStructBench model.
            confidence_threshold: Minimum confidence for detection. Defaults to 0.25.
            device: Device string ('cuda', 'cpu', 'cuda:0'). Auto-detected if None.
            use_gpu: Whether to prefer GPU if available. Defaults to True.
        """
        self.model_path = model_path or self.DEFAULT_MODEL
        self.confidence_threshold = confidence_threshold
        self.device = self._resolve_device(device, use_gpu)
        self.model = None
        self._initialized = False
    
    def _resolve_device(self, device: Optional[str], use_gpu: bool) -> str:
        """Resolve the compute device to use.
        
        Args:
            device: Explicit device string or None for auto-detection.
            use_gpu: Whether to prefer GPU.
            
        Returns:
            Device string ('cuda' or 'cpu').
        """
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
            from doclayout_yolo import YOLOv10
            
            logger.info(f"Loading DocLayout-YOLO model: {self.model_path}")
            logger.info(f"Using device: {self.device}")
            
            self.model = YOLOv10(self.model_path)
            self._initialized = True
            
            logger.info("DocLayout-YOLO model loaded successfully")
            
        except ImportError as e:
            logger.error(
                "DocLayout-YOLO not installed. "
                "Install with: pip install doclayout-yolo"
            )
            raise ImportError(
                "doclayout-yolo is required for layout analysis. "
                "Install with: pip install doclayout-yolo"
            ) from e
        except Exception as e:
            logger.error(f"Failed to load DocLayout-YOLO model: {e}")
            raise
    
    def detect_blocks(
        self,
        image: Union[Image.Image, np.ndarray, str, Path],
        page_number: int = 1,
        confidence_threshold: Optional[float] = None,
    ) -> list[LayoutBlock]:
        """Detect layout blocks in a document image.
        
        Args:
            image: PIL Image, numpy array, or path to image file.
            page_number: Page number for block identification (1-indexed).
            confidence_threshold: Override instance threshold for this call.
            
        Returns:
            List of LayoutBlock objects sorted by vertical position.
        """
        self._ensure_initialized()
        
        threshold = confidence_threshold or self.confidence_threshold
        
        # Convert image to format expected by model
        if isinstance(image, (str, Path)):
            image = Image.open(image)
        
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        
        # Run detection
        try:
            results = self.model.predict(
                image,
                conf=threshold,
                device=self.device,
                verbose=False,
            )
        except Exception as e:
            logger.error(f"Layout detection failed: {e}")
            raise
        
        # Parse results into LayoutBlock objects
        blocks: list[LayoutBlock] = []
        
        if results and len(results) > 0:
            result = results[0]  # Single image, single result
            
            if hasattr(result, "boxes") and result.boxes is not None:
                boxes = result.boxes
                
                for i, box in enumerate(boxes):
                    # Extract bounding box
                    xyxy = box.xyxy[0].cpu().numpy()
                    confidence = float(box.conf[0].cpu().numpy())
                    class_id = int(box.cls[0].cpu().numpy())
                    
                    # Map class ID to class name
                    class_name = result.names.get(class_id, "unknown")
                    block_type = DOCLAYOUT_CLASS_MAP.get(
                        class_name.lower(), BlockType.UNKNOWN
                    )
                    
                    # Create block
                    block = LayoutBlock(
                        block_id=f"p{page_number}_b{i}_{uuid.uuid4().hex[:8]}",
                        block_type=block_type,
                        bbox=BoundingBox(
                            x1=float(xyxy[0]),
                            y1=float(xyxy[1]),
                            x2=float(xyxy[2]),
                            y2=float(xyxy[3]),
                        ),
                        confidence=confidence,
                        page_number=page_number,
                    )
                    blocks.append(block)
        
        # Sort by vertical position (top to bottom)
        blocks.sort(key=lambda b: (b.bbox.y1, b.bbox.x1))
        
        logger.info(
            f"Detected {len(blocks)} blocks on page {page_number}: "
            f"{sum(1 for b in blocks if b.block_type == BlockType.FORMULA)} formulas, "
            f"{sum(1 for b in blocks if b.block_type == BlockType.TEXT)} text blocks"
        )
        
        return blocks
    
    def detect_blocks_batch(
        self,
        images: list[Union[Image.Image, np.ndarray]],
        start_page: int = 1,
    ) -> list[list[LayoutBlock]]:
        """Detect layout blocks in multiple images.
        
        Args:
            images: List of images to process.
            start_page: Starting page number (1-indexed).
            
        Returns:
            List of lists of LayoutBlock objects, one per image.
        """
        return [
            self.detect_blocks(img, page_number=start_page + i)
            for i, img in enumerate(images)
        ]
    
    def filter_by_type(
        self,
        blocks: list[LayoutBlock],
        block_types: Union[BlockType, list[BlockType]],
    ) -> list[LayoutBlock]:
        """Filter blocks by type.
        
        Args:
            blocks: List of blocks to filter.
            block_types: Single type or list of types to keep.
            
        Returns:
            Filtered list of blocks.
        """
        if isinstance(block_types, BlockType):
            block_types = [block_types]
        
        return [b for b in blocks if b.block_type in block_types]
    
    def get_formula_blocks(self, blocks: list[LayoutBlock]) -> list[LayoutBlock]:
        """Get only formula blocks from a detection result.
        
        Args:
            blocks: List of detected blocks.
            
        Returns:
            Filtered list containing only formula blocks.
        """
        return self.filter_by_type(blocks, BlockType.FORMULA)
    
    def crop_block(
        self,
        image: Union[Image.Image, np.ndarray],
        block: LayoutBlock,
        padding: int = 5,
    ) -> Image.Image:
        """Crop a region from an image based on block bounding box.
        
        Args:
            image: Source image.
            block: LayoutBlock with bounding box.
            padding: Pixels of padding around the crop.
            
        Returns:
            Cropped PIL Image.
        """
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        
        bbox = block.bbox
        
        # Add padding while staying within image bounds
        x1 = max(0, int(bbox.x1) - padding)
        y1 = max(0, int(bbox.y1) - padding)
        x2 = min(image.width, int(bbox.x2) + padding)
        y2 = min(image.height, int(bbox.y2) + padding)
        
        return image.crop((x1, y1, x2, y2))


class MockLayoutAnalyzer(LayoutAnalyzer):
    """Mock layout analyzer for testing without GPU.
    
    Generates synthetic layout blocks without running the model.
    Useful for unit testing and development.
    """
    
    def __init__(self, **kwargs):
        """Initialize mock analyzer (ignores model parameters)."""
        self.confidence_threshold = kwargs.get("confidence_threshold", 0.25)
        self._initialized = True
        self.model = None
        self.device = "cpu"
        self.model_path = "mock"
    
    def _ensure_initialized(self) -> None:
        """No-op for mock."""
        pass
    
    def detect_blocks(
        self,
        image: Union[Image.Image, np.ndarray, str, Path],
        page_number: int = 1,
        confidence_threshold: Optional[float] = None,
    ) -> list[LayoutBlock]:
        """Generate mock layout blocks for testing.
        
        Args:
            image: Image (used to determine dimensions).
            page_number: Page number for block IDs.
            confidence_threshold: Ignored in mock.
            
        Returns:
            List of synthetic LayoutBlock objects.
        """
        # Get image dimensions
        if isinstance(image, (str, Path)):
            image = Image.open(image)
        if isinstance(image, np.ndarray):
            h, w = image.shape[:2]
        else:
            w, h = image.size
        
        # Generate synthetic blocks
        blocks = [
            LayoutBlock(
                block_id=f"p{page_number}_mock_text_0",
                block_type=BlockType.TEXT,
                bbox=BoundingBox(x1=50, y1=50, x2=w-50, y2=150),
                confidence=0.95,
                page_number=page_number,
            ),
            LayoutBlock(
                block_id=f"p{page_number}_mock_formula_0",
                block_type=BlockType.FORMULA,
                bbox=BoundingBox(x1=100, y1=200, x2=w-100, y2=280),
                confidence=0.92,
                page_number=page_number,
            ),
            LayoutBlock(
                block_id=f"p{page_number}_mock_text_1",
                block_type=BlockType.TEXT,
                bbox=BoundingBox(x1=50, y1=300, x2=w-50, y2=450),
                confidence=0.94,
                page_number=page_number,
            ),
        ]
        
        return blocks
