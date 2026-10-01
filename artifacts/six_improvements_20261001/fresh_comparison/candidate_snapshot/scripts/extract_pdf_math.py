"""Produce reviewable math crops from selected PDF pages; no LLM or graph writes."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ingestion.ingestion_engine import IngestionEngine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--pages', type=int, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if any(p < 1 for p in args.pages) or len(set(args.pages)) != len(args.pages):
        parser.error('Pages must be distinct positive integers')
    args.output.mkdir(parents=True, exist_ok=False)
    for page in args.pages:
        result = IngestionEngine.process_pdf_math_candidates(args.pdf, page, args.output/f'page_{page}')
        print(f"Page {page}: {len(result['candidates'])} candidates; review required", flush=True)


if __name__ == '__main__':
    main()
