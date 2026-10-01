"""
Pydantic data models and schemas for MathemaTest ingestion pipeline.

These schemas provide type safety and structured output for the entire
document processing workflow, from layout detection through symbolic normalization.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class BlockType(str, Enum):
    """Type classification for document layout blocks."""
    
    TEXT = "text"
    FORMULA = "formula"
    FIGURE = "figure"
    TABLE = "table"
    TITLE = "title"
    LIST = "list"
    CAPTION = "caption"
    UNKNOWN = "unknown"


class BoundingBox(BaseModel):
    """Bounding box coordinates for a detected block.
    
    Coordinates are in pixels, origin at top-left.
    """
    
    x1: float = Field(..., description="Left x coordinate")
    y1: float = Field(..., description="Top y coordinate")
    x2: float = Field(..., description="Right x coordinate")
    y2: float = Field(..., description="Bottom y coordinate")
    
    @property
    def width(self) -> float:
        """Width of the bounding box."""
        return self.x2 - self.x1
    
    @property
    def height(self) -> float:
        """Height of the bounding box."""
        return self.y2 - self.y1
    
    @property
    def area(self) -> float:
        """Area of the bounding box."""
        return self.width * self.height
    
    @property
    def center(self) -> tuple[float, float]:
        """Center point of the bounding box."""
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)
    
    def to_xyxy(self) -> tuple[float, float, float, float]:
        """Return coordinates as (x1, y1, x2, y2) tuple."""
        return (self.x1, self.y1, self.x2, self.y2)
    
    def to_xywh(self) -> tuple[float, float, float, float]:
        """Return coordinates as (x, y, width, height) tuple."""
        return (self.x1, self.y1, self.width, self.height)


class LayoutBlock(BaseModel):
    """A detected layout block from document analysis.
    
    Represents a region of interest in a document page with its
    classification and confidence score.
    """
    
    block_id: str = Field(..., description="Unique identifier for this block")
    block_type: BlockType = Field(..., description="Classification of the block")
    bbox: BoundingBox = Field(..., description="Bounding box coordinates")
    confidence: float = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Detection confidence score"
    )
    page_number: int = Field(..., ge=1, description="1-indexed page number")
    
    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is within valid range."""
        return round(v, 4)


class ValidationError(BaseModel):
    """A single validation error from OCR output checking."""
    
    error_type: str = Field(..., description="Category of the error")
    message: str = Field(..., description="Human-readable error message")
    position: Optional[int] = Field(
        None, 
        description="Character position where error was detected"
    )
    context: Optional[str] = Field(
        None, 
        description="Surrounding text for context"
    )


class ValidationResult(BaseModel):
    """Result of OCR validation checks.
    
    Contains validation status and detailed error/warning information
    for debugging OCR hallucinations.
    """
    
    is_valid: bool = Field(..., description="Whether the LaTeX passed all validation")
    errors: list[ValidationError] = Field(
        default_factory=list,
        description="Critical errors that likely indicate hallucinations"
    )
    warnings: list[ValidationError] = Field(
        default_factory=list,
        description="Potential issues that may need review"
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence in the validation"
    )
    
    @property
    def error_count(self) -> int:
        """Total number of errors."""
        return len(self.errors)
    
    @property
    def warning_count(self) -> int:
        """Total number of warnings."""
        return len(self.warnings)


class NormalizedLatex(BaseModel):
    """Normalized LaTeX string ready for SymPy processing.
    
    Contains both the raw and normalized forms, along with
    validation and compatibility metadata.
    """
    
    raw: str = Field(..., description="Original extracted LaTeX string")
    normalized: str = Field(..., description="Normalized LaTeX for SymPy")
    sympy_compatible: bool = Field(
        ..., 
        description="Whether the LaTeX can be parsed by SymPy"
    )
    validation: ValidationResult = Field(
        ..., 
        description="Validation results from OCR checking"
    )
    normalization_applied: list[str] = Field(
        default_factory=list,
        description="List of normalization transformations applied"
    )


class SymbolicMetadata(BaseModel):
    """Metadata for symbolic processing of mathematical content.
    
    Contains normalized LaTeX and indicators for downstream
    SymPy/Lean4 processing readiness.
    """
    
    latex_normalized: Optional[NormalizedLatex] = Field(
        None,
        description="Normalized LaTeX data if block is a formula"
    )
    sympy_parseable: bool = Field(
        default=False,
        description="Whether content can be parsed by SymPy"
    )
    complexity_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Estimated complexity of the mathematical expression"
    )
    contains_variables: list[str] = Field(
        default_factory=list,
        description="Detected variable symbols in the expression"
    )
    contains_functions: list[str] = Field(
        default_factory=list,
        description="Detected function names in the expression"
    )


class SourceInfo(BaseModel):
    """Source tracking information for multi-document synthesis.
    
    Enables traceability back to the original document for
    knowledge graph construction and debugging.
    """
    
    document_id: str = Field(..., description="Unique identifier for source document")
    document_name: str = Field(..., description="Original filename")
    page_number: int = Field(..., ge=1, description="1-indexed page number")
    block_index: int = Field(..., ge=0, description="Index of block on the page")
    extraction_timestamp: str = Field(..., description="ISO format timestamp")


class StructuredBlock(BaseModel):
    """Complete structured output for a processed document block.
    
    This is the primary output schema for the ingestion pipeline,
    containing all extracted content and metadata ready for
    knowledge graph population.
    """
    
    block_type: BlockType = Field(..., description="Type classification")
    raw_content: str = Field(..., description="Raw extracted content (text or LaTeX)")
    symbolic_metadata: SymbolicMetadata = Field(
        ..., 
        description="Symbolic processing metadata"
    )
    source_info: SourceInfo = Field(..., description="Source document tracking")
    layout_block: LayoutBlock = Field(..., description="Original layout detection data")
    
    def to_neo4j_properties(self) -> dict:
        """Convert to properties dict for Neo4j node creation.
        
        Returns:
            Dictionary of properties suitable for Cypher query parameters.
        """
        return {
            "block_type": self.block_type.value,
            "content": self.raw_content,
            "sympy_parseable": self.symbolic_metadata.sympy_parseable,
            "source_document": self.source_info.document_id,
            "page_number": self.source_info.page_number,
            "complexity_score": self.symbolic_metadata.complexity_score,
        }


class IngestionResult(BaseModel):
    """Complete result from processing a document through the ingestion pipeline.
    
    Aggregates all structured blocks with document-level metadata
    for downstream processing.
    """
    
    document_id: str = Field(..., description="Unique identifier for the document")
    document_name: str = Field(..., description="Original filename")
    total_pages: int = Field(..., ge=1, description="Total pages processed")
    blocks: list[StructuredBlock] = Field(
        default_factory=list,
        description="All extracted structured blocks"
    )
    processing_time_seconds: float = Field(
        ..., 
        ge=0.0, 
        description="Total processing time"
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Any errors encountered during processing"
    )
    
    @property
    def formula_count(self) -> int:
        """Count of formula blocks extracted."""
        return sum(1 for b in self.blocks if b.block_type == BlockType.FORMULA)
    
    @property
    def text_count(self) -> int:
        """Count of text blocks extracted."""
        return sum(1 for b in self.blocks if b.block_type == BlockType.TEXT)
    
    @property
    def sympy_ready_count(self) -> int:
        """Count of blocks ready for SymPy processing."""
        return sum(1 for b in self.blocks if b.symbolic_metadata.sympy_parseable)
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json(indent=2)
