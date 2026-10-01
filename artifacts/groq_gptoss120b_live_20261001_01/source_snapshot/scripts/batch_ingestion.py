#!/usr/bin/env python3
"""
Batch PDF Ingestion Script for MathemaTest Phase A.

Processes large PDFs page-by-page with memory efficiency.
Adds source traceability (source_id, page_number, topic_tag) to all chunks.
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Generator
import json
import hashlib

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF
from openai import OpenAI
from tqdm import tqdm

from src.config.settings import get_settings, BudgetTracker
from src.graph_store.neo4j_client import Neo4jClient
from src.vector_store.chroma_client import ChromaVectorStore


logger = logging.getLogger(__name__)


# =============================================================================
# Topic Detection Prompt
# =============================================================================

TOPIC_EXTRACTION_PROMPT = """Analyze this text from a mathematics/physics document and extract:

1. **topic_tag**: A concise topic label (e.g., "derivatives", "newton_laws", "matrices")
2. **concepts**: List of mathematical/physics concepts mentioned
3. **formulas**: Any mathematical formulas in LaTeX format

TEXT:
{text}

Respond as JSON:
{{
    "topic_tag": "concise_topic_label",
    "concepts": ["concept1", "concept2"],
    "formulas": ["\\\\frac{{a}}{{b}}", "F = ma"]
}}
"""


class BatchIngestionPipeline:
    """Memory-efficient batch ingestion for large PDFs."""
    
    def __init__(
        self,
        neo4j_client: Optional[Neo4jClient] = None,
        chroma_client: Optional[ChromaVectorStore] = None,
        budget_tracker: Optional[BudgetTracker] = None,
        batch_size: int = 10,
    ):
        """Initialize batch ingestion pipeline.
        
        Args:
            neo4j_client: Neo4j client for graph storage.
            chroma_client: ChromaDB client for vector storage.
            budget_tracker: Budget tracker for API costs.
            batch_size: Number of pages to process before committing.
        """
        self.settings = get_settings()
        self.neo4j = neo4j_client or Neo4jClient()
        self.chroma = chroma_client or ChromaVectorStore()
        self.budget = budget_tracker or BudgetTracker(self.settings)
        self.batch_size = batch_size
        self.openai = self.settings.create_openai_client()
    
    def stream_pdf_pages(self, pdf_path: Path) -> Generator[Dict[str, Any], None, None]:
        """Stream PDF pages one at a time to minimize memory.
        
        Args:
            pdf_path: Path to PDF file.
            
        Yields:
            Dict with page_number, text, and metadata.
        """
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        for page_num in range(total_pages):
            page = doc.load_page(page_num)
            text = page.get_text()
            
            yield {
                "page_number": page_num + 1,  # 1-indexed
                "text": text,
                "total_pages": total_pages,
            }
            
            # Clear page from memory
            del page
        
        doc.close()
    
    def extract_topic_and_concepts(self, text: str, source_id: str) -> Dict[str, Any]:
        """Extract topic tag and concepts from page text using GPT-4o-mini.
        
        Args:
            text: Page text content.
            source_id: Source document identifier.
            
        Returns:
            Dict with topic_tag, concepts, formulas.
        """
        # Skip if text is too short
        if len(text.strip()) < 50:
            return {"topic_tag": "empty", "concepts": [], "formulas": []}
        
        # Truncate very long text
        truncated = text[:3000] if len(text) > 3000 else text
        
        try:
            response = self.openai.chat.completions.create(
                model=self.settings.default_model,
                messages=[
                    {"role": "system", "content": "You extract mathematical topics and concepts. Respond only with valid JSON."},
                    {"role": "user", "content": TOPIC_EXTRACTION_PROMPT.format(text=truncated)},
                ],
                max_tokens=500,
                temperature=0.3,
            )
            
            try:
                self.budget.track_usage(
                    response.model,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                    f"topic_extraction_{source_id}",
                )
            except AttributeError:
                pass  # BudgetTracker API may vary
            
            # Parse response
            content = response.choices[0].message.content.strip()
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            return json.loads(content)
            
        except Exception as e:
            logger.warning(f"Topic extraction failed: {e}")
            return {"topic_tag": "unknown", "concepts": [], "formulas": []}
    
    def create_chunk_id(self, source_id: str, page_number: int, chunk_index: int) -> str:
        """Create unique chunk ID."""
        data = f"{source_id}:{page_number}:{chunk_index}"
        return hashlib.md5(data.encode()).hexdigest()[:16]
    
    def process_page(
        self,
        page_data: Dict[str, Any],
        source_id: str,
        source_name: str,
        extract_topics: bool = True,
    ) -> Dict[str, Any]:
        """Process a single page.
        
        Args:
            page_data: Page data from stream_pdf_pages.
            source_id: Source document identifier.
            source_name: Human-readable source name.
            extract_topics: Whether to call LLM for topic extraction.
            
        Returns:
            Processed page data with chunks.
        """
        text = page_data["text"]
        page_number = page_data["page_number"]
        
        # Extract topics if enabled
        if extract_topics and len(text.strip()) > 50:
            extraction = self.extract_topic_and_concepts(text, source_id)
        else:
            extraction = {"topic_tag": "content", "concepts": [], "formulas": []}
        
        # Split text into chunks (simple paragraph-based)
        chunks = self._split_into_chunks(text, max_chunk_size=1000)
        
        processed_chunks = []
        for i, chunk_text in enumerate(chunks):
            if not chunk_text.strip():
                continue
                
            chunk_id = self.create_chunk_id(source_id, page_number, i)
            
            processed_chunks.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "metadata": {
                    "source_id": source_id,
                    "source_name": source_name,
                    "page_number": page_number,
                    "chunk_index": i,
                    "topic_tag": extraction["topic_tag"],
                    "concepts": extraction.get("concepts", []),
                },
            })
        
        return {
            "page_number": page_number,
            "topic_tag": extraction["topic_tag"],
            "concepts": extraction.get("concepts", []),
            "formulas": extraction.get("formulas", []),
            "chunks": processed_chunks,
        }
    
    def _split_into_chunks(self, text: str, max_chunk_size: int = 1000) -> List[str]:
        """Split text into chunks at paragraph boundaries."""
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) < max_chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def ingest_to_chroma(self, chunks: List[Dict[str, Any]]) -> int:
        """Ingest chunks to ChromaDB.
        
        Args:
            chunks: List of processed chunks.
            
        Returns:
            Number of chunks ingested.
        """
        if not chunks:
            return 0
        
        # Convert to ChromaVectorStore document format
        docs = []
        for c in chunks:
            # Convert list metadata to string for ChromaDB compatibility
            metadata = c["metadata"].copy()
            if "concepts" in metadata and isinstance(metadata["concepts"], list):
                metadata["concepts"] = ", ".join(metadata["concepts"])
            
            docs.append({
                "id": c["chunk_id"],
                "content": c["text"],
                **metadata,
            })
        
        self.chroma.add_documents(docs)
        
        return len(chunks)
    
    def ingest_concepts_to_neo4j(
        self,
        concepts: List[str],
        topic_tag: str,
        source_id: str,
        page_number: int,
    ) -> int:
        """Ingest concepts to Neo4j with deduplication.
        
        Args:
            concepts: List of concept names.
            topic_tag: Topic tag for the page.
            source_id: Source document ID.
            page_number: Page number.
            
        Returns:
            Number of concepts ingested.
        """
        if not concepts:
            return 0
        
        count = 0
        for concept in concepts:
            # Normalize concept name for deduplication
            normalized_name = self._normalize_concept_name(concept)
            
            # MERGE to deduplicate
            query = """
            MERGE (c:Concept {normalized_name: $normalized_name})
            ON CREATE SET 
                c.name = $name,
                c.created_at = datetime(),
                c.source_ids = [$source_id],
                c.topic_tags = [$topic_tag]
            ON MATCH SET
                c.source_ids = CASE 
                    WHEN NOT $source_id IN c.source_ids 
                    THEN c.source_ids + $source_id 
                    ELSE c.source_ids 
                END,
                c.topic_tags = CASE 
                    WHEN NOT $topic_tag IN c.topic_tags 
                    THEN c.topic_tags + $topic_tag 
                    ELSE c.topic_tags 
                END
            """
            
            with self.neo4j.session() as session:
                session.run(query, {
                    "normalized_name": normalized_name,
                    "name": concept,
                    "source_id": source_id,
                    "topic_tag": topic_tag,
                })
            count += 1
        
        return count
    
    def _normalize_concept_name(self, name: str) -> str:
        """Normalize concept name for deduplication."""
        # Lowercase, remove extra spaces, basic normalization
        normalized = name.lower().strip()
        normalized = " ".join(normalized.split())
        return normalized
    
    def process_pdf(
        self,
        pdf_path: Path,
        source_id: Optional[str] = None,
        extract_topics: bool = True,
        page_limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Process entire PDF with batch ingestion.
        
        Args:
            pdf_path: Path to PDF file.
            source_id: Source identifier (uses filename if None).
            extract_topics: Whether to extract topics via LLM.
            page_limit: Maximum pages to process (for testing).
            
        Returns:
            Processing summary.
        """
        pdf_path = Path(pdf_path)
        source_id = source_id or pdf_path.stem
        source_name = pdf_path.name
        
        logger.info(f"Starting batch ingestion: {source_name}")
        start_time = time.time()
        
        stats = {
            "source_id": source_id,
            "source_name": source_name,
            "pages_processed": 0,
            "chunks_ingested": 0,
            "concepts_found": 0,
            "formulas_found": 0,
            "errors": [],
        }
        
        # Collect chunks for batch processing
        chunk_buffer = []
        
        for page_data in tqdm(
            self.stream_pdf_pages(pdf_path),
            desc=f"Processing {source_name}",
            total=None,
        ):
            if page_limit and page_data["page_number"] > page_limit:
                break
            
            try:
                processed = self.process_page(
                    page_data,
                    source_id,
                    source_name,
                    extract_topics=extract_topics,
                )
                
                stats["pages_processed"] += 1
                stats["formulas_found"] += len(processed.get("formulas", []))
                
                # Add chunks to buffer
                chunk_buffer.extend(processed["chunks"])
                
                # Ingest concepts to Neo4j
                concepts = processed.get("concepts", [])
                if concepts:
                    self.ingest_concepts_to_neo4j(
                        concepts,
                        processed["topic_tag"],
                        source_id,
                        page_data["page_number"],
                    )
                    stats["concepts_found"] += len(concepts)
                
                # Batch commit to ChromaDB
                if len(chunk_buffer) >= self.batch_size * 5:
                    stats["chunks_ingested"] += self.ingest_to_chroma(chunk_buffer)
                    chunk_buffer = []
                    
            except Exception as e:
                error_msg = f"Page {page_data['page_number']}: {str(e)}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)
        
        # Final flush
        if chunk_buffer:
            stats["chunks_ingested"] += self.ingest_to_chroma(chunk_buffer)
        
        stats["processing_time_seconds"] = round(time.time() - start_time, 2)
        
        logger.info(
            f"Completed {source_name}: {stats['pages_processed']} pages, "
            f"{stats['chunks_ingested']} chunks, {stats['concepts_found']} concepts"
        )
        
        return stats
    
    def process_multiple_pdfs(
        self,
        pdf_paths: List[Path],
        extract_topics: bool = True,
        page_limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Process multiple PDFs.
        
        Args:
            pdf_paths: List of PDF paths.
            extract_topics: Whether to extract topics.
            page_limit: Page limit per PDF.
            
        Returns:
            List of processing summaries.
        """
        results = []
        
        for pdf_path in pdf_paths:
            try:
                result = self.process_pdf(
                    pdf_path,
                    extract_topics=extract_topics,
                    page_limit=page_limit,
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to process {pdf_path}: {e}")
                results.append({
                    "source_name": pdf_path.name,
                    "error": str(e),
                })
        
        return results
    
    def close(self):
        """Close connections."""
        self.neo4j.close()


def main():
    """Main entry point for batch ingestion."""
    parser = argparse.ArgumentParser(description="Batch PDF ingestion for MathemaTest")
    parser.add_argument("--data-dir", type=str, default="data", help="Data directory")
    parser.add_argument("--page-limit", type=int, default=None, help="Page limit per PDF")
    parser.add_argument("--skip-topics", action="store_true", help="Skip LLM topic extraction")
    parser.add_argument("--physics-only", action="store_true", help="Process only Physics PDF")
    parser.add_argument("--mit-only", action="store_true", help="Process only MIT Calculus")
    parser.add_argument("--aime-only", action="store_true", help="Process only AIME PDF")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    
    data_dir = Path(args.data_dir)
    
    # Collect PDFs to process
    pdfs = []
    
    if args.physics_only:
        pdfs.append(data_dir / "University_Physics_Volume_1_-_WEB.pdf")
    elif args.mit_only:
        pdfs.extend(sorted(data_dir.glob("mit_calculus_lec_week*.pdf")))
    elif args.aime_only:
        pdfs.append(data_dir / "ZIML_Download_2024_AIME_I.pdf")
    else:
        # Process all
        pdfs.append(data_dir / "University_Physics_Volume_1_-_WEB.pdf")
        pdfs.extend(sorted(data_dir.glob("mit_calculus_lec_week*.pdf")))
        pdfs.append(data_dir / "ZIML_Download_2024_AIME_I.pdf")
    
    # Filter existing files
    pdfs = [p for p in pdfs if p.exists()]
    
    if not pdfs:
        logger.error("No PDFs found to process!")
        return
    
    logger.info(f"Processing {len(pdfs)} PDFs...")
    
    pipeline = BatchIngestionPipeline()
    
    try:
        results = pipeline.process_multiple_pdfs(
            pdfs,
            extract_topics=not args.skip_topics,
            page_limit=args.page_limit,
        )
        
        # Summary
        total_pages = sum(r.get("pages_processed", 0) for r in results)
        total_chunks = sum(r.get("chunks_ingested", 0) for r in results)
        total_concepts = sum(r.get("concepts_found", 0) for r in results)
        
        print("\n" + "=" * 60)
        print("BATCH INGESTION COMPLETE")
        print("=" * 60)
        print(f"PDFs Processed: {len(results)}")
        print(f"Total Pages: {total_pages}")
        print(f"Total Chunks: {total_chunks}")
        print(f"Total Concepts: {total_concepts}")
        
        # Save results
        output_path = Path("ingestion_results.json")
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {output_path}")
        
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
