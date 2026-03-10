#!/usr/bin/env python3
"""
pipeline/02_extract.py

Stage 2: Regression Test Extraction

For each bug in BugsInPy, this script:
  1. Reads the bug metadata (fix commit, buggy commit, trigger test paths)
  2. Uses PyDriller to diff the fix commit against its parent
  3. Identifies test functions that are NEW in the fix commit (not present in parent)
  4. Extracts the full source of each new test function using the AST
  5. Writes one JSON file per bug to data/extracted/

Output: data/extracted/{project}_{bug_id}.json

Run:
    python3 pipeline/02_extract.py
    python3 pipeline/02_extract.py --bug pandas_1 --verbose
    python3 pipeline/02_extract.py --force   # re-process already extracted bugs
"""

import argparse
import ast
import json
import logging
import os
import sys
from pathlib import Path

from pydriller import Repository
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUGSINPY_DIR = PROJECT_ROOT / "data" / "raw" / "bugsinpy"
OUTPUT_DIR = PROJECT_ROOT / "data" / "extracted"

# ---------------------------------------------------------------------------
# Sampling: stratified across projects, target 100-150 bugs total
# Minimum 5 bugs per project where available.
# Adjust MAX_BUGS_PER_PROJECT and TOTAL_BUDGET as needed.
# ---------------------------------------------------------------------------

MAX_BUGS_PER_PROJECT = 15
TOTAL_BUDGET = 150

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def read_bugsinpy_metadata(bugsinpy_dir: Path) -> list[dict]:
    """
    Walk the BugsInPy projects directory and collect bug metadata.

    BugsInPy structure:
        projects/{project}/bugs/{bug_id}/bug.info
        projects/{project}/bugs/{bug_id}/run_test.sh  (contains trigger test paths)

    Returns a list of dicts with keys:
        project, bug_id, fix_commit, buggy_commit, trigger_test_paths, repo_url
    """
    bugs = []
    projects_dir = bugsinpy_dir / "projects"
    if not projects_dir.exists():
        log.error("BugsInPy projects directory not found: %s", projects_dir)
        sys.exit(1)

    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        project = project_dir.name
        bugs_dir = project_dir / "bugs"
        if not bugs_dir.exists():
            continue

        # Read repo URL from project-level project.info
        project_info_path = project_dir / "project.info"
        project_info = _parse_bug_info(project_info_path) if project_info_path.exists() else {}
        repo_url = project_info.get("github_url", "").strip().rstrip("/")

        count = 0
        for bug_dir in sorted(bugs_dir.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 0):
            if not bug_dir.is_dir():
                continue
            if count >= MAX_BUGS_PER_PROJECT:
                break

            bug_info_path = bug_dir / "bug.info"
            run_test_path = bug_dir / "run_test.sh"
            if not bug_info_path.exists():
                continue

            info = _parse_bug_info(bug_info_path)
            if not info:
                continue

            if run_test_path.exists():
                trigger_test_paths, trigger_func_names = _parse_run_test(run_test_path)
            else:
                trigger_test_paths, trigger_func_names = [], []

            # Also check bug.info for test_file field
            test_file_from_info = info.get("test_file", "").strip()
            if test_file_from_info and test_file_from_info not in trigger_test_paths:
                trigger_test_paths.append(test_file_from_info)

            bug_id = f"{project}_{bug_dir.name}"

            bugs.append({
                "bug_id": bug_id,
                "project": project,
                "fix_commit": info.get("fixed_commit_id", "").strip(),
                "buggy_commit": info.get("buggy_commit_id", "").strip(),
                "repo_url": repo_url,
                "trigger_test_paths": trigger_test_paths,
                "trigger_func_names": trigger_func_names,
            })
            count += 1

    return bugs


def _parse_bug_info(path: Path) -> dict:
    """Parse a BugsInPy bug.info file into a dict."""
    result = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip().strip('"')
    except Exception as e:
        log.warning("Could not parse %s: %s", path, e)
    return result


def _parse_run_test(path: Path) -> tuple[list[str], list[str]]:
    """Extract test file paths and specific test function names from run_test.sh.

    Returns (file_paths, function_names). function_names may include
    'ClassName::method' or just 'method'.
    """
    file_paths = []
    func_names = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("pytest") or line.startswith("python -m pytest"):
                parts = line.split()
                for part in parts[1:]:
                    if part.startswith("-"):
                        continue
                    if "::" in part:
                        segments = part.split("::")
                        file_paths.append(segments[0])
                        # Last segment is the function name
                        func_names.append(segments[-1])
                    elif part.endswith(".py"):
                        file_paths.append(part)
                    break
    except Exception as e:
        log.warning("Could not parse %s: %s", path, e)
    return list(set(file_paths)), list(set(func_names))


def extract_new_test_functions(
    repo_url: str, fix_commit: str,
    trigger_test_paths: list[str],
    trigger_func_names: list[str] | None = None,
) -> list[dict]:
    """
    Use PyDriller to find test functions added or modified in fix_commit.

    Extracts:
      1. Test functions that are NEW in the fix commit (not in parent)
      2. Test functions that are MODIFIED and match known trigger function names
      3. If neither yields results, all modified test functions in test files

    Returns a list of dicts with keys:
        test_file, test_function, test_source, is_new_in_fix_commit
    """
    results = []
    modified_fallbacks = []
    trigger_func_set = set(trigger_func_names or [])

    try:
        for commit in Repository(repo_url, single=fix_commit).traverse_commits():
            for modified_file in commit.modified_files:
                if modified_file.new_path is None:
                    continue
                if not _is_test_file(modified_file.new_path, trigger_test_paths):
                    continue

                source_after = modified_file.source_code or ""
                source_before = modified_file.source_code_before or ""

                funcs_after = _get_test_function_names(source_after)
                funcs_before = _get_test_function_names(source_before)
                new_funcs = funcs_after - funcs_before

                # 1. Brand new test functions
                for func_name in new_funcs:
                    func_source = _extract_function_source(source_after, func_name)
                    if func_source:
                        results.append({
                            "test_file": modified_file.new_path,
                            "test_function": func_name,
                            "test_source": func_source,
                            "is_new_in_fix_commit": True,
                        })

                # 2. Modified test functions matching trigger names
                existing_funcs = funcs_after & funcs_before
                for func_name in existing_funcs:
                    if func_name not in trigger_func_set:
                        continue
                    source_a = _extract_function_source(source_after, func_name)
                    source_b = _extract_function_source(source_before, func_name)
                    if source_a and source_a != source_b:
                        results.append({
                            "test_file": modified_file.new_path,
                            "test_function": func_name,
                            "test_source": source_a,
                            "is_new_in_fix_commit": False,
                        })

                # 3. Collect all modified existing test functions as fallback
                if not results:
                    for func_name in existing_funcs:
                        source_a = _extract_function_source(source_after, func_name)
                        source_b = _extract_function_source(source_before, func_name)
                        if source_a and source_a != source_b:
                            modified_fallbacks.append({
                                "test_file": modified_file.new_path,
                                "test_function": func_name,
                                "test_source": source_a,
                                "is_new_in_fix_commit": False,
                            })

    except Exception as e:
        log.warning("PyDriller error for %s @ %s: %s", repo_url, fix_commit, e)

    # Use fallbacks only if no new or named-trigger tests were found
    if not results and modified_fallbacks:
        results = modified_fallbacks

    return results


def _is_test_file(path: str, trigger_test_paths: list[str]) -> bool:
    """Return True if path looks like a test file or matches a known trigger path."""
    if any(path.endswith(tp) or tp in path for tp in trigger_test_paths if tp):
        return True
    filename = os.path.basename(path)
    return filename.startswith("test_") or filename.endswith("_test.py")


def _get_test_function_names(source: str) -> set[str]:
    """Return the set of top-level test function names in source."""
    names = set()
    if not source:
        return names
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
                names.add(node.name)
    except SyntaxError:
        pass
    return names


def _extract_function_source(source: str, func_name: str) -> str | None:
    """Extract the source code of a named function from a source string."""
    try:
        tree = ast.parse(source)
        lines = source.splitlines(keepends=True)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                start = node.lineno - 1
                end = node.end_lineno
                return "".join(lines[start:end])
    except Exception:
        pass
    return None


def process_bug(bug: dict, output_dir: Path, force: bool, verbose: bool) -> bool:
    """Process a single bug. Returns True if written, False if skipped."""
    out_path = output_dir / f"{bug['bug_id']}.json"
    if out_path.exists() and not force:
        if verbose:
            log.info("Skipping %s (already extracted)", bug["bug_id"])
        return False

    if verbose:
        log.info("Extracting %s ...", bug["bug_id"])

    trigger_tests = []
    if bug["repo_url"] and bug["fix_commit"]:
        trigger_tests = extract_new_test_functions(
            bug["repo_url"], bug["fix_commit"],
            bug["trigger_test_paths"],
            bug.get("trigger_func_names"),
        )

    result = {
        "bug_id": bug["bug_id"],
        "project": bug["project"],
        "fix_commit": bug["fix_commit"],
        "buggy_commit": bug["buggy_commit"],
        "repo_url": bug["repo_url"],
        "trigger_tests": trigger_tests,
    }

    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stage 2: Extract trigger tests from BugsInPy fix commits.")
    parser.add_argument("--bug", type=str, default=None, help="Process only this bug_id (e.g. pandas_1)")
    parser.add_argument("--projects", type=str, default=None, help="Comma-separated list of projects to process")
    parser.add_argument("--force", action="store_true", help="Re-process already extracted bugs")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not BUGSINPY_DIR.exists():
        log.error("BugsInPy not found at %s. Run pipeline/01_setup.sh first.", BUGSINPY_DIR)
        sys.exit(1)

    bugs = read_bugsinpy_metadata(BUGSINPY_DIR)
    log.info("Loaded %d bugs from BugsInPy (budget: %d)", len(bugs), TOTAL_BUDGET)

    # Apply sampling budget
    from collections import defaultdict
    by_project: dict[str, list] = defaultdict(list)
    for b in bugs:
        by_project[b["project"]].append(b)
    sampled = []
    for project_bugs in by_project.values():
        sampled.extend(project_bugs[:MAX_BUGS_PER_PROJECT])
    sampled = sampled[:TOTAL_BUDGET]
    log.info("Sampled %d bugs after stratification", len(sampled))

    if args.projects:
        project_set = set(args.projects.split(","))
        sampled = [b for b in sampled if b["project"] in project_set]
        log.info("Filtered to projects %s: %d bugs", project_set, len(sampled))

    if args.bug:
        sampled = [b for b in sampled if b["bug_id"] == args.bug]
        if not sampled:
            log.error("Bug '%s' not found in sampled set.", args.bug)
            sys.exit(1)

    written = 0
    skipped = 0
    for bug in tqdm(sampled, desc="Extracting", disable=args.verbose):
        if process_bug(bug, OUTPUT_DIR, force=args.force, verbose=args.verbose):
            written += 1
        else:
            skipped += 1

    log.info("Done. Written: %d, Skipped (already done): %d", written, skipped)


if __name__ == "__main__":
    main()
