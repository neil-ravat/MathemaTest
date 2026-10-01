"""
Integration tests for the full ingestion pipeline.

Tests the end-to-end flow using mock components.
"""

import pytest
import json
from pathlib import Path

from src.ingestion.ingestion_engine import (
    IngestionEngine,
    MockIngestionEngine,
    create_engine,
)
from src.models.schemas import BlockType, IngestionResult


@pytest.fixture
def mock_engine():
    """Create a mock ingestion engine for testing."""
    return MockIngestionEngine()


@pytest.fixture
def temp_image(tmp_path):
    """Create a temporary test image."""
    from PIL import Image
    img = Image.new("RGB", (800, 1000), color="white")
    img_path = tmp_path / "test_page.png"
    img.save(img_path)
    return img_path


class TestMockEngine:
    """Tests using the mock engine."""
    
    def test_process_image_returns_result(self, mock_engine, temp_image):
        """Processing an image should return IngestionResult."""
        result = mock_engine.process_image(temp_image)
        
        assert isinstance(result, IngestionResult)
        assert result.total_pages == 1
        assert len(result.blocks) > 0
    
    def test_result_has_formula_blocks(self, mock_engine, temp_image):
        """Result should include formula blocks."""
        result = mock_engine.process_image(temp_image)
        
        formula_blocks = [b for b in result.blocks if b.block_type == BlockType.FORMULA]
        assert len(formula_blocks) > 0
    
    def test_formula_blocks_have_latex(self, mock_engine, temp_image):
        """Formula blocks should contain LaTeX content."""
        result = mock_engine.process_image(temp_image)
        
        formula_blocks = [b for b in result.blocks if b.block_type == BlockType.FORMULA]
        for block in formula_blocks:
            assert len(block.raw_content) > 0
            assert "\\" in block.raw_content  # LaTeX commands
    
    def test_blocks_have_source_info(self, mock_engine, temp_image):
        """All blocks should have source tracking info."""
        result = mock_engine.process_image(temp_image)
        
        for block in result.blocks:
            assert block.source_info is not None
            assert block.source_info.page_number == 1
            assert len(block.source_info.document_id) > 0
    
    def test_blocks_have_layout_info(self, mock_engine, temp_image):
        """All blocks should have layout detection info."""
        result = mock_engine.process_image(temp_image)
        
        for block in result.blocks:
            assert block.layout_block is not None
            assert block.layout_block.bbox is not None
            assert block.layout_block.confidence >= 0
            assert block.layout_block.confidence <= 1


class TestStructuredOutput:
    """Tests for structured JSON output format."""
    
    def test_result_serializes_to_json(self, mock_engine, temp_image):
        """IngestionResult should serialize to valid JSON."""
        result = mock_engine.process_image(temp_image)
        
        json_str = result.to_json()
        assert isinstance(json_str, str)
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
    
    def test_json_has_required_fields(self, mock_engine, temp_image):
        """JSON output should have all required fields."""
        result = mock_engine.process_image(temp_image)
        parsed = json.loads(result.to_json())
        
        assert "document_id" in parsed
        assert "document_name" in parsed
        assert "total_pages" in parsed
        assert "blocks" in parsed
        assert "processing_time_seconds" in parsed
    
    def test_block_json_structure(self, mock_engine, temp_image):
        """Block JSON should have correct structure."""
        result = mock_engine.process_image(temp_image)
        parsed = json.loads(result.to_json())
        
        assert len(parsed["blocks"]) > 0
        block = parsed["blocks"][0]
        
        assert "block_type" in block
        assert "raw_content" in block
        assert "symbolic_metadata" in block
        assert "source_info" in block
    
    def test_symbolic_metadata_structure(self, mock_engine, temp_image):
        """Symbolic metadata should have correct structure."""
        result = mock_engine.process_image(temp_image)
        parsed = json.loads(result.to_json())
        
        # Find a formula block
        formula_blocks = [b for b in parsed["blocks"] if b["block_type"] == "formula"]
        assert len(formula_blocks) > 0
        
        metadata = formula_blocks[0]["symbolic_metadata"]
        assert "sympy_parseable" in metadata
        assert "complexity_score" in metadata


class TestNeo4jIntegration:
    """Tests for Neo4j property generation."""
    
    def test_to_neo4j_properties(self, mock_engine, temp_image):
        """Blocks should generate Neo4j-compatible properties."""
        result = mock_engine.process_image(temp_image)
        
        for block in result.blocks:
            props = block.to_neo4j_properties()
            
            assert isinstance(props, dict)
            assert "block_type" in props
            assert "content" in props
            assert "source_document" in props
            assert "page_number" in props
    
    def test_neo4j_properties_types(self, mock_engine, temp_image):
        """Neo4j properties should have correct types."""
        result = mock_engine.process_image(temp_image)
        
        for block in result.blocks:
            props = block.to_neo4j_properties()
            
            assert isinstance(props["block_type"], str)
            assert isinstance(props["content"], str)
            assert isinstance(props["page_number"], int)
            assert isinstance(props["sympy_parseable"], bool)
            assert isinstance(props["complexity_score"], float)


class TestFactoryFunction:
    """Tests for the create_engine factory."""
    
    def test_create_mock_engine(self):
        """Factory should create mock engine when requested."""
        engine = create_engine(use_mock=True)
        assert isinstance(engine, MockIngestionEngine)
    
    def test_create_real_engine(self):
        """Factory should create real engine by default."""
        engine = create_engine(use_mock=False)
        assert isinstance(engine, IngestionEngine)
        assert not isinstance(engine, MockIngestionEngine)


class TestResultAggregation:
    """Tests for result statistics and aggregation."""
    
    def test_formula_count(self, mock_engine, temp_image):
        """Should correctly count formula blocks."""
        result = mock_engine.process_image(temp_image)
        
        manual_count = sum(1 for b in result.blocks if b.block_type == BlockType.FORMULA)
        assert result.formula_count == manual_count
    
    def test_text_count(self, mock_engine, temp_image):
        """Should correctly count text blocks."""
        result = mock_engine.process_image(temp_image)
        
        manual_count = sum(1 for b in result.blocks if b.block_type == BlockType.TEXT)
        assert result.text_count == manual_count
    
    def test_sympy_ready_count(self, mock_engine, temp_image):
        """Should correctly count SymPy-ready blocks."""
        result = mock_engine.process_image(temp_image)
        
        manual_count = sum(
            1 for b in result.blocks if b.symbolic_metadata.sympy_parseable
        )
        assert result.sympy_ready_count == manual_count


class TestErrorHandling:
    """Tests for error handling."""
    
    def test_nonexistent_pdf_raises(self, mock_engine):
        """Processing nonexistent PDF should raise FileNotFoundError."""
        # Mock engine doesn't use real files for PDF, but real engine would
        # This tests the error handling in the base engine
        engine = IngestionEngine()
        
        with pytest.raises(FileNotFoundError):
            engine.process_pdf("/nonexistent/path/to/file.pdf")
    
    def test_errors_captured_in_result(self, mock_engine, temp_image):
        """Processing errors should be captured in result, not raised."""
        result = mock_engine.process_image(temp_image)
        
        # Mock engine shouldn't produce errors
        assert len(result.errors) == 0
