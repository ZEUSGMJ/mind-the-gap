#!/usr/bin/env python3
"""
pipeline/04_classify.py

Stage 4: Semantic Gap Type Classification

For each trigger test in data/classified/, applies the priority-ordered rule-based
classifier to assign a single gap type. Rules are applied in priority order and the
first match wins, ensuring mutual exclusivity.

Classification Scheme:

  Priority 1: EXCEPTION_HANDLING
    Test body uses pytest.raises, assertRaises, or with self.assertRaises

  Priority 2: BOUNDARY_CONDITION
    Test inputs include numeric boundary literals: 0, -1, sys.maxsize,
    float('inf'), float('-inf'), or empty containers: [], {}, "", b""

  Priority 3: STATE_TRANSITION
    Test uses @pytest.fixture with autouse=True, or calls explicit
    setup/teardown methods

  Priority 4: NONE_NULL_HANDLING
    Test inputs or assertions involve None or float('nan')

  Priority 5: RETURN_VALUE
    Test asserts on a specific return value (assertEqual, assert x == y, assertIs)
    but does NOT match any of the above

  Priority 6: TYPE_COERCION
    Test passes a literal whose type does not match an annotated parameter type

  Priority 7: OTHER
    No rule matched

This script can optionally run a second-pass LLM classifier (via Anthropic API)
to compute Cohen's kappa between the rule-based and LLM-based classifications,
validating reproducibility without introducing human bias.

Output: updates data/classified/{bug_id}.json in-place with gap_type and gap_type_priority_matched

Run:
    python3 pipeline/04_classify.py
    python3 pipeline/04_classify.py --bug pandas_1 --verbose
    python3 pipeline/04_classify.py --force
    python3 pipeline/04_classify.py --llm        # opt in to inline LLM second pass
"""

import argparse
import ast
import json
import logging
import os
import sys
import textwrap
from pathlib import Path

import anthropic
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLASSIFIED_DIR = PROJECT_ROOT / "data" / "classified"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

GAP_TYPES = [
    "EXCEPTION_HANDLING",
    "BOUNDARY_CONDITION",
    "STATE_TRANSITION",
    "NONE_NULL_HANDLING",
    "RETURN_VALUE",
    "TYPE_COERCION",
    "OTHER",
]

BOUNDARY_NUMERIC_VALUES = {0, -1}
BOUNDARY_FLOAT_NAMES = {"inf"}

# ---------------------------------------------------------------------------
# Rule-based classifier
# ---------------------------------------------------------------------------

def classify(test_source: str, metrics: dict) -> tuple[str, int]:
    """
    Apply priority-ordered rules to assign a gap type.
    Returns (gap_type, priority_matched).
    """
    if not test_source or not test_source.strip():
        return "OTHER", 7

    # Priority 1: EXCEPTION_HANDLING -- already computed in metrics
    if metrics.get("exception_testing", False):
        return "EXCEPTION_HANDLING", 1

    # Dedent to handle indented class methods
    dedented = textwrap.dedent(test_source)

    # Parse AST for rules 2-6
    try:
        tree = ast.parse(dedented)
    except SyntaxError:
        return "OTHER", 7

    # Priority 2: BOUNDARY_CONDITION
    if _has_boundary_literals(tree):
        return "BOUNDARY_CONDITION", 2

    # Priority 3: STATE_TRANSITION
    if _has_state_transition(tree):
        return "STATE_TRANSITION", 3

    # Priority 4: NONE_NULL_HANDLING
    if _has_none_or_nan(tree):
        return "NONE_NULL_HANDLING", 4

    # Priority 5: RETURN_VALUE
    if metrics.get("assertion_count", 0) > 0:
        return "RETURN_VALUE", 5

    # Priority 6: TYPE_COERCION
    if _has_type_coercion(tree):
        return "TYPE_COERCION", 6

    return "OTHER", 7


def _has_boundary_literals(tree: ast.AST) -> bool:
    """Check for numeric boundary values or empty containers in test call arguments."""
    for node in ast.walk(tree):
        # Numeric literals: 0, -1 (but not booleans; False == 0 in Python)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                pass  # Skip booleans; bool is a subclass of int
            elif node.value in BOUNDARY_NUMERIC_VALUES:
                return True
            # Empty string or bytes
            if node.value in ("", b""):
                return True
        # Empty list, dict, set, tuple
        if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.Tuple)):
            if not (node.elts if hasattr(node, "elts") else node.keys):
                return True
        # UnaryOp for -1: UnaryOp(op=USub, operand=Constant(1))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            if isinstance(node.operand, ast.Constant) and node.operand.value == 1:
                return True
        # float('inf') / float('-inf')
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "float":
                if node.args and isinstance(node.args[0], ast.Constant):
                    if str(node.args[0].value).lower() in ("inf", "-inf"):
                        return True
        # sys.maxsize
        if isinstance(node, ast.Attribute):
            if node.attr == "maxsize" and isinstance(node.value, ast.Name) and node.value.id == "sys":
                return True
    return False


def _has_state_transition(tree: ast.AST) -> bool:
    """Check for autouse fixtures or explicit setUp/tearDown calls."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                # @pytest.fixture(autouse=True)
                if isinstance(decorator, ast.Call):
                    for kw in decorator.keywords:
                        if kw.arg == "autouse" and isinstance(kw.value, ast.Constant) and kw.value.value:
                            return True
            # setUp / tearDown method calls
            if node.name.startswith("test"):
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        f = child.func
                        if isinstance(f, ast.Attribute) and f.attr in ("setUp", "tearDown", "setup", "teardown"):
                            return True
    return False


def _has_none_or_nan(tree: ast.AST) -> bool:
    """Check for None or NaN in test inputs or assertions."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value is None:
            return True
        # float('nan')
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "float":
                if node.args and isinstance(node.args[0], ast.Constant):
                    if str(node.args[0].value).lower() == "nan":
                        return True
        # math.nan or numpy.nan
        if isinstance(node, ast.Attribute) and node.attr in ("nan", "NaN", "NAN"):
            return True
    return False


def _has_type_coercion(tree: ast.AST) -> bool:
    """
    Heuristic: test passes a string where a numeric is expected, or vice versa.
    Looks for function calls with mixed-type literal arguments (string + numeric together).
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args:
            arg_types = set()
            for arg in node.args:
                if isinstance(arg, ast.Constant):
                    arg_types.add(type(arg.value).__name__)
            if "str" in arg_types and ("int" in arg_types or "float" in arg_types):
                return True
    return False


# ---------------------------------------------------------------------------
# LLM second-pass classifier (for Cohen's kappa computation)
# ---------------------------------------------------------------------------

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


def llm_classify(test_source: str, client: anthropic.Anthropic) -> str:
    """Call Claude to classify a test function. Returns a gap type string."""
    try:
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=20,
            system=LLM_SYSTEM,
            messages=[{"role": "user", "content": f"Classify this test:\n\n```python\n{test_source}\n```"}],
        )
        result = message.content[0].text.strip().upper()
        if result in GAP_TYPES:
            return result
        return "OTHER"
    except Exception as e:
        log.warning("LLM classification failed: %s", e)
        return "OTHER"


# ---------------------------------------------------------------------------
# Cohen's Kappa
# ---------------------------------------------------------------------------

def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    """Compute Cohen's kappa between two lists of labels."""
    if len(labels_a) != len(labels_b) or not labels_a:
        return 0.0

    n = len(labels_a)
    categories = list(set(labels_a + labels_b))
    k = len(categories)
    cat_index = {c: i for i, c in enumerate(categories)}

    # Observed agreement
    po = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n

    # Expected agreement
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
# Processing
# ---------------------------------------------------------------------------

def process_bug(path: Path, force: bool, verbose: bool, llm_client=None) -> tuple[bool, list, list]:
    """
    Classify all trigger tests in one bug JSON.
    Returns (was_written, rule_labels, llm_labels).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Could not read %s: %s", path, e)
        return False, [], []

    tests = data.get("trigger_tests", [])
    if not tests:
        return False, [], []

    # Check if already classified
    already_done = all(t.get("gap_type") is not None for t in tests)
    if already_done and not force:
        if verbose:
            log.info("Skipping %s (already classified)", data["bug_id"])
        return False, [], []

    rule_labels = []
    llm_labels = []

    for test in tests:
        source = test.get("test_source", "")
        metrics = test.get("metrics", {})

        gap_type, priority = classify(source, metrics)
        test["gap_type"] = gap_type
        test["gap_type_priority_matched"] = priority
        rule_labels.append(gap_type)

        if llm_client:
            llm_gap = llm_classify(source, llm_client)
            test["gap_type_llm"] = llm_gap
            llm_labels.append(llm_gap)

    if verbose:
        log.info("Classified %s: %s", data["bug_id"], [t["gap_type"] for t in tests])

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True, rule_labels, llm_labels


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stage 4: Classify semantic gap types.")
    parser.add_argument("--bug", type=str, default=None, help="Process only this bug_id")
    parser.add_argument("--force", action="store_true", help="Re-classify already classified bugs")
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Run inline LLM second pass (default: off; use 04b_* scripts instead)",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    paths = sorted(CLASSIFIED_DIR.glob("*.json"))
    if not paths:
        log.error("No classified bugs found in %s. Run pipeline/03_metrics.py first.", CLASSIFIED_DIR)
        sys.exit(1)

    if args.bug:
        paths = [p for p in paths if p.stem == args.bug]
        if not paths:
            log.error("Bug '%s' not found in classified output.", args.bug)
            sys.exit(1)

    llm_client = None
    if args.llm:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            llm_client = anthropic.Anthropic(api_key=api_key)
            log.info("LLM second pass enabled (claude-opus-4-5)")
        else:
            log.warning("ANTHROPIC_API_KEY not set. Skipping inline LLM second pass.")

    all_rule_labels = []
    all_llm_labels = []
    written = skipped = 0

    for path in tqdm(paths, desc="Classifying", disable=args.verbose):
        was_written, rule_labels, llm_labels = process_bug(
            path, force=args.force, verbose=args.verbose, llm_client=llm_client
        )
        if was_written:
            written += 1
            all_rule_labels.extend(rule_labels)
            all_llm_labels.extend(llm_labels)
        else:
            skipped += 1

    log.info("Done. Written: %d, Skipped: %d", written, skipped)

    # Log kappa if LLM pass ran (do not write to file; use 04b_* scripts for persistent kappa)
    if all_rule_labels and all_llm_labels and len(all_rule_labels) == len(all_llm_labels):
        kappa = cohens_kappa(all_rule_labels, all_llm_labels)
        log.info("Cohen's kappa (rule vs. LLM): %.4f (not written to file; use 04b_* scripts for persistent kappa)", kappa)


if __name__ == "__main__":
    main()
