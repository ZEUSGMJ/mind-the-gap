#!/usr/bin/env python3
"""
pipeline/06b_generate_validation_sheet.py

Generates a CSV validation sheet for two independent human raters.
Samples 15 bugs (stratified by project) and outputs one row per test
with the test source, assigned classification, and empty columns for
each rater to fill in.

Also generates a companion instructions file.

Output:
    data/results/validation_sheet.csv
    data/results/validation_instructions.md

Run:
    python3 pipeline/06b_generate_validation_sheet.py
    python3 pipeline/06b_generate_validation_sheet.py --n 10
"""

import argparse
import csv
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLASSIFIED_DIR = PROJECT_ROOT / "data" / "classified"
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

PRIORITY_EXPLANATIONS = {
    1: "EXCEPTION_HANDLING: test uses pytest.raises, assertRaises, or self.assertRaises",
    2: "BOUNDARY_CONDITION: inputs include 0, -1, sys.maxsize, float('inf'), empty [], {}, \"\", b\"\"",
    3: "STATE_TRANSITION: uses autouse fixtures or explicit setUp/tearDown",
    4: "NONE_NULL_HANDLING: inputs or assertions involve None or NaN",
    5: "RETURN_VALUE: asserts on a specific return value",
    6: "TYPE_COERCION: passes a literal of wrong type for the parameter",
    7: "OTHER: no rule matched",
}


def load_bugs_with_tests() -> list[dict]:
    """Load all bugs that have classified trigger tests."""
    bugs = []
    for path in sorted(CLASSIFIED_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        tests = [t for t in data.get("trigger_tests", [])
                 if t.get("gap_type") and t.get("test_source", "").strip()]
        if tests:
            bugs.append(data)
    return bugs


def stratified_sample(bugs: list[dict], n: int) -> list[dict]:
    """Sample n bugs, at least 1 per project where possible."""
    by_project = {}
    for bug in bugs:
        by_project.setdefault(bug["project"], []).append(bug)

    sampled = []
    projects = sorted(by_project.keys())

    # First pass: one per project
    for proj in projects:
        if len(sampled) >= n:
            break
        choice = random.choice(by_project[proj])
        sampled.append(choice)
        by_project[proj].remove(choice)

    # Second pass: fill remaining slots
    remaining = []
    for proj_bugs in by_project.values():
        remaining.extend(proj_bugs)
    random.shuffle(remaining)

    while len(sampled) < n and remaining:
        sampled.append(remaining.pop())

    return sampled[:n]


def generate_csv(sample: list[dict], out_path: Path, answer_key_path: Path):
    """Write blinded validation CSV (no classifier answers) and a separate answer key."""
    fieldnames = [
        "row_num", "bug_id", "project", "test_file", "test_function",
        "test_source", "jisnu_label", "suvarna_label",
        "jisnu_notes", "suvarna_notes",
    ]

    rows = []
    answer_key = []
    idx = 0
    for bug in sample:
        for test in bug.get("trigger_tests", []):
            if not test.get("gap_type") or not test.get("test_source", "").strip():
                continue
            idx += 1
            priority = test.get("gap_type_priority_matched", 7)
            rows.append({
                "row_num": idx,
                "bug_id": bug["bug_id"],
                "project": bug["project"],
                "test_file": test.get("test_file", ""),
                "test_function": test.get("test_function", ""),
                "test_source": test["test_source"],
                "jisnu_label": "",
                "suvarna_label": "",
                "jisnu_notes": "",
                "suvarna_notes": "",
            })
            answer_key.append({
                "row_num": idx,
                "bug_id": bug["bug_id"],
                "test_function": test.get("test_function", ""),
                "assigned_gap_type": test["gap_type"],
                "priority_matched": priority,
                "rule_explanation": PRIORITY_EXPLANATIONS.get(priority, "unknown"),
            })

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Write answer key separately (not shared with raters)
    key_fields = ["row_num", "bug_id", "test_function", "assigned_gap_type",
                  "priority_matched", "rule_explanation"]
    with open(answer_key_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=key_fields)
        writer.writeheader()
        writer.writerows(answer_key)

    return rows


def generate_instructions(out_path: Path, n_bugs: int, n_tests: int, projects: list[str]):
    """Write companion instructions file."""
    projects_str = ", ".join(sorted(projects))
    text = f"""# Manual Validation Instructions

Hey Suvarna, I put together this spreadsheet so we can both validate the classifier's output independently. There are {n_tests} test functions from {n_bugs} sampled bugs across {len(projects)} projects in our dataset.

What you need to do: read each test's source code and decide which gap type it belongs to, using the rules below.

## Before you start

- Fill in your column (suvarna_label). I'll fill in mine (jisnu_label) separately.
- Please don't look at my column until you're done. We need independent ratings for the paper.
- If you're not sure about one, just go with your best guess and leave a note in suvarna_notes.
- Use the exact type names from the table below (e.g., RETURN_VALUE, not "return value").

## Gap types

Our classifier uses a priority system. It checks the rules top to bottom and assigns the first one that matches. You should do the same: go through the list in order and pick the first rule that fits.

| Priority | Gap Type | What to look for |
|----------|----------|-----------------|
| 1 | EXCEPTION_HANDLING | Test uses `pytest.raises`, `assertRaises`, or `with self.assertRaises` |
| 2 | BOUNDARY_CONDITION | Test inputs include boundary values like 0, -1, sys.maxsize, float('inf'), float('-inf'), or empty containers like [], {{}}, "", b"" |
| 3 | STATE_TRANSITION | Test uses `@pytest.fixture` with `autouse=True`, or calls setUp/tearDown methods |
| 4 | NONE_NULL_HANDLING | Test inputs or assertions involve `None` or `float('nan')` |
| 5 | RETURN_VALUE | Test asserts on a return value using assertEqual, assert x == y, assertIs, etc. |
| 6 | TYPE_COERCION | Test passes a literal whose type doesn't match the parameter's type annotation |
| 7 | OTHER | Doesn't match any of the above |

## Reading the spreadsheet

- **test_source** has the full Python source of the test function. That's the main thing to read.
- Read the code, then pick the first matching gap type from the priority table above.

## Valid labels

Use one of these exactly:
- EXCEPTION_HANDLING
- BOUNDARY_CONDITION
- STATE_TRANSITION
- NONE_NULL_HANDLING
- RETURN_VALUE
- TYPE_COERCION
- OTHER

## Projects covered

{projects_str}

Once we're both done I'll run the agreement script and we can compare results. Should take about 15-20 minutes. Thanks!
"""
    out_path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Generate validation spreadsheet for two raters.")
    parser.add_argument("--n", type=int, default=15, help="Number of bugs to sample (default: 15)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing validation sheet")
    args = parser.parse_args()

    random.seed(args.seed)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    bugs = load_bugs_with_tests()
    if not bugs:
        print("No classified bugs found. Run pipeline/04_classify.py first.")
        sys.exit(1)

    sample = stratified_sample(bugs, args.n)
    projects = sorted(set(b["project"] for b in sample))

    csv_path = RESULTS_DIR / "validation_sheet.csv"
    answer_key_path = RESULTS_DIR / "validation_answer_key.csv"

    if csv_path.exists() and not args.force:
        print(f"ERROR: {csv_path} already exists. Use --force to overwrite.")
        print("  This safety check prevents accidental loss of human rater labels.")
        sys.exit(1)

    rows = generate_csv(sample, csv_path, answer_key_path)

    instructions_path = RESULTS_DIR / "validation_instructions.md"
    generate_instructions(instructions_path, len(sample), len(rows), projects)

    print(f"Validation sheet (blinded): {csv_path}")
    print(f"  {len(rows)} tests from {len(sample)} bugs across {len(projects)} projects")
    print(f"  Projects: {', '.join(projects)}")
    print(f"Answer key (DO NOT share with raters): {answer_key_path}")
    print(f"Instructions: {instructions_path}")
    print()
    print("Next steps:")
    print("  1. Open the CSV in Google Sheets (File > Import)")
    print("  2. Share with your teammate")
    print("  3. Each person fills in their label column independently")
    print("  4. Run: python3 pipeline/06c_compute_validation_agreement.py")


if __name__ == "__main__":
    main()
