# Automated Auditing of Mathematical Curricula via Causal Neuro-Symbolic GraphRAG

![License](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)
![Python](https://img.shields.io/badge/Python-3.11-blue.svg)
![Neo4j](https://img.shields.io/badge/Neo4j-5.15-green.svg)
![Status](https://img.shields.io/badge/Status-Research%20Preview-orange.svg)

**MathemaTest** is a research framework for identifying "pedagogical gaps" (missing prerequisites) in mathematical textbooks using a novel **Causal GraphRAG** architecture. By enforcing strict temporal causality on retrieval—preventing the "Future Leakage" common in standard RAG—we enable Large Language Models to simulate the state of a linear learner.

The current implementation combines source-scoped retrieval, Neo4j relationship provenance, PDF/OCR ingestion, exact rational arithmetic, and Lean 4 checks. It also fails closed when evidence is out of scope, a graph relationship lacks an explicit source witness, or an answer contains a supported numerical contradiction.

## Current engineering KPIs

These are reproducible development and integrity results, not production accuracy claims:

| KPI | Result | Scope |
| :--- | :--- | :--- |
| Automated regression suite | **308/308 tests passing** | Provenance, retrieval, ingestion, graph extraction, arithmetic, and verification contracts |
| Locked artifact integrity | **189/189 entries matched** | Frozen NCERT feasibility study |
| Relationship guard replay | **9/9 flawed or only partly supported edges quarantined** | Previously audited NCERT edges |
| Relationship coverage check | **4/4 supported candidates retained** | Inspected Electricity development set after guard tuning |
| Live numerical development check | **3/3 correct numeric values** | Three exposed NCERT Electricity questions; two accepted and one safely rejected for a contradictory assumption |

The live check deliberately distinguishes numerical correctness from solution reliability: MathemaTest rejected an otherwise correct `8 A` response because its stated `100 Ω` assumption contradicted the question's `60 V / 4 A = 15 Ω` operating point. See [the assumption-consistency report](MATHEMATEST_ASSUMPTION_CHECK_RESULTS.md) and [the fresh-study limitations](NCERT_FRESH_STUDY_RESULTS.md).

### Resume-ready description

> Built MathemaTest, a Python/Neo4j/ChromaDB neuro-symbolic GraphRAG pipeline for source-grounded textbook auditing, with PDF/OCR ingestion, temporal retrieval constraints, exact arithmetic, and Lean 4 verification. Added provenance and consistency guards that matched 189/189 frozen artifact checks, quarantined 9/9 previously flagged graph edges, and caught a contradictory physics assumption before answer acceptance.

Our system was evaluated on the *OpenStax Calculus Vol 1* corpus, where it correctly flagged **47.9%** of theorems as having missing or forward-referencing definitions, a capability that standard "Naive RAG" masks (93.3% Failure Rate) due to hallucinated validity.

This repository contains the source code, dataset, and formal verification findings for the paper:  
**"Automated Auditing of Mathematical Curricula: A Causal Neuro-Symbolic Framework with Formal Verification"** (ICLR 2026 Submission).

---

## 🏛️ Architecture & Methodology

Our system integrates a Semantic Knowledge Graph (Neo4j) with a Causal Controller that filters Vector Search (ChromaDB) results based on curriculum metadata.

![Architecture Diagram](assets_readme/architecture_diagram.png)

### 1. The Causal Controller (Hybrid Retrieval)
Unlike standard RAG, which retrieves the most semantically similar context regardless of its position in the text, MathemaTest implements a **Causal Filter**.

**Algorithm:**
Given a query theorem $T$ located in Chapter $C_{query}$:
1.  **Vector Retrieval:** Fetch Top-K candidates $\{D_1, ..., D_K\}$ from ChromaDB.
2.  **Temporal Filtering:** Discard any document $D_i$ where:
    $$ D_i.chapter\_index > C_{query} $$ 
    This prevents the model from "cheating" by peeking at future definitions (e.g., using Chapter 3's *Derivative* definition to validate a Chapter 1 theorem).
3.  **Graph Traversal:** Traverse `DEPENDS_ON` edges in Neo4j to gather explicit historical dependencies.

### 2. The Neuro-Symbolic Bridge
We employ a two-stage verification pipeline to audit each theorem:
*   **Semantic Verification (LLM):** Checks consistency using Causal GraphRAG.
*   **Syntactic Verification (Lean 4):** Attempts to auto-formalize the theorem into verifiable code.
    *   *Prompt Strategy:* Few-shot Chain-of-Thought targeting `Mathlib` imports.
    *   *Constraint:* "If a definition is missing from the provided context, you must DECLARE it as a hypothesis, do not hallucinate a library import."

---

## 📚 Dataset: OpenStax Calculus

The system was audited on the industry-standard *OpenStax Calculus Volume 1* textbook.

| Metric | Count | Description |
| :--- | :--- | :--- |
| **Total Audit Scope** | **503 Items** | Theorems, Lemmas, and Definitions |
| **Chapters** | 1-6 | Functions, Limits, Derivatives, Integration |
| **Graph Nodes** | ~4,120 | Total semantic clusters in Neo4j |
| **Graph Density** | 3.02 | Edges per node (Sparse Dependency Graph) |

---

## 🔬 Case Study: The "RAG Lobotomy"

To demonstrate the failure of standard RAG, we analyzed **Theorem 1.2.3** (Velocity), which intuitively references "Derivatives" in Chapter 1, despite the formal definition appearing in Chapter 3.

**The Query:** *"Is the theorem about instantaneous velocity valid?"*

| Method | Retrieved Context | Model Response | Verdict |
| :--- | :--- | :--- | :--- |
| **Naive RAG** | **Definition 3.1** (Chapter 3) | *"YES. The theorem is valid because velocity is defined as the derivative (Def 3.1)..."* | ❌ **False Positive** (Hallucination) |
| **Our Framework** | *Empty / Ch 1 Only* | *"NO. The term 'derivative' has not been defined yet in the current context. This is a gap."* | ✅ **True Negative** (Gap Detected) |

We term this phenomenon the **"RAG Lobotomy"**: Providing future context removes the model's ability to perceive the pedagogical structure, effectively "lobotomizing" its critical reasoning.

---

## 📊 Evaluation & Results

### 1. The Lobotomy Benchmark (n=30 Verified Gaps)
We sampled 30 items with known pedagogical gaps. Standard RAG (Red) almost entirely masks these gaps, while MathemaTest (Green) recovers the baseline skepticism of the Raw model.

![RAG Lobotomy Benchmark](assets_readme/rag_lobotomy_benchmark.png)

### 2. The Neuro-Symbolic Gap (Global Audit n=503)
Running the system on the full corpus revealed a massive capability gap between **Semantic Logic** (LLM reasoning) and **Syntactic Formalization** (Code generation).

![Neuro-Symbolic Gap Funnel](assets_readme/neurosymbolic_gap_funnel.png)

| System Stage | Count (n) | Success Rate | Interpretation |
| :--- | :--- | :--- | :--- |
| **Total Items** | 503 | 100% | Full Corpus |
| **Logically Consistent** | 262 | 52.1% | Verified by GPT-4o Semantic Check |
| **Pedagogical Gaps** | 241 | 47.9% | Missing Prerequisites / Forward References |
| **Formally Verified** | **0** | **0.0%** | **No Theorem Compiled Successfully** |

### 3. Pedagogical Heatmap
The "Gap Density" is highest in **Chapter 1 (Functions)**, confirming that early chapters rely heavily on intuition (Real Analysis concepts) that are not rigorously defined until later.

![Pedagogical Heatmap](assets_readme/pedagogical_heatmap.png)

---

## 🚀 Future Work: DeepSeek-Prover
The **0% Formal Verification** rate is a critical finding. It highlights that general-purpose models (GPT-4o) cannot bridge the gap to formal verification without extensive human-in-the-loop annotations. 
We argue that integrating specialized reasoning models like **DeepSeek-Prover-V1.5** (projected impact shown in Fig 2) is the necessary next step to achieve autonomous formalization of textbook mathematics.

---

## 🛠️ Usage

### Prerequisites
*   Python 3.11+
*   Neo4j Database (AuraDB or Local)
*   OpenAI API Key

### Installation
1.  **Clone & Install:**
    ```bash
    git clone https://github.com/neil-ravat/MathemaTest.git
    cd MathemaTest
    pip install -r requirements.txt
    ```

2.  **Configuration:**
    Create a `.env` file:
    ```bash
    NEO4J_URI=bolt://localhost:7687
    NEO4J_PASSWORD=your_password
    OPENAI_API_KEY=sk-...
    ```

3.  **Run the Audit:**
    ```bash
    # Run the full Causal Audit on the Textbook
    python scripts/run_textbook_audit.py
    ```

4.  **Reproduce Plots:**
    ```bash
    # Generate the Figures from the paper
    python scripts/generate_finale_plots.py
    ```

---

## 📚 Citation

```bibtex
@inproceedings{mathematest2026,
  title={Automated Auditing of Mathematical Curricula via Causal Neuro-Symbolic GraphRAG},
  author={Shirgaonkar, Vedant},
  booktitle={N/A},
  year={2026}
}
```
