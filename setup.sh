#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "==> Setting up Mind the Gap environment"

# Create venv if not present
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "    Created venv"
fi

source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "    Dependencies installed"

# Create data directories
mkdir -p data/raw data/extracted data/classified data/results/figures
echo "    Data directories ready"

echo "==> Setup complete. Run: source venv/bin/activate"
