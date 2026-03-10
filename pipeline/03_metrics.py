#!/usr/bin/env python3
"""
pipeline/03_metrics.py

Stage 3: Structural Metric Computation

For each extracted bug JSON in data/extracted/, this script:
  1. Parses each trigger test function using the AST
  2. Computes structural metrics:
       - loc: lines of code in the test function
       - assertion_count: number of assert statements / self.assert* calls
       - exception_testing: bool, True if test uses pytest.raises or assertRaises
       - fixture_count: number of @pytest.fixture decorators or fixture parameters
       - parameterized: bool, True if test uses @pytest.mark.parametrize
       - cyclomatic_complexity: McCabe complexity via radon
  3. Writes enriched JSON to data/classified/ (intermediate -- classify.py adds gap_type)

Output: data/classified/{bug_id}.json  (metrics added, gap_type not yet assigned)

Run:
    python3 pipeline/03_metrics.py
    python3 pipeline/03_metrics.py --bug pandas_1 --verbose
    python3 pipeline/03_metrics.py --force
"""

import argparse
import ast
import json
import logging
import sys
import textwrap
from pathlib import Path

from radon.complexity import cc_visit
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"
CLASSIFIED_DIR = PROJECT_ROOT / "data" / "classified"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def compute_metrics(test_source: str) -> dict:
    """Compute structural metrics for a single test function source string."""
    metrics = {
        "loc": 0,
        "assertion_count": 0,
        "exception_testing": False,
        "fixture_count": 0,
        "parameterized": False,
        "cyclomatic_complexity": 1,
    }

    if not test_source or not test_source.strip():
        return metrics

    lines = [l for l in test_source.splitlines() if l.strip()]
    metrics["loc"] = len(lines)

    # Dedent to handle indented class methods
    dedented = textwrap.dedent(test_source)

    try:
        tree = ast.parse(dedented)
    except SyntaxError:
        return metrics

    for node in ast.walk(tree):
        # Assertion count: assert statements and self.assert* calls
        if isinstance(node, ast.Assert):
            metrics["assertion_count"] += 1
        elif isinstance(node, ast.Call):
            func = node.func
            # self.assert* pattern
            if isinstance(func, ast.Attribute) and func.attr.startswith("assert"):
                metrics["assertion_count"] += 1
            # pytest.raises
            if isinstance(func, ast.Attribute) and func.attr == "raises":
                if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                    metrics["exception_testing"] = True
            # self.assertRaises / unittest assertRaises
            if isinstance(func, ast.Attribute) and func.attr == "assertRaises":
                metrics["exception_testing"] = True

        # Exception via context manager: with pytest.raises(...) or with self.assertRaises(...)
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if isinstance(call, ast.Call):
                    f = call.func
                    if isinstance(f, ast.Attribute) and f.attr in ("raises", "assertRaises"):
                        metrics["exception_testing"] = True

    # Decorators (must look at FunctionDef node)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
            for decorator in node.decorator_list:
                # @pytest.mark.parametrize
                if isinstance(decorator, ast.Call):
                    func = decorator.func
                    if isinstance(func, ast.Attribute) and func.attr == "parametrize":
                        metrics["parameterized"] = True
                    if isinstance(func, ast.Attribute) and func.attr == "fixture":
                        metrics["fixture_count"] += 1
                elif isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                    metrics["fixture_count"] += 1

            # Count fixture parameters (function args that are fixture names -- heuristic: non-self args)
            args = node.args
            param_names = [a.arg for a in args.args if a.arg != "self"]
            # This is a heuristic: we count non-self parameters as potential fixture injections
            # only if there are no default values (unfilled fixtures)
            fixture_params = len(param_names) - len(args.defaults)
            if fixture_params > 0:
                metrics["fixture_count"] += fixture_params

    # Cyclomatic complexity via radon
    try:
        results = cc_visit(dedented)
        if results:
            metrics["cyclomatic_complexity"] = results[0].complexity
    except Exception:
        pass

    return metrics


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def process_bug(extracted_path: Path, classified_dir: Path, force: bool, verbose: bool) -> bool:
    out_path = classified_dir / extracted_path.name
    if out_path.exists() and not force:
        if verbose:
            log.info("Skipping %s (already has metrics)", extracted_path.stem)
        return False

    try:
        data = json.loads(extracted_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Could not read %s: %s", extracted_path, e)
        return False

    for test in data.get("trigger_tests", []):
        source = test.get("test_source", "")
        test["metrics"] = compute_metrics(source)
        # gap_type will be added by 04_classify.py
        test["gap_type"] = None
        test["gap_type_priority_matched"] = None

    if verbose:
        log.info("Computed metrics for %s (%d tests)", data["bug_id"], len(data["trigger_tests"]))

    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stage 3: Compute structural metrics for trigger tests.")
    parser.add_argument("--bug", type=str, default=None, help="Process only this bug_id")
    parser.add_argument("--force", action="store_true", help="Re-process already completed bugs")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    CLASSIFIED_DIR.mkdir(parents=True, exist_ok=True)

    paths = sorted(EXTRACTED_DIR.glob("*.json"))
    if not paths:
        log.error("No extracted bugs found in %s. Run pipeline/02_extract.py first.", EXTRACTED_DIR)
        sys.exit(1)

    if args.bug:
        paths = [p for p in paths if p.stem == args.bug]
        if not paths:
            log.error("Bug '%s' not found in extracted output.", args.bug)
            sys.exit(1)

    written = skipped = 0
    for path in tqdm(paths, desc="Computing metrics", disable=args.verbose):
        if process_bug(path, CLASSIFIED_DIR, force=args.force, verbose=args.verbose):
            written += 1
        else:
            skipped += 1

    log.info("Done. Written: %d, Skipped: %d", written, skipped)


if __name__ == "__main__":
    main()
