#!/usr/bin/env python3
"""
pipeline/06c_compute_validation_agreement.py

Reads the completed validation_sheet.csv (after both raters fill in their columns)
and computes inter-rater agreement statistics.

Reports:
    - Jisnu vs AST classifier (% agreement + Cohen's kappa)
    - Suvarna vs AST classifier (% agreement + Cohen's kappa)
    - Jisnu vs Suvarna (% agreement + Cohen's kappa)

Output:
    data/results/manual_validation.json

Run:
    python3 pipeline/06c_compute_validation_agreement.py
"""

import csv
import json
import sys
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

GAP_TYPES = [
    "EXCEPTION_HANDLING",
    "BOUNDARY_CONDITION",
    "STATE_TRANSITION",
    "NONE_NULL_HANDLING",
    "RETURN_VALUE",
    "TYPE_COERCION",
    "OTHER",
]


def load_sheet(path: Path) -> list[dict]:
    """Load the completed validation CSV."""
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def compute_agreement(labels_a: list[str], labels_b: list[str], name_a: str, name_b: str) -> dict:
    """Compute agreement percentage and Cohen's kappa between two label lists."""
    assert len(labels_a) == len(labels_b), "Label lists must be same length"
    n = len(labels_a)
    agreed = sum(1 for a, b in zip(labels_a, labels_b) if a == b)
    pct = round(100 * agreed / n, 1) if n > 0 else 0.0

    try:
        kappa = round(cohen_kappa_score(labels_a, labels_b), 4)
    except Exception:
        kappa = None

    disagreements = []
    for i, (a, b) in enumerate(zip(labels_a, labels_b)):
        if a != b:
            disagreements.append({"index": i, name_a: a, name_b: b})

    return {
        "rater_a": name_a,
        "rater_b": name_b,
        "n": n,
        "agreed": agreed,
        "agreement_pct": pct,
        "kappa": kappa,
        "disagreements": disagreements,
    }


def main():
    csv_path = RESULTS_DIR / "validation_sheet.csv"
    if not csv_path.exists():
        print(f"Not found: {csv_path}")
        print("Run pipeline/06b_generate_validation_sheet.py first.")
        sys.exit(1)

    key_path = RESULTS_DIR / "validation_answer_key.csv"
    if not key_path.exists():
        print(f"Not found: {key_path}")
        print("Run pipeline/06b_generate_validation_sheet.py first.")
        sys.exit(1)

    rows = load_sheet(csv_path)
    key_rows = load_sheet(key_path)

    # Build answer key lookup by row_num
    key_by_row = {r["row_num"]: r["assigned_gap_type"] for r in key_rows}

    # Filter to rows where at least one rater provided a label
    ast_labels = []
    jisnu_labels = []
    suvarna_labels = []
    valid_rows = []

    for row in rows:
        jl = row.get("jisnu_label", "").strip().upper().replace(" ", "_")
        sl = row.get("suvarna_label", "").strip().upper().replace(" ", "_")
        ast = key_by_row.get(row.get("row_num", ""), "")

        if not jl and not sl:
            continue

        if jl and jl not in GAP_TYPES:
            print(f"Warning: invalid jisnu_label '{jl}' in row {row.get('row_num', '?')}, skipping")
            continue
        if sl and sl not in GAP_TYPES:
            print(f"Warning: invalid suvarna_label '{sl}' in row {row.get('row_num', '?')}, skipping")
            continue

        valid_rows.append(row)
        ast_labels.append(ast)
        jisnu_labels.append(jl if jl else None)
        suvarna_labels.append(sl if sl else None)

    if not valid_rows:
        print("No completed validations found. Fill in jisnu_label and/or suvarna_label columns first.")
        sys.exit(1)

    results = {"comparisons": []}

    # Jisnu vs AST
    jisnu_valid = [(a, j) for a, j in zip(ast_labels, jisnu_labels) if j]
    if jisnu_valid:
        a_list, j_list = zip(*jisnu_valid)
        comp = compute_agreement(list(a_list), list(j_list), "ast_classifier", "jisnu")
        results["comparisons"].append(comp)
        print(f"Jisnu vs AST:    {comp['agreement_pct']}% agreement, kappa={comp['kappa']}  (n={comp['n']})")

    # Suvarna vs AST
    suvarna_valid = [(a, s) for a, s in zip(ast_labels, suvarna_labels) if s]
    if suvarna_valid:
        a_list, s_list = zip(*suvarna_valid)
        comp = compute_agreement(list(a_list), list(s_list), "ast_classifier", "suvarna")
        results["comparisons"].append(comp)
        print(f"Suvarna vs AST:  {comp['agreement_pct']}% agreement, kappa={comp['kappa']}  (n={comp['n']})")

    # Jisnu vs Suvarna
    both_valid = [(j, s) for j, s in zip(jisnu_labels, suvarna_labels) if j and s]
    if both_valid:
        j_list, s_list = zip(*both_valid)
        comp = compute_agreement(list(j_list), list(s_list), "jisnu", "suvarna")
        results["comparisons"].append(comp)
        print(f"Jisnu vs Suvarna: {comp['agreement_pct']}% agreement, kappa={comp['kappa']}  (n={comp['n']})")

    # Save
    out_path = RESULTS_DIR / "manual_validation.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
