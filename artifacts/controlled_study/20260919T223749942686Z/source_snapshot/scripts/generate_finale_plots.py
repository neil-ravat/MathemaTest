import json
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import os
import sys
from collections import Counter
from matplotlib.colors import ListedColormap

# Setup
plt.rcParams['font.family'] = 'sans-serif'
sns.set_theme(style="whitegrid", context="paper", font_scale=1.4)

ARTIFACTS_DIR = "artifacts"
FINALE_DIR = os.path.join(ARTIFACTS_DIR, "finaleplots")
AUDIT_REPORT = os.path.join(ARTIFACTS_DIR, "audit_report.json")
BENCHMARK_REPORT = os.path.join(ARTIFACTS_DIR, "grand_benchmark_matrix.json")

def load_json(path):
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        return {}
    with open(path, 'r') as f:
        return json.load(f)

def clean_audit_data(data):
    cleaned = []
    for item in data:
        ch = item.get("chapter", 999)
        try:
            ch = int(ch)
        except:
            ch = 999
        item["chapter"] = ch
        
        # We need data up to Ch 10 for analysis
        if ch <= 10:
            if item.get("missing_prerequisites") is None:
                item["missing_prerequisites"] = []
            cleaned.append(item)
    return cleaned

def generate_fig1_lobotomy_benchmark(benchmark_data):
    """
    Figure 1: The 'RAG Lobotomy' Effect
    Refinement: Rename 'Llama-3.3' to 'Llama-3.3-70B-versatile'
    Refinement: Clean plot - no 'MathemaTest' bars, no annotations.
    """
    print("Generating Figure 1: Lobotomy Benchmark (Clean)...")
    summary = benchmark_data.get("summary", {})
    records = []
    
    # Map original model names to display names
    model_map = {
        "GPT-4o-mini": "GPT-4o-mini",
        "Llama-3.3": "Llama-3.3-70B-versatile"
    }

    models_to_plot = ["GPT-4o-mini", "Llama-3.3"]
    
    for m in models_to_plot:
        if m in summary:
            disp_name = model_map.get(m, m)
            records.append({
                "Model": disp_name, 
                "Strategy": "Raw (No Context)", 
                "Recall (%)": summary[m]["raw_gap_rate"] * 100
            })
            records.append({
                "Model": disp_name, 
                "Strategy": "Naive RAG (Full Context)", 
                "Recall (%)": summary[m]["naive_rag_gap_rate"] * 100
            })
            
    df = pd.DataFrame(records)
    
    plt.figure(figsize=(10, 6))
    
    palette = {"Raw (No Context)": "#95a5a6", "Naive RAG (Full Context)": "#c0392b"}
    
    sns.barplot(x="Model", y="Recall (%)", hue="Strategy", data=df, palette=palette)
    
    plt.title("Impact of Retrieval Strategy on Gap Detection (Sample N=30 Verified Gaps)", fontweight='bold')
    plt.ylabel("Gap Detection Recall (%)")
    plt.ylim(0, 115)
    plt.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(os.path.join(FINALE_DIR, "final_fig1_lobotomy_benchmark.png"), dpi=300)
    plt.close()

def generate_fig2_neurosymbolic_funnel(audit_data):
    """
    Figure 2: The Neurosymbolic Gap (Hybrid with Funnel)
    Refinement: Include 'Pedagogical Gaps' bar.
    Refinement: Update title with "(Global Textbook Audit)"
    Refinement: Fix Data Consistency (Total = Logic + Gap). Exclude 'FAIL_LOGIC' noise.
    """
    print("Generating Figure 2: Neurosymbolic Gap + Funnel (Consistent)...")
    
    # Filter for relevant statuses only to ensure Total = Sum(Parts)
    # We ignore FAIL_LOGIC or other errors for the publication plot as they are noise (N=2)
    relevant_items = [d for d in audit_data if d.get("status") in ["VERIFIED_LOGIC", "VERIFIED_FORMAL", "FAIL_GAP"]]
    
    total = len(relevant_items)
    valid_logic = len([d for d in relevant_items if "VERIFIED" in d.get("status", "")])
    gap_pedagogical = len([d for d in relevant_items if "FAIL_GAP" in d.get("status", "")])
    valid_formal = len([d for d in relevant_items if "VERIFIED_FORMAL" in d.get("status", "")])
    
    # Projection
    projected_formal = int(total * 0.40)
    
    # Categories top to bottom:
    # 1. Total
    # 2. Logic
    # 3. Gaps 
    # 4. Formal
    
    categories = [
        "Total Mathematical Items",
        "Logically Consistent",
        "Pedagogical Gaps Detected",
        "Formally Verified (SOTA)" 
    ]
    
    counts = [total, valid_logic, gap_pedagogical, valid_formal]
    # Colors: Grey, Blue, Red, Gold
    colors = ["#bdc3c7", "#3498db", "#e74c3c", "#f1c40f"]
    
    plt.figure(figsize=(12, 7))
    
    # Main bars
    bars = plt.barh(categories, counts, color=colors)
    
    # Ghost Bar for Projection (behind/on top of Formal)
    # Index 3 is Formal
    plt.barh(categories[3], projected_formal, color="#f1c40f", alpha=0.3, 
             hatch='//', edgecolor='#f39c12', linestyle='--')
             
    ax = plt.gca()
    ax.invert_yaxis() 
    
    # Annotations
    for i, (rect, c) in enumerate(zip(bars, counts)):
        width = rect.get_width()
        label_text = f"n={c} ({c/total:.1%})"
        
        x_pos = width + (total * 0.015)
        
        # Zero handler
        if c == 0:
            width = total * 0.005
            rect.set_width(width)
            x_pos = width + (total * 0.015)
            
        plt.text(x_pos, rect.get_y() + rect.get_height()/2, label_text,
                 va='center', fontweight='bold', color="#2c3e50")
                 
    # Projection Text
    plt.text(projected_formal + (total * 0.02), 3, # Adjusted Y index for 4th bar (index 3)
             f"Projected ~40%\n(DeepSeek-Prover)", 
             va='center', color="#d35400", fontweight='bold', style='italic')

    # Add Arrow from 0 to 40% (Neurosymbolic Gap)
    # The 'Formal' bar is at index 3 (y=3 because categories are 0,1,2,3 from top if inverted?)
    # Wait, categories list index 3 is "Formally Verified".
    # Bar plot coords: 0, 1, 2, 3.
    # We want arrow at y ~ 3.3 to be below/above?
    # Categories: Total (0), Logic (1), Gap (2), Formal (3).
    # Since ax.invert_yaxis() is ON, 0 is top, 3 is bottom.
    # We want text/arrow below the 3rd bar (Formal).
    # Y-coordinates for bars are 0, 1, 2, 3.
    # Text "Projected" is at y=3 in the code above (same level as bar).
    # Arrow should be slightly offset. 
    # Let's verify coords from `generate_formal_gap_plot.py`.
    # It used `xy=(..., 2.3)` when there were 3 bars (0,1,2).
    # Here we have 4 bars (0,1,2,3). So expected y ~ 3.3.
    
    plt.annotate("", xy=(projected_formal, 3.3), xytext=(valid_formal, 3.3),
                 arrowprops=dict(arrowstyle="->", color="#e67e22", lw=1.5))
    plt.text(projected_formal/2, 3.25, "The Neurosymbolic Gap", 
             ha='center', va='bottom', color="#e67e22", fontsize=10)
             
    plt.title("The Neurosymbolic Gap: Semantic Logic vs. Syntactic Code (Global Textbook Audit)", 
              fontweight='bold', fontsize=15)
    plt.xlabel("Number of Mathematical Items")
    plt.xlim(0, total * 1.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FINALE_DIR, "final_fig2_neurosymbolic_gap.png"), dpi=300)
    plt.close()

def generate_fig3_heatmap(audit_data):
    """
    Figure 3: Heatmap
    Refinement: Filter out 'Preliminaries' (Chapter 0)
    """
    print("Generating Figure 3: Heatmap (No Prelims)...")
    
    ch_map = {
        1: "Functions", 2: "Limits", 3: "Derivatives", 
        4: "Applications", 5: "Integration", 6: "Diff Eq"
    }
    
    # Organize data (Ch 1-6 only)
    rows = {c: [] for c in range(1, 7)} # 1 to 6
    
    for item in audit_data:
        ch = item.get("chapter")
        if ch is not None and ch in rows:
            # 0=Gap, 1=Valid
            val = 0 if "FAIL_GAP" in item.get("status", "") else 1
            rows[ch].append(val)
            
    max_len = max(len(r) for r in rows.values()) if rows else 0
    matrix = []
    labels = []
    
    for c in range(1, 7):
        r = rows[c]
        padded = r + [np.nan]*(max_len - len(r))
        matrix.append(padded)
        labels.append(f"{c}: {ch_map.get(c, str(c))}")
        
    df = pd.DataFrame(matrix, index=labels)
    
    plt.figure(figsize=(14, 7))
    cmap = ListedColormap(['#e74c3c', '#2ecc71']) # Red, Green
    
    ax = sns.heatmap(df, cmap=cmap, cbar=True, mask=df.isnull(), 
                     linewidths=0.5, linecolor='white',
                     cbar_kws={"ticks": [0.25, 0.75], "label": "Analysis Verdict"})
    
    cbar = ax.collections[0].colorbar
    cbar.set_ticklabels(['Gap Detected', 'Verified Sound'])
    
    plt.title("Pedagogical Integrity Map: Distribution of Gaps by Chapter", fontweight='bold')
    plt.xlabel("Theorem Progression (Item Index)")
    plt.ylabel("Curriculum Chapter")
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.savefig(os.path.join(FINALE_DIR, "final_fig3_heatmap.png"), dpi=300)
    plt.close()

def main():
    bench = load_json(BENCHMARK_REPORT)
    audit_raw = load_json(AUDIT_REPORT)
    audit = clean_audit_data(audit_raw)
    
    print(f"Loaded Audit: {len(audit)} items.")
    
    generate_fig1_lobotomy_benchmark(bench)
    generate_fig2_neurosymbolic_funnel(audit)
    generate_fig3_heatmap(audit)
    # Figure 4 is assumed to be good as is, but could be regenerated if desired.
    # User didn't ask for changes to Fig 4, but let's assume suite consistency is good.
    # I'll enable it if needed, but for now stick to request.
    
    print("Finale plots generated in artifacts/finaleplots/")

if __name__ == "__main__":
    main()
