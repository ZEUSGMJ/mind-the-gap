#!/usr/bin/env python3
"""
pipeline/03b_fix_metrics.py

Stage 3b: Fix-Side Metrics Extraction

For each bug in data/classified/, uses PyDriller to analyze the fix commit
and extract metrics about the code fix (non-test files only).

Clones each project repo once to a temp directory, then analyzes all bugs
for that project from the local clone.

Metrics computed per bug:
    - fix_loc_added: lines added in non-test files
    - fix_loc_deleted: lines deleted in non-test files
    - fix_files_changed: number of non-test files modified
    - fix_total_files: total files modified (including test files)
    - fix_test_only: True if the fix only modified test files

Output: updates data/classified/{bug_id}.json in-place with fix_metrics key

Run:
    python3 pipeline/03b_fix_metrics.py
    python3 pipeline/03b_fix_metrics.py --bug pandas_1 --verbose
    python3 pipeline/03b_fix_metrics.py --force
"""

import argparse
import json
import logging
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from pydriller import Repository
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLASSIFIED_DIR = PROJECT_ROOT / "data" / "classified"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _is_test_file(path: str) -> bool:
    """Heuristic: file is a test file if its path contains 'test'."""
    if not path:
        return False
    parts = path.lower().split("/")
    basename = parts[-1]
    return (
        basename.startswith("test_")
        or basename.endswith("_test.py")
        or "tests" in parts
        or "test" in parts
    )


def clone_repo(repo_url: str, dest: Path) -> bool:
    """Clone a repo to dest. Returns True on success."""
    try:
        subprocess.run(
            ["git", "clone", "--bare", repo_url, str(dest)],
            capture_output=True, timeout=300, check=True,
        )
        return True
    except Exception as e:
        log.warning("Clone failed for %s: %s", repo_url, e)
        return False


def extract_fix_metrics(local_repo: str, fix_commit: str) -> dict:
    """Analyze the fix commit from a local repo and return fix-side metrics."""
    metrics = {
        "fix_loc_added": 0,
        "fix_loc_deleted": 0,
        "fix_files_changed": 0,
        "fix_total_files": 0,
        "fix_test_only": True,
    }

    try:
        for commit in Repository(local_repo, single=fix_commit).traverse_commits():
            metrics["fix_total_files"] = len(commit.modified_files)
            for mf in commit.modified_files:
                path = mf.new_path or mf.old_path or ""
                is_test = _is_test_file(path)
                if not is_test:
                    metrics["fix_loc_added"] += mf.added_lines
                    metrics["fix_loc_deleted"] += mf.deleted_lines
                    metrics["fix_files_changed"] += 1
                    metrics["fix_test_only"] = False
    except Exception as e:
        log.warning("PyDriller error for commit %s: %s", fix_commit, e)

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Stage 3b: Extract fix-side metrics.")
    parser.add_argument("--bug", type=str, default=None, help="Process only this bug_id")
    parser.add_argument("--force", action="store_true", help="Re-process already computed bugs")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    paths = sorted(CLASSIFIED_DIR.glob("*.json"))
    if not paths:
        log.error("No classified bugs found in %s", CLASSIFIED_DIR)
        sys.exit(1)

    if args.bug:
        paths = [p for p in paths if p.stem == args.bug]
        if not paths:
            log.error("Bug '%s' not found.", args.bug)
            sys.exit(1)

    # Group bugs by repo_url so we clone each repo only once
    bugs_by_repo = defaultdict(list)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if data.get("fix_metrics") and not args.force:
            continue

        repo_url = data.get("repo_url", "").strip()
        fix_commit = data.get("fix_commit", "").strip()
        if repo_url and fix_commit:
            bugs_by_repo[repo_url].append((path, data, fix_commit))

    total_bugs = sum(len(v) for v in bugs_by_repo.values())
    if not total_bugs:
        log.info("All bugs already have fix_metrics. Use --force to recompute.")
        return

    log.info("Processing %d bugs across %d repos", total_bugs, len(bugs_by_repo))

    written = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        for repo_url, bug_list in bugs_by_repo.items():
            repo_name = repo_url.rstrip("/").split("/")[-1]
            local_repo = Path(tmpdir) / repo_name

            log.info("Cloning %s (%d bugs)...", repo_name, len(bug_list))
            if not clone_repo(repo_url, local_repo):
                log.warning("Skipping all bugs for %s", repo_name)
                continue

            for path, data, fix_commit in tqdm(bug_list, desc=repo_name, disable=args.verbose):
                metrics = extract_fix_metrics(str(local_repo), fix_commit)
                data["fix_metrics"] = metrics

                if args.verbose:
                    log.info("%s: %s", data["bug_id"], metrics)

                path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                written += 1

            # Remove clone to free disk space
            shutil.rmtree(local_repo, ignore_errors=True)

    log.info("Done. Written: %d", written)


if __name__ == "__main__":
    main()
