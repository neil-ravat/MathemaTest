"""
Main ingestion engine orchestrating the multimodal document processing pipeline.

This module combines layout detection, formula extraction, and LaTeX normalization
into a unified pipeline that converts PDF documents into structured JSON output
ready for knowledge graph population.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import numpy as np
from PIL import Image

from src.models.schemas import (
    BlockType,
    BoundingBox,
    LayoutBlock,
    NormalizedLatex,
    SourceInfo,
    StructuredBlock,
    SymbolicMetadata,
    IngestionResult,
    ValidationResult,
)
from src.ingestion.layout_parser import LayoutAnalyzer, MockLayoutAnalyzer
from src.ingestion.formula_extractor import FormulaExtractor, MockFormulaExtractor
from src.ingestion.latex_normalizer import LaTeXNormalizer
from src.ingestion.ocr_utils import OCRValidator


logger = logging.getLogger(__name__)


class IngestionEngine:
    """Main document ingestion engine for MathemaTest.
    
    Orchestrates the full processing pipeline:
    1. PDF → Page Images (pdf2image)
    2. Page Images → Layout Blocks (DocLayout-YOLO)
    3. Formula Blocks → LaTeX (UniMERNet)
    4. LaTeX → Normalized LaTeX (LaTeXNormalizer)
    5. All Blocks → Structured JSON Output
    
    Example:
        >>> engine = IngestionEngine()
        >>> result = engine.process_pdf("textbook.pdf")
        >>> print(f"Extracted {result.formula_count} formulas")
        >>> with open("output.json", "w") as f:
        ...     f.write(result.to_json())
    
    Environment Requirements:
        - pdf2image (requires poppler-utils system package)
        - doclayout-yolo for layout detection
        - unimernet for formula OCR
        - CUDA-capable GPU recommended
    """
    
    def __init__(
        self,
        layout_analyzer: Optional[LayoutAnalyzer] = None,
        formula_extractor: Optional[FormulaExtractor] = None,
        latex_normalizer: Optional[LaTeXNormalizer] = None,
        ocr_validator: Optional[OCRValidator] = None,
        use_gpu: bool = True,
        dpi: int = 200,
        confidence_threshold: float = 0.25,
    ):
        """Initialize the ingestion engine.
        
        Args:
            layout_analyzer: Custom layout analyzer. Creates default if None.
            formula_extractor: Custom formula extractor. Creates default if None.
            latex_normalizer: Custom LaTeX normalizer. Creates default if None.
            ocr_validator: Custom OCR validator. Creates default if None.
            use_gpu: Whether to use GPU for processing. Defaults to True.
            dpi: DPI for PDF rendering. Higher = better quality but slower.
            confidence_threshold: Minimum confidence for layout detection.
        """
        self.layout_analyzer = layout_analyzer or LayoutAnalyzer(
            use_gpu=use_gpu,
            confidence_threshold=confidence_threshold,
        )
        self.formula_extractor = formula_extractor or FormulaExtractor(
            use_gpu=use_gpu,
        )
        self.ocr_validator = ocr_validator or OCRValidator(strict_mode=True)
        self.latex_normalizer = latex_normalizer or LaTeXNormalizer(
            validator=self.ocr_validator,
        )
        self.dpi = dpi
        self.use_gpu = use_gpu
    
    def process_pdf(
        self,
        pdf_path: Union[str, Path],
        page_range: Optional[tuple[int, int]] = None,
        document_id: Optional[str] = None,
    ) -> IngestionResult:
        """Process a PDF document through the full ingestion pipeline.
        
        Args:
            pdf_path: Path to the PDF file.
            page_range: Optional (start, end) page range (1-indexed, inclusive).
            document_id: Custom document ID. Auto-generated if None.
            
        Returns:
            IngestionResult with all extracted structured blocks.
        """
        pdf_path = Path(pdf_path)
        start_time = time.time()
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        # Generate document ID
        if document_id is None:
            document_id = self._generate_document_id(pdf_path)
        
        logger.info(f"Processing PDF: {pdf_path.name} (ID: {document_id})")
        
        # Convert PDF to images
        try:
            images = self._pdf_to_images(pdf_path, page_range)
            total_pages = len(images)
            logger.info(f"Converted {total_pages} pages to images at {self.dpi} DPI")
        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return IngestionResult(
                document_id=document_id,
                document_name=pdf_path.name,
                total_pages=0,
                blocks=[],
                processing_time_seconds=time.time() - start_time,
                errors=[f"PDF conversion failed: {str(e)}"],
            )
        
        # Process each page
        all_blocks: list[StructuredBlock] = []
        errors: list[str] = []
        
        start_page = page_range[0] if page_range else 1
        
        for i, image in enumerate(images):
            page_num = start_page + i
            logger.info(f"Processing page {page_num}/{total_pages}")
            
            try:
                page_blocks = self._process_page(
                    image=image,
                    page_number=page_num,
                    document_id=document_id,
                    document_name=pdf_path.name,
                )
                all_blocks.extend(page_blocks)
            except Exception as e:
                error_msg = f"Page {page_num} processing failed: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        processing_time = time.time() - start_time
        
        result = IngestionResult(
            document_id=document_id,
            document_name=pdf_path.name,
            total_pages=total_pages,
            blocks=all_blocks,
            processing_time_seconds=round(processing_time, 2),
            errors=errors,
        )
        
        logger.info(
            f"Processing complete: {len(all_blocks)} blocks extracted "
            f"({result.formula_count} formulas, {result.sympy_ready_count} SymPy-ready) "
            f"in {processing_time:.2f}s"
        )
        
        return result
    
    def process_image(
        self,
        image: Union[Image.Image, np.ndarray, str, Path],
        page_number: int = 1,
        document_id: Optional[str] = None,
        document_name: str = "image",
    ) -> IngestionResult:
        """Process a single image through the ingestion pipeline.
        
        Useful for processing individual pages or document images.
        
        Args:
            image: PIL Image, numpy array, or path to image.
            page_number: Page number for source tracking.
            document_id: Custom document ID.
            document_name: Name for source tracking.
            
        Returns:
            IngestionResult with extracted structured blocks.
        """
        start_time = time.time()
        
        # Load image if path
        if isinstance(image, (str, Path)):
            image_path = Path(image)
            document_name = image_path.name
            image = Image.open(image)
        
        if document_id is None:
            document_id = f"img_{uuid.uuid4().hex[:12]}"
        
        logger.info(f"Processing image: {document_name}")
        
        try:
            blocks = self._process_page(
                image=image,
                page_number=page_number,
                document_id=document_id,
                document_name=document_name,
            )
        except Exception as e:
            logger.error(f"Image processing failed: {e}")
            return IngestionResult(
                document_id=document_id,
                document_name=document_name,
                total_pages=1,
                blocks=[],
                processing_time_seconds=time.time() - start_time,
                errors=[str(e)],
            )
        
        return IngestionResult(
            document_id=document_id,
            document_name=document_name,
            total_pages=1,
            blocks=blocks,
            processing_time_seconds=round(time.time() - start_time, 2),
            errors=[],
        )
    
    def _process_page(
        self,
        image: Union[Image.Image, np.ndarray],
        page_number: int,
        document_id: str,
        document_name: str,
    ) -> list[StructuredBlock]:
        """Process a single page image.
        
        Args:
            image: The page image.
            page_number: Page number (1-indexed).
            document_id: Document identifier.
            document_name: Document filename.
            
        Returns:
            List of StructuredBlock objects from this page.
        """
        # Ensure PIL Image
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
        
        # Step 1: Layout detection
        layout_blocks = self.layout_analyzer.detect_blocks(
            image=image,
            page_number=page_number,
        )
        
        # Step 2: Process each block
        structured_blocks: list[StructuredBlock] = []
        timestamp = datetime.now(timezone.utc).isoformat()
        
        formula_blocks = [b for b in layout_blocks if b.block_type == BlockType.FORMULA]
        
        # Batch extract formulas for efficiency
        if formula_blocks:
            formula_images = [
                self.layout_analyzer.crop_block(image, block)
                for block in formula_blocks
            ]
            latex_strings = self.formula_extractor.extract_latex_batch(
                formula_images, normalize=False
            )
        else:
            latex_strings = []
        
        formula_idx = 0
        
        for block_idx, layout_block in enumerate(layout_blocks):
            # Extract content based on block type
            if layout_block.block_type == BlockType.FORMULA:
                raw_content = latex_strings[formula_idx] if formula_idx < len(latex_strings) else ""
                formula_idx += 1
                
                # Normalize LaTeX for SymPy
                normalized = self.latex_normalizer.normalize(raw_content)
                
                symbolic_metadata = SymbolicMetadata(
                    latex_normalized=normalized,
                    sympy_parseable=normalized.sympy_compatible,
                    complexity_score=self._estimate_complexity(raw_content),
                    contains_variables=self.latex_normalizer.extract_variables(raw_content),
                    contains_functions=self.latex_normalizer.extract_functions(raw_content),
                )
            else:
                # Non-formula blocks (text, figures, tables)
                raw_content = f"[{layout_block.block_type.value} block]"
                symbolic_metadata = SymbolicMetadata(
                    latex_normalized=None,
                    sympy_parseable=False,
                    complexity_score=0.0,
                )
            
            # Create source info for traceability
            source_info = SourceInfo(
                document_id=document_id,
                document_name=document_name,
                page_number=page_number,
                block_index=block_idx,
                extraction_timestamp=timestamp,
            )
            
            # Create structured block
            structured_block = StructuredBlock(
                block_type=layout_block.block_type,
                raw_content=raw_content,
                symbolic_metadata=symbolic_metadata,
                source_info=source_info,
                layout_block=layout_block,
            )
            
            structured_blocks.append(structured_block)
        
        return structured_blocks
    
    def _pdf_to_images(
        self,
        pdf_path: Path,
        page_range: Optional[tuple[int, int]] = None,
    ) -> list[Image.Image]:
        """Convert PDF pages to images.
        
        Args:
            pdf_path: Path to PDF file.
            page_range: Optional (start, end) page range (1-indexed).
            
        Returns:
            List of PIL Images for each page.
        """
        try:
            from pdf2image import convert_from_path
        except ImportError:
            raise ImportError(
                "pdf2image is required for PDF processing. "
                "Install with: pip install pdf2image\n"
                "Also requires poppler-utils: "
                "brew install poppler (macOS) or apt-get install poppler-utils (Linux)"
            )
        
        kwargs = {"dpi": self.dpi}
        
        if page_range:
            kwargs["first_page"] = page_range[0]
            kwargs["last_page"] = page_range[1]
        
        return convert_from_path(str(pdf_path), **kwargs)
    
    def _generate_document_id(self, pdf_path: Path) -> str:
        """Generate a unique document ID based on file content.
        
        Args:
            pdf_path: Path to the document.
            
        Returns:
            Unique document identifier.
        """
        # Use file hash for reproducible IDs
        with open(pdf_path, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()[:12]
        
        return f"doc_{pdf_path.stem}_{file_hash}"
    
    def _estimate_complexity(self, latex_str: str) -> float:
        """Estimate the complexity of a LaTeX expression.
        
        Args:
            latex_str: The LaTeX string.
            
        Returns:
            Complexity score between 0 and 1.
        """
        if not latex_str:
            return 0.0
        
        score = 0.0
        
        # Length-based complexity
        length = len(latex_str)
        if length > 200:
            score += 0.3
        elif length > 100:
            score += 0.2
        elif length > 50:
            score += 0.1
        
        # Feature-based complexity
        complexity_markers = [
            (r"\\frac", 0.1),
            (r"\\int", 0.15),
            (r"\\sum", 0.12),
            (r"\\prod", 0.12),
            (r"\\lim", 0.1),
            (r"_{.*}", 0.05),
            (r"\^{.*}", 0.05),
            (r"\\sqrt", 0.08),
            (r"\\matrix", 0.2),
            (r"\\begin\{cases\}", 0.15),
        ]
        
        import re
        for pattern, weight in complexity_markers:
            if re.search(pattern, latex_str):
                score += weight
        
        # Nesting depth
        max_depth = 0
        current_depth = 0
        for char in latex_str:
            if char == "{":
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            elif char == "}":
                current_depth -= 1
        
        score += min(0.15, max_depth * 0.03)
        
        return min(1.0, score)


class MockIngestionEngine(IngestionEngine):
    """Mock ingestion engine for testing without GPU dependencies.
    
    Uses mock analyzers to simulate pipeline behavior.
    """
    
    def __init__(self, **kwargs):
        """Initialize with mock components."""
        super().__init__(
            layout_analyzer=MockLayoutAnalyzer(),
            formula_extractor=MockFormulaExtractor(),
            **kwargs,
        )
    
    def _pdf_to_images(
        self,
        pdf_path: Path,
        page_range: Optional[tuple[int, int]] = None,
    ) -> list[Image.Image]:
        """Generate mock images for testing.
        
        Args:
            pdf_path: Ignored.
            page_range: Used to determine number of pages.
            
        Returns:
            List of blank test images.
        """
        if page_range:
            num_pages = page_range[1] - page_range[0] + 1
        else:
            num_pages = 3  # Default mock page count
        
        # Generate blank test images
        return [
            Image.new("RGB", (612, 792), color="white")
            for _ in range(num_pages)
        ]


def create_engine(
    use_mock: bool = False,
    use_gpu: bool = True,
    **kwargs,
) -> IngestionEngine:
    """Factory function to create an appropriate ingestion engine.
    
    Args:
        use_mock: If True, create mock engine for testing.
        use_gpu: Whether to use GPU acceleration.
        **kwargs: Additional arguments passed to engine constructor.
        
    Returns:
        Configured IngestionEngine instance.
    """
    if use_mock:
        return MockIngestionEngine(**kwargs)
    return IngestionEngine(use_gpu=use_gpu, **kwargs)
