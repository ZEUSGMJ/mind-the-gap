#!/usr/bin/env python3
"""
pipeline/04b_classify_ollama.py

Cohen's Kappa via Local LLM (Ollama)

Sends each trigger test to local Ollama models for classification using the same
priority-ordered rules as the AST-based classifier (04_classify.py). Computes
Cohen's kappa between the rule-based labels and each LLM's labels.

Prerequisites:
    - Ollama running at http://localhost:11434
    - Compatible models pulled locally, for example phi3:mini

Run:
    python3 pipeline/04b_classify_ollama.py
    python3 pipeline/04b_classify_ollama.py --model phi3:mini
    python3 pipeline/04b_classify_ollama.py --bug pandas_1 --verbose
"""

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLASSIFIED_DIR = PROJECT_ROOT / "data" / "classified"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"

DEFAULT_MODELS = [
    {"model": "phi3:mini", "params": "3.8B"},
    {"model": "qwen3.5:4b", "params": "4B"},
    {"model": "llama3.3:8b", "params": "8B"},
]

GAP_TYPES = [
    "EXCEPTION_HANDLING",
    "BOUNDARY_CONDITION",
    "STATE_TRANSITION",
    "NONE_NULL_HANDLING",
    "RETURN_VALUE",
    "TYPE_COERCION",
    "OTHER",
]

# Same prompt used in 04_classify.py for the Anthropic API LLM pass
LLM_SYSTEM = """You are a research assistant classifying Python regression tests into semantic gap types.
Apply the following rules in priority order. Return ONLY the gap type name, nothing else.

Priority 1: EXCEPTION_HANDLING -- test uses pytest.raises, assertRaises, or with self.assertRaises
Priority 2: BOUNDARY_CONDITION -- test inputs include 0, -1, sys.maxsize, float('inf'), float('-inf'), empty [], {}, "", b""
Priority 3: STATE_TRANSITION -- test uses autouse fixtures or explicit setUp/tearDown
Priority 4: NONE_NULL_HANDLING -- test inputs or assertions involve None or NaN
Priority 5: RETURN_VALUE -- test asserts on a specific return value
Priority 6: TYPE_COERCION -- test passes a literal of wrong type for the parameter
Priority 7: OTHER -- none of the above

Return one of: EXCEPTION_HANDLING, BOUNDARY_CONDITION, STATE_TRANSITION, NONE_NULL_HANDLING, RETURN_VALUE, TYPE_COERCION, OTHER"""


# ---------------------------------------------------------------------------
# Cohen's Kappa (copied from 04_classify.py to keep this script standalone)
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
# Ollama classification
# ---------------------------------------------------------------------------

def ollama_classify(test_source: str, model: str) -> str:
    """Send a test to the Ollama model and parse the gap type response."""
    prompt = f"{LLM_SYSTEM}\n\nClassify this test:\n\n```python\n{test_source}\n```"
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 30, "temperature": 0.0},
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        # Extract the gap type from the response (model may add extra text)
        for gap_type in GAP_TYPES:
            if gap_type in raw.upper():
                return gap_type
        log.debug("Could not parse LLM response for model %s: %s", model, raw)
        return "OTHER"
    except Exception as e:
        log.warning("Ollama call failed (model=%s): %s", model, e)
        return "OTHER"


# ---------------------------------------------------------------------------
# Load all classified tests
# ---------------------------------------------------------------------------

def load_tests(bug_filter: str = None) -> list[dict]:
    """Load all trigger tests with their AST-based gap_type labels."""
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

def print_confusion(rule_labels: list[str], llm_labels: list[str], model_name: str):
    """Print a simple confusion matrix of disagreements."""
    present = sorted(set(rule_labels + llm_labels))
    matrix = {a: Counter() for a in present}
    for r, l in zip(rule_labels, llm_labels):
        matrix[r][l] += 1

    # Header
    col_w = max(len(g) for g in present)
    header = f"{'Rule \\ LLM':<22}" + "".join(f"{g:>{col_w+2}}" for g in present)
    print(f"\nConfusion Matrix ({model_name}):")
    print(header)
    print("-" * len(header))
    for row in present:
        vals = "".join(f"{matrix[row][col]:>{col_w+2}}" for col in present)
        print(f"{row:<22}{vals}")

    # Disagreements
    disagreements = [(r, l) for r, l in zip(rule_labels, llm_labels) if r != l]
    if disagreements:
        print(f"\nDisagreements: {len(disagreements)} / {len(rule_labels)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Cohen's kappa via local Ollama LLMs.")
    parser.add_argument("--model", type=str, default=None, help="Run only this model (e.g., phi3:mini)")
    parser.add_argument("--bug", type=str, default=None, help="Process only this bug_id")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Check Ollama is reachable
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        r.raise_for_status()
        available = [m["name"] for m in r.json().get("models", [])]
        log.info("Ollama models available: %s", available)
    except Exception as e:
        log.error("Cannot reach Ollama at localhost:11434: %s", e)
        sys.exit(1)

    # Determine which models to run
    if args.model:
        models = [m for m in DEFAULT_MODELS if m["model"] == args.model]
        if not models:
            models = [{"model": args.model, "params": "unknown"}]
    else:
        models = DEFAULT_MODELS

    # Load tests
    tests = load_tests(bug_filter=args.bug)
    if not tests:
        log.error("No classified tests found.")
        sys.exit(1)
    log.info("Loaded %d tests for classification.", len(tests))

    rule_labels = [t["rule_label"] for t in tests]
    results = []
    all_llm_labels = {}  # model_name -> list of labels

    for model_info in models:
        model_name = model_info["model"]
        log.info("Running model: %s (%s)", model_name, model_info["params"])

        llm_labels = []
        for t in tqdm(tests, desc=model_name):
            label = ollama_classify(t["test_source"], model_name)
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
                 model_name, kappa, agreement, len(rule_labels), agreement_pct)

        print_confusion(rule_labels, llm_labels, model_name)
        all_llm_labels[model_name] = llm_labels

        results.append({
            "model": model_name,
            "params": model_info["params"],
            "kappa": round(kappa, 4),
            "n_tests": len(rule_labels),
            "agreement_pct": agreement_pct,
        })

    # Save results (merge with existing results from previous runs)
    kappa_path = RESULTS_DIR / "cohens_kappa.json"
    existing_models = []
    if kappa_path.exists():
        try:
            existing_data = json.loads(kappa_path.read_text(encoding="utf-8"))
            existing_models = existing_data.get("models", [])
        except Exception:
            pass
    # Replace entries for models we just ran, keep others
    ran_names = {r["model"] for r in results}
    merged = [m for m in existing_models if m["model"] not in ran_names] + results
    kappa_data = {
        "models": merged,
        "note": "Agreement between priority rule-based AST classifier and local LLM classifiers via Ollama",
    }
    kappa_path.write_text(json.dumps(kappa_data, indent=2), encoding="utf-8")
    log.info("Results saved to %s", kappa_path)

    # Save per-model disagreements (uses labels already computed above)
    if not args.bug and all_llm_labels:
        for model_name, llm_labels in all_llm_labels.items():
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
            safe_name = model_name.replace(":", "_").replace("/", "_")
            disagree_path = RESULTS_DIR / f"kappa_disagreements_{safe_name}.json"
            disagree_path.write_text(json.dumps(disagreements, indent=2), encoding="utf-8")
            log.info("Disagreements for %s saved to %s", model_name, disagree_path)


if __name__ == "__main__":
    main()
