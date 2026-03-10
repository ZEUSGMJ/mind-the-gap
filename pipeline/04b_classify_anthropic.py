#!/usr/bin/env python3
"""
pipeline/04b_classify_anthropic.py

Cohen's Kappa via Anthropic API (Claude Haiku).

Sends each trigger test to Claude Haiku for classification using the same
priority-ordered rules as the AST-based classifier (04_classify.py). Computes
Cohen's kappa between the rule-based labels and Haiku's labels.

Prerequisites:
    export ANTHROPIC_API_KEY=sk-ant-...

Run:
    python3 pipeline/04b_classify_anthropic.py
    python3 pipeline/04b_classify_anthropic.py --bug pandas_1 --verbose
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLASSIFIED_DIR = PROJECT_ROOT / "data" / "classified"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

GAP_TYPES = [
    "EXCEPTION_HANDLING",
    "BOUNDARY_CONDITION",
    "STATE_TRANSITION",
    "NONE_NULL_HANDLING",
    "RETURN_VALUE",
    "TYPE_COERCION",
    "OTHER",
]

SYSTEM_PROMPT = """You are a research assistant classifying Python regression tests into semantic gap types.
Apply the following rules in STRICT priority order. The FIRST matching rule wins. Return ONLY the gap type name on a single line, nothing else.

Priority 1: EXCEPTION_HANDLING -- test body contains pytest.raises, assertRaises, or with self.assertRaises
Priority 2: BOUNDARY_CONDITION -- test inputs include numeric boundary values (0, -1, sys.maxsize, float('inf'), float('-inf')) or empty containers ([], {}, "", b"")
Priority 3: STATE_TRANSITION -- test uses @pytest.fixture with autouse=True, or calls explicit setUp/tearDown methods
Priority 4: NONE_NULL_HANDLING -- test inputs or assertions involve None or float('nan')
Priority 5: RETURN_VALUE -- test asserts on a specific return value using assertEqual, assert x == y, or assertIs
Priority 6: TYPE_COERCION -- test passes a literal whose type does not match the annotated parameter type
Priority 7: OTHER -- none of the above

Return exactly one of: EXCEPTION_HANDLING, BOUNDARY_CONDITION, STATE_TRANSITION, NONE_NULL_HANDLING, RETURN_VALUE, TYPE_COERCION, OTHER"""


# ---------------------------------------------------------------------------
# Cohen's Kappa
# ---------------------------------------------------------------------------

def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    if len(labels_a) != len(labels_b) or not labels_a:
        return 0.0
    n = len(labels_a)
    categories = list(set(labels_a + labels_b))
    k = len(categories)
    cat_index = {c: i for i, c in enumerate(categories)}
    po = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    count_a = [0] * k
    count_b = [0] * k
    for a, b in zip(labels_a, labels_b):
        count_a[cat_index[a]] += 1
        count_b[cat_index[b]] += 1
    pe = sum((count_a[i] / n) * (count_b[i] / n) for i in range(k))
    if pe == 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


# ---------------------------------------------------------------------------
# Anthropic classification
# ---------------------------------------------------------------------------

def classify_test(client: Anthropic, test_source: str) -> str:
    """Send a test to Claude Haiku and parse the gap type response."""
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=20,
            temperature=0.0,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"Classify this test:\n\n```python\n{test_source}\n```"}
            ],
        )
        raw = response.content[0].text.strip().upper()
        for gap_type in GAP_TYPES:
            if gap_type in raw:
                return gap_type
        log.debug("Could not parse response: %s", raw)
        return "OTHER"
    except Exception as e:
        log.warning("API call failed: %s", e)
        return "OTHER"


# ---------------------------------------------------------------------------
# Load all classified tests
# ---------------------------------------------------------------------------

def load_tests(bug_filter: str = None) -> list[dict]:
    tests = []
    paths = sorted(CLASSIFIED_DIR.glob("*.json"))
    if bug_filter:
        paths = [p for p in paths if p.stem == bug_filter]
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for t in data.get("trigger_tests", []):
            if t.get("gap_type") and t.get("test_source", "").strip():
                tests.append({
                    "bug_id": data["bug_id"],
                    "test_function": t.get("test_function", ""),
                    "test_source": t["test_source"],
                    "rule_label": t["gap_type"],
                })
    return tests


# ---------------------------------------------------------------------------
# Confusion matrix
# ---------------------------------------------------------------------------

def print_confusion(rule_labels: list[str], llm_labels: list[str]):
    present = sorted(set(rule_labels + llm_labels))
    matrix = {a: Counter() for a in present}
    for r, l in zip(rule_labels, llm_labels):
        matrix[r][l] += 1

    col_w = max(len(g) for g in present)
    header = f"{'Rule \\ LLM':<22}" + "".join(f"{g:>{col_w+2}}" for g in present)
    print(f"\nConfusion Matrix ({MODEL}):")
    print(header)
    print("-" * len(header))
    for row in present:
        vals = "".join(f"{matrix[row][col]:>{col_w+2}}" for col in present)
        print(f"{row:<22}{vals}")

    disagreements = [(r, l) for r, l in zip(rule_labels, llm_labels) if r != l]
    if disagreements:
        print(f"\nDisagreements: {len(disagreements)} / {len(rule_labels)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Cohen's kappa via Anthropic API (Claude Haiku).")
    parser.add_argument("--bug", type=str, default=None, help="Process only this bug_id")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY not set. Export it before running.")
        sys.exit(1)

    client = Anthropic(api_key=api_key)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    tests = load_tests(bug_filter=args.bug)
    if not tests:
        log.error("No classified tests found.")
        sys.exit(1)
    log.info("Loaded %d tests for classification.", len(tests))

    rule_labels = [t["rule_label"] for t in tests]
    llm_labels = []

    for t in tqdm(tests, desc=MODEL):
        label = classify_test(client, t["test_source"])
        llm_labels.append(label)
        if args.verbose:
            match = "OK" if label == t["rule_label"] else "MISMATCH"
            log.debug("  %s %s: rule=%s llm=%s %s",
                      t["bug_id"], t["test_function"], t["rule_label"], label, match)

    # Compute kappa
    kappa = cohens_kappa(rule_labels, llm_labels)
    agreement = sum(1 for r, l in zip(rule_labels, llm_labels) if r == l)
    agreement_pct = round(100 * agreement / len(rule_labels), 1)

    log.info("  %s: kappa=%.4f, agreement=%d/%d (%.1f%%)",
             MODEL, kappa, agreement, len(rule_labels), agreement_pct)

    print_confusion(rule_labels, llm_labels)

    result = {
        "model": MODEL,
        "params": "Claude Haiku 4.5",
        "kappa": round(kappa, 4),
        "n_tests": len(rule_labels),
        "agreement_pct": agreement_pct,
    }

    # Merge with existing kappa results
    kappa_path = RESULTS_DIR / "cohens_kappa.json"
    existing_models = []
    if kappa_path.exists():
        try:
            existing_data = json.loads(kappa_path.read_text(encoding="utf-8"))
            existing_models = existing_data.get("models", [])
        except Exception:
            pass
    merged = [m for m in existing_models if m["model"] != MODEL] + [result]
    kappa_data = {
        "models": merged,
        "note": "Agreement between priority rule-based AST classifier and LLM classifiers",
    }
    kappa_path.write_text(json.dumps(kappa_data, indent=2), encoding="utf-8")
    log.info("Results saved to %s", kappa_path)

    # Save disagreements
    if not args.bug:
        disagreements = []
        for t, rl, ll in zip(tests, rule_labels, llm_labels):
            if rl != ll:
                disagreements.append({
                    "bug_id": t["bug_id"],
                    "test_function": t["test_function"],
                    "rule_label": rl,
                    "llm_label": ll,
                    "test_source_preview": t["test_source"][:200],
                })
        disagree_path = RESULTS_DIR / "kappa_disagreements_haiku.json"
        disagree_path.write_text(json.dumps(disagreements, indent=2), encoding="utf-8")
        log.info("Disagreements saved to %s", disagree_path)


if __name__ == "__main__":
    main()
