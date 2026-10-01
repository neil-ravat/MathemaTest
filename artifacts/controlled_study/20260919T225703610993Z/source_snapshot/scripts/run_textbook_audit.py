#!/usr/bin/env python3
"""
Textbook Audit Driver Script.

Automates the full-textbook auditing process:
1. Fetches all theorems/examples from Neo4j
2. Runs AuditorProver on each with chapter-restricted context
3. Saves results with resume capability
4. Generates summary report

Usage:
    python scripts/run_textbook_audit.py                    # Full audit
    python scripts/run_textbook_audit.py --limit 10         # First 10 items
    python scripts/run_textbook_audit.py --chapter 5        # Only Chapter 5
    python scripts/run_textbook_audit.py --limit 5 --dry    # Dry run (no LLM calls)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm

from src.config.settings import get_settings
from src.graph_store.neo4j_client import Neo4jClient
from src.verification.auditor_prover import AuditorProver


# =============================================================================
# CONSTANTS
# =============================================================================

ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts"
REPORT_PATH = ARTIFACTS_DIR / "audit_report.json"


# =============================================================================
# FETCH TARGETS
# =============================================================================

def fetch_audit_targets(
    client: Neo4jClient,
    chapter: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch all audit targets (Theorems, Examples) from Neo4j.
    
    Args:
        client: Neo4j client.
        chapter: If specified, only fetch from this chapter.
        
    Returns:
        List of target dicts with id, label, text, chapter.
    """
    # Build query with optional chapter filter
    if chapter is not None:
        query = """
        MATCH (n)
        WHERE (n:Theorem OR n:Example OR n:Lemma)
          AND n.chapter = $chapter
          AND (n.statement IS NOT NULL OR n.description IS NOT NULL)
        RETURN 
            n.node_id AS id,
            labels(n)[0] AS label,
            COALESCE(n.statement, n.description) AS text,
            n.chapter AS chapter,
            n.name AS name
        ORDER BY n.chapter ASC, n.node_id ASC
        """
        params = {"chapter": chapter}
    else:
        query = """
        MATCH (n)
        WHERE (n:Theorem OR n:Example OR n:Lemma)
          AND n.chapter IS NOT NULL
          AND (n.statement IS NOT NULL OR n.description IS NOT NULL)
        RETURN 
            n.node_id AS id,
            labels(n)[0] AS label,
            COALESCE(n.statement, n.description) AS text,
            n.chapter AS chapter,
            n.name AS name
        ORDER BY n.chapter ASC, n.node_id ASC
        """
        params = {}
    
    targets = []
    with client.session() as session:
        result = session.run(query, **params)
        for record in result:
            targets.append({
                "id": record["id"],
                "label": record["label"],
                "text": record["text"],
                "chapter": record["chapter"],
                "name": record["name"],
            })
    
    return targets


# =============================================================================
# RESUME CAPABILITY
# =============================================================================

def load_existing_results(report_path: Path) -> tuple[List[Dict], Set[str]]:
    """Load existing results and extract processed IDs for resume.
    
    Returns:
        Tuple of (results list, set of processed IDs).
    """
    if not report_path.exists():
        return [], set()
    
    try:
        with open(report_path, "r") as f:
            results = json.load(f)
        processed_ids = {r["id"] for r in results if "id" in r}
        return results, processed_ids
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Warning: Could not load existing results: {e}")
        return [], set()


def save_results(results: List[Dict], report_path: Path):
    """Save results to JSON file (atomic write for safety)."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file first, then rename (atomic)
    temp_path = report_path.with_suffix(".tmp")
    with open(temp_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    temp_path.rename(report_path)


# =============================================================================
# MAIN AUDIT LOOP
# =============================================================================

def run_audit(
    targets: List[Dict],
    prover: AuditorProver,
    report_path: Path,
    dry_run: bool = False,
    rate_limit: float = 0.5,
    skip_lean: bool = False,
) -> List[Dict]:
    """Run the audit loop with resume capability.
    
    Args:
        targets: List of audit targets.
        prover: AuditorProver instance.
        report_path: Path to save results.
        dry_run: If True, skip LLM calls (for testing).
        rate_limit: Seconds to wait between API calls.
        skip_lean: If True, skip Lean compilation for speed.
        
    Returns:
        Full list of results.
    """
    # Load existing results for resume
    results, processed_ids = load_existing_results(report_path)
    
    if processed_ids:
        print(f"Resuming: {len(processed_ids)} already processed, {len(targets) - len(processed_ids)} remaining")
    
    # Track stats
    stats = {"formal": 0, "logic": 0, "gap": 0, "fail": 0, "skipped": 0}
    
    for target in tqdm(targets, desc="Auditing", unit="item"):
        target_id = target["id"]
        
        # Skip already processed
        if target_id in processed_ids:
            stats["skipped"] += 1
            continue
        
        # Dry run mode
        if dry_run:
            result_dict = {
                "id": target_id,
                "chapter": target["chapter"],
                "label": target["label"],
                "name": target.get("name", ""),
                "status": "DRY_RUN",
                "reason": "Dry run - no LLM call made",
                "lean_code": None,
                "timestamp": datetime.now().isoformat(),
            }
        else:
            # Run actual audit
            try:
                audit_result = prover.audit_theorem(
                    theorem_text=target["text"],
                    chapter=target["chapter"],
                    skip_lean=skip_lean,
                )
                
                result_dict = {
                    "id": target_id,
                    "chapter": target["chapter"],
                    "label": target["label"],
                    "name": target.get("name", ""),
                    "status": audit_result.status,
                    "reason": audit_result.reason,
                    "llm_confidence": audit_result.llm_confidence,
                    "lean_code": audit_result.lean_code,
                    "lean_error": audit_result.lean_error,
                    "missing_prerequisites": audit_result.missing_prerequisites,
                    "context_count": audit_result.context_count,
                    "timestamp": datetime.now().isoformat(),
                }
                
                # Track stats
                if audit_result.status == "VERIFIED_FORMAL":
                    stats["formal"] += 1
                elif audit_result.status in ["VERIFIED_LOGIC", "PASS_INFORMAL"]:
                    stats["logic"] += 1
                elif audit_result.status == "FAIL_GAP":
                    stats["gap"] += 1
                else:
                    stats["fail"] += 1
                    
            except Exception as e:
                result_dict = {
                    "id": target_id,
                    "chapter": target["chapter"],
                    "label": target["label"],
                    "name": target.get("name", ""),
                    "status": "ERROR",
                    "reason": f"Exception: {str(e)}",
                    "lean_code": None,
                    "timestamp": datetime.now().isoformat(),
                }
                stats["fail"] += 1
        
        # Append and save immediately
        results.append(result_dict)
        save_results(results, report_path)
        
        # Rate limiting
        if not dry_run:
            time.sleep(rate_limit)
    
    # Print running stats
    print(f"\n🏆 Formal: {stats['formal']} | ✅ Logic: {stats['logic']} | ⚠️ Gap: {stats['gap']} | ❌ Fail: {stats['fail']}")
    
    return results


# =============================================================================
# SUMMARY GENERATOR
# =============================================================================

def generate_summary(report_path: Path) -> str:
    """Generate a Markdown summary of audit results.
    
    Args:
        report_path: Path to the JSON report.
        
    Returns:
        Markdown summary string.
    """
    if not report_path.exists():
        return "No audit report found."
    
    with open(report_path, "r") as f:
        results = json.load(f)
    
    if not results:
        return "No results in audit report."
    
    # Count statuses
    total = len(results)
    formal = sum(1 for r in results if r.get("status") == "VERIFIED_FORMAL")
    logic = sum(1 for r in results if r.get("status") in ["VERIFIED_LOGIC", "PASS_INFORMAL"])
    gap = sum(1 for r in results if r.get("status") == "FAIL_GAP")
    fail_lean = sum(1 for r in results if r.get("status") == "FAIL_LEAN")
    errors = sum(1 for r in results if r.get("status") in ["ERROR", "FAIL_LLM"])
    dry_run = sum(1 for r in results if r.get("status") == "DRY_RUN")
    
    pass_count = formal + logic
    pass_rate = (pass_count / total * 100) if total > 0 else 0
    gap_rate = (gap / total * 100) if total > 0 else 0
    
    # Get failed IDs
    failed_ids = [r["id"] for r in results if r.get("status") in ["FAIL_GAP", "FAIL_LEAN", "ERROR"]]
    gap_ids = [r["id"] for r in results if r.get("status") == "FAIL_GAP"]
    
    # Build summary
    lines = [
        "# Textbook Audit Summary",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Report:** `{report_path}`",
        "",
        "## Statistics",
        "",
        f"| Metric | Count | Percentage |",
        f"|--------|-------|------------|",
        f"| Total Processed | {total} | 100% |",
        f"| 🏆 Verified (Formal Lean) | {formal} | {formal/total*100:.1f}% |",
        f"| ✅ Verified (Logic Only) | {logic} | {logic/total*100:.1f}% |",
        f"| ⚠️ Gap Detected | {gap} | {gap_rate:.1f}% |",
        f"| ❌ Lean Fail (Hard) | {fail_lean} | {fail_lean/total*100:.1f}% |",
        f"| 🔴 Errors | {errors} | {errors/total*100:.1f}% |",
    ]
    
    if dry_run > 0:
        lines.append(f"| 🔵 Dry Run | {dry_run} | {dry_run/total*100:.1f}% |")
    
    lines.extend([
        "",
        "## Pass Rate",
        "",
        f"**Overall Pass Rate:** {pass_rate:.1f}% ({pass_count}/{total})",
        "",
        f"**Gap Detection Rate:** {gap_rate:.1f}% ({gap}/{total})",
        "",
    ])
    
    if gap_ids:
        lines.extend([
            "## Items with Gaps",
            "",
        ])
        for gid in gap_ids[:20]:  # Limit to 20
            # Find the item
            item = next((r for r in results if r["id"] == gid), None)
            if item:
                lines.append(f"- **{gid}** (Ch {item.get('chapter')}): {item.get('name', 'N/A')}")
        
        if len(gap_ids) > 20:
            lines.append(f"- ... and {len(gap_ids) - 20} more")
    
    return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Run textbook audit on theorems and examples.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_textbook_audit.py                  # Full audit
  python scripts/run_textbook_audit.py --limit 10      # First 10 items
  python scripts/run_textbook_audit.py --chapter 5     # Only Chapter 5
  python scripts/run_textbook_audit.py --dry           # Dry run (no API calls)
  python scripts/run_textbook_audit.py --summary       # Show summary only
        """
    )
    
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=None,
        help="Maximum number of items to process (default: all)"
    )
    
    parser.add_argument(
        "--chapter", "-c",
        type=int,
        default=None,
        help="Only audit items from this chapter"
    )
    
    parser.add_argument(
        "--dry",
        action="store_true",
        help="Dry run mode - no LLM calls, just shows targets"
    )
    
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Only show summary of existing results"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=str(REPORT_PATH),
        help=f"Output JSON path (default: {REPORT_PATH})"
    )
    
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=0.5,
        help="Seconds between API calls (default: 0.5)"
    )
    
    parser.add_argument(
        "--skip-lean",
        action="store_true",
        help="Skip Lean compilation for speed (~5s/item vs ~90s/item)"
    )
    
    args = parser.parse_args()
    report_path = Path(args.output)
    
    # Summary only mode
    if args.summary:
        summary = generate_summary(report_path)
        print(summary)
        return
    
    print("=" * 60)
    print("TEXTBOOK AUDIT")
    print("=" * 60)
    print(f"Output: {report_path}")
    print(f"Limit: {args.limit or 'All'}")
    print(f"Chapter: {args.chapter or 'All'}")
    print(f"Dry Run: {args.dry}")
    print()
    
    # Initialize clients
    print("[1] Connecting to Neo4j...")
    neo4j_client = Neo4jClient()
    
    # Fetch targets
    print("[2] Fetching audit targets...")
    targets = fetch_audit_targets(neo4j_client, chapter=args.chapter)
    print(f"    Found {len(targets)} targets")
    
    # Apply limit
    if args.limit:
        targets = targets[:args.limit]
        print(f"    Limited to {len(targets)} targets")
    
    if not targets:
        print("No targets found. Exiting.")
        neo4j_client.close()
        return
    
    # Initialize prover (only if not dry run)
    prover = None
    if not args.dry:
        print("[3] Initializing AuditorProver...")
        prover = AuditorProver()
    else:
        print("[3] Dry run mode - skipping prover initialization")
        # Create a mock prover for dry run
        class MockProver:
            def audit_theorem(self, text, chapter):
                from src.verification.auditor_prover import AuditResult
                return AuditResult(
                    theorem_text=text,
                    chapter_tested=chapter,
                    status="DRY_RUN",
                    reason="Dry run",
                )
            def close(self):
                pass
        prover = MockProver()
    
    # Run audit
    print("[4] Running audit...")
    if args.skip_lean:
        print("    [FAST MODE] Skipping Lean compilation")
    results = run_audit(
        targets=targets,
        prover=prover,
        report_path=report_path,
        dry_run=args.dry,
        rate_limit=args.rate_limit,
        skip_lean=args.skip_lean,
    )
    
    # Cleanup
    prover.close()
    neo4j_client.close()
    
    # Generate summary
    print()
    print("=" * 60)
    summary = generate_summary(report_path)
    print(summary)
    
    print()
    print(f"Results saved to: {report_path}")


if __name__ == "__main__":
    main()
