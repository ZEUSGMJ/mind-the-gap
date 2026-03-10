#!/usr/bin/env bash
# pipeline/01_setup.sh
# Clones BugsInPy and validates project structure.
# Safe to re-run -- pulls latest if already cloned.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
RAW_DIR="$PROJECT_ROOT/data/raw"
BUGSINPY_DIR="$RAW_DIR/bugsinpy"

echo "==> Stage 1: BugsInPy Setup"

mkdir -p "$RAW_DIR"

if [ -d "$BUGSINPY_DIR/.git" ]; then
    echo "    BugsInPy already cloned. Pulling latest..."
    git -C "$BUGSINPY_DIR" pull --quiet
else
    echo "    Cloning BugsInPy..."
    git clone https://github.com/soarsmu/BugsInPy.git "$BUGSINPY_DIR" --quiet
fi

# Validate expected structure
if [ ! -d "$BUGSINPY_DIR/projects" ]; then
    echo "ERROR: BugsInPy clone is missing 'projects/' directory. Something went wrong." >&2
    exit 1
fi

PROJECT_COUNT=$(ls "$BUGSINPY_DIR/projects" | wc -l)
echo "    Found $PROJECT_COUNT projects in BugsInPy"

echo "==> Stage 1 complete. BugsInPy ready at: $BUGSINPY_DIR"
