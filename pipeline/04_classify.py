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

Output: updates data/classified/{bug_id}.json in-place with gap_type and gap_type_priority_matched

Run:
    python3 pipeline/04_classify.py
    python3 pipeline/04_classify.py --bug pandas_1 --verbose
    python3 pipeline/04_classify.py --force
"""

import argparse
import ast
import json
import logging
import sys
import textwrap
from pathlib import Path

from tqdm import tqdm

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLASSIFIED_DIR = PROJECT_ROOT / "data" / "classified"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

BOUNDARY_NUMERIC_VALUES = {0, -1}

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
# Processing
# ---------------------------------------------------------------------------

def process_bug(path: Path, force: bool, verbose: bool) -> bool:
    """
    Classify all trigger tests in one bug JSON.
    Returns whether the bug JSON was updated.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Could not read %s: %s", path, e)
        return False

    tests = data.get("trigger_tests", [])
    if not tests:
        return False

    # Check if already classified
    already_done = all(t.get("gap_type") is not None for t in tests)
    if already_done and not force:
        if verbose:
            log.info("Skipping %s (already classified)", data["bug_id"])
        return False

    for test in tests:
        source = test.get("test_source", "")
        metrics = test.get("metrics", {})

        gap_type, priority = classify(source, metrics)
        test["gap_type"] = gap_type
        test["gap_type_priority_matched"] = priority

    if verbose:
        log.info("Classified %s: %s", data["bug_id"], [t["gap_type"] for t in tests])

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stage 4: Classify semantic gap types.")
    parser.add_argument("--bug", type=str, default=None, help="Process only this bug_id")
    parser.add_argument("--force", action="store_true", help="Re-classify already classified bugs")
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

    written = skipped = 0

    for path in tqdm(paths, desc="Classifying", disable=args.verbose):
        was_written = process_bug(path, force=args.force, verbose=args.verbose)
        if was_written:
            written += 1
        else:
            skipped += 1

    log.info("Done. Written: %d, Skipped: %d", written, skipped)


if __name__ == "__main__":
    main()
