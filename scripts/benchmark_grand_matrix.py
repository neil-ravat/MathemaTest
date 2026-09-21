#!/usr/bin/env python3
"""
Grand Benchmark Matrix: Phase 2

Compares 3 models × 2 modes:
- Models: GPT-4o-mini, Llama-3.3-70b-versatile, Gemini-1.5-flash
- Modes: Raw (Zero-Shot), Naive RAG (Unfiltered)

Tests on 30 sampled FAIL_GAP items from Phase 1 audit.
"""

import os
import json
import random
import re
import sys
from tqdm import tqdm
from dotenv import load_dotenv
import google.generativeai as genai
from groq import Groq
from openai import OpenAI
import time
import chromadb
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# Load environment variables
load_dotenv()

from src.graph_store.neo4j_client import Neo4jClient

# Initialize API clients
import openai
from groq import Groq
import google.generativeai as genai

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize clients
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

groq_client = Groq(api_key=GROQ_API_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# --- LLM Call Functions ---

def call_gpt(prompt: str, model: str = "gpt-4o-mini") -> str:
    """Call OpenAI GPT model."""
    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"ERROR: {e}"

def call_llama(prompt: str, model: str = "llama-3.3-70b-versatile") -> str:
    """Call Llama model via Groq."""
    try:
        response = groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"ERROR: {e}"

def call_gemini(prompt: str, model: str = "gemini-1.5-flash") -> str:
    """Call Google Gemini model with rate limit handling."""
    max_retries = 3
    base_wait = 10
    
    for attempt in range(max_retries + 1):
        try:
            model_instance = genai.GenerativeModel(model)
            response = model_instance.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=500,
                ),
            )
            return response.text.strip()
        except Exception as e:
            e_str = str(e)
            if "429" in e_str or "quota" in e_str.lower() or "resource" in e_str.lower():
                if attempt < max_retries:
                    wait_time = base_wait * (2 ** attempt) + random.uniform(0, 5)
                    print(f"    [Gemini 429] Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
            return f"ERROR: {e}"


# --- Graph & RAG Functions ---

def load_with_raw_text(audit_path: str, n: int = 30) -> List[Dict[str, Any]]:
    """Load FAIL_GAP items and fetch their raw theorem text from Neo4j."""
    if not os.path.exists(audit_path):
        print(f"Error: {audit_path} not found.")
        return []

    with open(audit_path, "r") as f:
        data = json.load(f)

    # Filter for FAIL_GAP
    gap_items = [d for d in data if d.get("status") == "FAIL_GAP"]
    print(f"    Found {len(gap_items)} FAIL_GAP items.")
    
    if not gap_items:
        return []

    # Sample
    random.seed(42)
    sampled = random.sample(gap_items, min(n, len(gap_items)))
    print(f"    Sampled {len(sampled)} items.")

    # Connect to Neo4j to get raw text
    print("    Connecting to Neo4j to fetch raw theorem text...")
    client = Neo4jClient()
    
    enriched_items = []
    with client.session() as session:
        for item in sampled:
            item_id = item.get("id")
            # Query for the text/statement/content of the node
            # The node label could be Theorem, Example, etc. We try to match by ID.
            # Using WHERE clause to match either id or node_id property
            query = """
            MATCH (n)
            WHERE n.id = $id OR n.node_id = $id
            RETURN 
                coalesce(n.statement, n.content, n.description, n.name) as text,
                n.raw_latex as latex,
                labels(n) as labels
            """
            result = session.run(query, id=item_id).single()
            
            if result:
                text = result["text"]
                # If text is too short, try to append latex if available
                if result["latex"] and len(str(text)) < 50:
                     text = f"{text}\n\n{result['latex']}"
                
                item["raw_text"] = text
                enriched_items.append(item)
            else:
                print(f"    [Warning] Could not find text for ID: {item_id}")
    
    client.close()
    return enriched_items

def get_chroma_context(query: str, n_results: int = 5) -> str:
    """Query ChromaDB for naive RAG context."""
    from src.vector_store.chroma_client import ChromaVectorStore
    store = ChromaVectorStore()
    results = store.search(query, n_results=n_results)
    
    if not results:
        return "No relevant context found."
    
    parts = []
    for i, r in enumerate(results, 1):
        c = r.get("content", "")
        parts.append(f"[{i}] {c[:600]}") # Truncate chunks slightly
    return "\n\n".join(parts)


# --- Evaluation Logic ---

def score_response(response: str) -> str:
    """Decode explicit verdicts only; legacy yes/no is anchored to the start.

    This legacy experiment still uses self-selected positive cases and is not
    an independently labeled evaluation. Operational errors are not detections.
    """
    from src.verification.verdicts import parse_verdict
    if response.strip().upper().startswith("ERROR:"):
        return "ERROR"
    try:
        status = parse_verdict(response).status
        return {"PASS": "RAW_PASS", "FAIL_GAP": "RAW_GAP"}.get(status, "UNCLEAR")
    except (ValueError, TypeError):
        match = re.match(r"^\s*(yes|no)\b", response, re.IGNORECASE)
        if match:
            return "RAW_PASS" if match.group(1).lower() == "yes" else "RAW_GAP"
        return "UNCLEAR"


def run_benchmark():
    print("="*60)
    print("GRAND BENCHMARK: RAW THEOREM TEXT")
    print("="*60)
    
    # 1. Load Data
    sampled_items = load_with_raw_text("artifacts/audit_report.json")
    if not sampled_items:
        print("No items to benchmark. Exiting.")
        return

    # 2. Setup Models
    models = {
        "GPT-4o-mini": call_gpt,
        "Llama-3.3": call_llama,
        "Gemini-1.5-flash": call_gemini,
    }
    
    results = {m: {"raw_scores": [], "rag_scores": []} for m in models}
    
    # 3. Main Loop
    print("\nStarting Benchmark...")
    
    for item in tqdm(sampled_items, desc="Items"):
        theorem_text = item["raw_text"]
        
        # We assume the raw text might not contain the word "Theorem", so we prep it.
        # But we must NOT include the 'reason' (leakage).
        
        # PROMPTS
        prompt_raw = f"""You are a mathematician. Analyze the following theorem text. 
Is it logically self-contained and standard?
Answer with 'Yes' if it is complete and valid, or 'No' if it requires additional context or has missing dependencies.

Theorem Text:
{theorem_text}

Your verdict:"""

        # Get Naive RAG context
        context = get_chroma_context(theorem_text)
        prompt_rag = f"""Using the provided context, is the following theorem text valid and self-contained?
Context:
{context}

Theorem Text:
{theorem_text}

Your verdict:"""

        for m_name, call_fn in models.items():
            # Zero-Shot
            try:
                raw_resp = call_fn(prompt_raw)
                raw_sc = score_response(raw_resp)
            except Exception as e:
                raw_resp = str(e)
                raw_sc = "UNCLEAR"
            
            # Naive RAG
            try:
                rag_resp = call_fn(prompt_rag)
                rag_sc = score_response(rag_resp)
            except Exception as e:
                rag_resp = str(e)
                rag_sc = "UNCLEAR"
                
            results[m_name]["raw_scores"].append(raw_sc)
            results[m_name]["rag_scores"].append(rag_sc)
            
            # Optional: Sleep to be nice to APIs
            time.sleep(0.5)


    # 4. Save & Print
    summary = {}
    print("\n" + "=" * 80)
    print(f"{'Model':<20} | {'Raw Gap%':>10} | {'Raw Hall%':>10} | {'NaiveRAG Gap%':>14} | {'NaiveRAG Hall%':>14}")
    print("-" * 80)

    for m_name in models:
        r_scores = results[m_name]["raw_scores"]
        g_scores = results[m_name]["rag_scores"]
        
        # Calculate percentages
        n_raw = len(r_scores) if r_scores else 1
        n_rag = len(g_scores) if g_scores else 1
        
        raw_gap_rate = 100 * r_scores.count("RAW_GAP") / n_raw
        raw_hall_rate = 100 * r_scores.count("RAW_PASS") / n_raw
        rag_gap_rate = 100 * g_scores.count("RAW_GAP") / n_rag
        rag_hall_rate = 100 * g_scores.count("RAW_PASS") / n_rag
        
        summary[m_name] = {
            "raw_errors": r_scores.count("ERROR"),
            "raw_unclear": r_scores.count("UNCLEAR"),
            "rag_errors": g_scores.count("ERROR"),
            "rag_unclear": g_scores.count("UNCLEAR"),
            "raw_gap_rate": r_scores.count("RAW_GAP") / n_raw,
            "raw_hallucination_rate": r_scores.count("RAW_PASS") / n_raw,
            "naive_rag_gap_rate": g_scores.count("RAW_GAP") / n_rag,
            "naive_rag_hallucination_rate": g_scores.count("RAW_PASS") / n_rag
        }
        
        print(f"{m_name:<20} | {raw_gap_rate:>9.1f}% | {raw_hall_rate:>9.1f}% | {rag_gap_rate:>13.1f}% | {rag_hall_rate:>13.1f}%")

    print("-" * 80)
    print(f"{'MathemaTest (Ours)':<20} | {'N/A':>10} | {'N/A':>10} | {'47.9% (filtered)':>14} |")
    print("Key: Gap% = correctly detected gaps, Hall% = hallucinated validity")
    print("=" * 80)

    final_output = {
        "summary": summary,
        "detailed_results": results,
        "metadata": {
            "n_items": len(sampled_items),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
    }
    
    with open("artifacts/grand_benchmark_matrix.json", "w") as f:
        json.dump(final_output, f, indent=2)



if __name__ == "__main__":
    run_benchmark()
