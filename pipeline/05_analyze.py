#!/usr/bin/env python3
"""
pipeline/05_analyze.py

Stage 5: Statistical Analysis and Results Generation

Reads all classified bug JSONs from data/classified/, aggregates into a flat
CSV, then runs:
  1. Distribution of semantic gap types (frequency + percentage)
  2. Structural metrics per gap type (mean, median, std)
  3. Mann-Whitney U test: pairwise comparisons between gap types on each metric
  4. Loads Cohen's kappa from data/results/cohens_kappa.json (computed by the 04b_* scripts)
  5. Writes summary tables and a flat CSV for use in the paper

Output:
  data/results/classified_bugs.csv     -- one row per trigger test
  data/results/gap_type_distribution.json
  data/results/structural_metrics.json
  data/results/mann_whitney.json
  data/results/summary.txt             -- human-readable summary for the paper

Run:
    python3 pipeline/05_analyze.py
    python3 pipeline/05_analyze.py --verbose
"""

import argparse
import json
import logging
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLASSIFIED_DIR = PROJECT_ROOT / "data" / "classified"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

STRUCTURAL_METRICS = ["loc", "assertion_count", "cyclomatic_complexity", "fixture_count"]
FIX_METRICS = ["fix_loc_added", "fix_loc_deleted", "fix_files_changed"]

# ---------------------------------------------------------------------------
# Load classified data into a flat DataFrame
# ---------------------------------------------------------------------------

def load_classified() -> pd.DataFrame:
    rows = []
    paths = sorted(CLASSIFIED_DIR.glob("*.json"))
    if not paths:
        log.error("No classified bugs found in %s.", CLASSIFIED_DIR)
        sys.exit(1)

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Could not read %s: %s", path, e)
            continue

        fix_metrics = data.get("fix_metrics", {})

        for test in data.get("trigger_tests", []):
            if not test.get("gap_type"):
                continue
            metrics = test.get("metrics", {})
            rows.append({
                "bug_id": data["bug_id"],
                "project": data["project"],
                "test_file": test.get("test_file", ""),
                "test_function": test.get("test_function", ""),
                "gap_type": test["gap_type"],
                "gap_type_priority_matched": test.get("gap_type_priority_matched"),
                "loc": metrics.get("loc", 0),
                "assertion_count": metrics.get("assertion_count", 0),
                "exception_testing": int(metrics.get("exception_testing", False)),
                "fixture_count": metrics.get("fixture_count", 0),
                "parameterized": int(metrics.get("parameterized", False)),
                "cyclomatic_complexity": metrics.get("cyclomatic_complexity", 1),
                "fix_loc_added": fix_metrics.get("fix_loc_added", 0),
                "fix_loc_deleted": fix_metrics.get("fix_loc_deleted", 0),
                "fix_files_changed": fix_metrics.get("fix_files_changed", 0),
                "gap_type_llm": test.get("gap_type_llm", None),
            })

    if not rows:
        log.error("No classified tests found. Run pipeline/04_classify.py first.")
        sys.exit(1)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def gap_type_distribution(df: pd.DataFrame) -> dict:
    counts = df["gap_type"].value_counts()
    total = len(df)
    result = {}
    for gap_type, count in counts.items():
        result[gap_type] = {
            "count": int(count),
            "percentage": round(100 * count / total, 2),
        }
    return result


def _bug_level_fix_df(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate fix metrics to one row per bug.

    Fix metrics are per-bug, not per-test. When a bug has multiple trigger tests,
    the fix metrics are identical across rows. Assign each bug's gap type as the
    most common type among its tests (mode). This avoids inflating sample size
    for fix-metric statistical tests.
    """
    bug_rows = []
    for bug_id, group in df.groupby("bug_id"):
        gap_type = group["gap_type"].mode().iloc[0]
        row = {"bug_id": bug_id, "gap_type": gap_type}
        for m in FIX_METRICS:
            row[m] = group[m].iloc[0]
        bug_rows.append(row)
    return pd.DataFrame(bug_rows)


def structural_metrics_per_type(df: pd.DataFrame) -> dict:
    result = {}
    bug_df = _bug_level_fix_df(df)
    for gap_type, group in df.groupby("gap_type"):
        result[gap_type] = {}
        for metric in STRUCTURAL_METRICS:
            vals = group[metric].dropna()
            result[gap_type][metric] = {
                "mean": round(float(vals.mean()), 3),
                "median": round(float(vals.median()), 3),
                "std": round(float(vals.std()), 3),
                "n": int(len(vals)),
            }
    # Fix metrics at bug level
    for gap_type, group in bug_df.groupby("gap_type"):
        if gap_type not in result:
            result[gap_type] = {}
        for metric in FIX_METRICS:
            vals = group[metric].dropna()
            result[gap_type][metric] = {
                "mean": round(float(vals.mean()), 3),
                "median": round(float(vals.median()), 3),
                "std": round(float(vals.std()), 3),
                "n": int(len(vals)),
            }
    return result


def mann_whitney_tests(df: pd.DataFrame) -> dict:
    """
    Pairwise Mann-Whitney U tests between all gap type pairs for each metric.
    Uses two-sided test. Reports U statistic and p-value.
    Fix metrics are tested at the bug level (deduplicated) to avoid inflated N.
    """
    results = {}
    gap_types = df["gap_type"].unique().tolist()
    bug_df = _bug_level_fix_df(df)

    for metric in STRUCTURAL_METRICS:
        results[metric] = {}
        for a, b in combinations(sorted(gap_types), 2):
            vals_a = df[df["gap_type"] == a][metric].dropna().values
            vals_b = df[df["gap_type"] == b][metric].dropna().values
            if len(vals_a) < 2 or len(vals_b) < 2:
                results[metric][f"{a}_vs_{b}"] = {"U": None, "p_value": None, "note": "insufficient data"}
                continue
            stat, p = mannwhitneyu(vals_a, vals_b, alternative="two-sided")
            results[metric][f"{a}_vs_{b}"] = {
                "U": round(float(stat), 4),
                "p_value": round(float(p), 6),
                "significant": bool(p < 0.05),
            }

    # Fix metrics at bug level
    bug_gap_types = bug_df["gap_type"].unique().tolist()
    for metric in FIX_METRICS:
        results[metric] = {}
        for a, b in combinations(sorted(bug_gap_types), 2):
            vals_a = bug_df[bug_df["gap_type"] == a][metric].dropna().values
            vals_b = bug_df[bug_df["gap_type"] == b][metric].dropna().values
            if len(vals_a) < 2 or len(vals_b) < 2:
                results[metric][f"{a}_vs_{b}"] = {"U": None, "p_value": None, "note": "insufficient data"}
                continue
            stat, p = mannwhitneyu(vals_a, vals_b, alternative="two-sided")
            results[metric][f"{a}_vs_{b}"] = {
                "U": round(float(stat), 4),
                "p_value": round(float(p), 6),
                "significant": bool(p < 0.05),
            }

    return results


def load_kappa() -> dict:
    kappa_path = RESULTS_DIR / "cohens_kappa.json"
    if kappa_path.exists():
        data = json.loads(kappa_path.read_text(encoding="utf-8"))
        # Support both old format {"kappa": x} and new format {"models": [...]}
        if "models" in data and data["models"]:
            return data
        return data
    return {"models": [], "note": "LLM second pass was not run"}


def write_summary(df: pd.DataFrame, distribution: dict, metrics_by_type: dict,
                  mw_results: dict, kappa: dict, out_path: Path):
    lines = []
    lines.append("=" * 60)
    lines.append("MIND THE GAP: ANALYSIS SUMMARY")
    lines.append("=" * 60)
    lines.append(f"\nTotal trigger tests analyzed: {len(df)}")
    lines.append(f"Total bugs: {df['bug_id'].nunique()}")
    lines.append(f"Projects: {df['project'].nunique()}")

    lines.append("\n--- Gap Type Distribution ---")
    for gt, info in sorted(distribution.items(), key=lambda x: -x[1]["count"]):
        lines.append(f"  {gt:<25} {info['count']:>4}  ({info['percentage']:>5.1f}%)")

    lines.append("\n--- Structural Metrics by Gap Type (mean / median) ---")
    for gt in sorted(metrics_by_type.keys()):
        lines.append(f"\n  {gt}")
        for metric, stats in metrics_by_type[gt].items():
            lines.append(f"    {metric:<30} mean={stats['mean']:.2f}  median={stats['median']:.2f}  n={stats['n']}")

    lines.append("\n--- Mann-Whitney U (significant pairs, p < 0.05) ---")
    for metric, pairs in mw_results.items():
        sig = {k: v for k, v in pairs.items() if v.get("significant")}
        if sig:
            lines.append(f"\n  {metric}")
            for pair, result in sig.items():
                lines.append(f"    {pair:<50} U={result['U']}  p={result['p_value']}")

    lines.append("\n--- Inter-Rater Agreement ---")
    models = kappa.get("models", [])
    if models:
        for m in models:
            lines.append(f"  {m['model']:<35} kappa={m['kappa']:.4f}  agreement={m['agreement_pct']}%  (n={m['n_tests']})")
    elif kappa.get("kappa") is not None:
        lines.append(f"  Cohen's kappa (rule vs. LLM): {kappa['kappa']:.4f}  (n={kappa.get('n_tests', '?')})")
    else:
        lines.append("  LLM second pass not run. Kappa not available.")

    lines.append("\n" + "=" * 60)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Summary written to %s", out_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stage 5: Aggregate classified tests into final analysis artifacts.")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Loading classified data...")
    df = load_classified()
    log.info("Loaded %d classified tests from %d bugs", len(df), df["bug_id"].nunique())

    # Write flat CSV
    csv_path = RESULTS_DIR / "classified_bugs.csv"
    df.to_csv(csv_path, index=False)
    log.info("Wrote %s", csv_path)

    # Distribution
    distribution = gap_type_distribution(df)
    (RESULTS_DIR / "gap_type_distribution.json").write_text(
        json.dumps(distribution, indent=2), encoding="utf-8"
    )

    # Structural metrics per type
    metrics_by_type = structural_metrics_per_type(df)
    (RESULTS_DIR / "structural_metrics.json").write_text(
        json.dumps(metrics_by_type, indent=2), encoding="utf-8"
    )

    # Mann-Whitney U
    mw_results = mann_whitney_tests(df)
    (RESULTS_DIR / "mann_whitney.json").write_text(
        json.dumps(mw_results, indent=2), encoding="utf-8"
    )

    # Kappa
    kappa = load_kappa()

    # Human-readable summary
    write_summary(df, distribution, metrics_by_type, mw_results, kappa,
                  RESULTS_DIR / "summary.txt")

    log.info("Analysis complete. Results in %s", RESULTS_DIR)


if __name__ == "__main__":
    main()
