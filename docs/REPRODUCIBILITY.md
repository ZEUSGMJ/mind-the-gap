# Reproducibility Guide

This document describes how to rerun the pipeline from a fresh clone and how to
optionally reproduce the LLM second-pass validation.

## Environment Setup

```bash
git clone <your-github-url> mind-the-gap-repro
cd mind-the-gap-repro
bash setup.sh
source venv/bin/activate
```

## Main Deterministic Pipeline

This is the primary study workflow.

```bash
bash pipeline/01_setup.sh
python3 pipeline/02_extract.py
python3 pipeline/03_metrics.py
python3 pipeline/03b_fix_metrics.py
python3 pipeline/04_classify.py
python3 pipeline/05_analyze.py
```

Outputs are written to `data/results/`.

Expected headline counts:

- 211 trigger tests
- 139 bugs with trigger tests
- 14 projects

## Single-Bug Debugging

```bash
python3 pipeline/02_extract.py --bug pandas_1 --verbose
python3 pipeline/03_metrics.py --bug pandas_1 --verbose
python3 pipeline/03b_fix_metrics.py --bug pandas_1 --verbose
python3 pipeline/04_classify.py --bug pandas_1 --verbose
```

## Optional: Reproduce LLM Second-Pass Agreement

These scripts are optional. They are not required to regenerate the main study
artifacts.

### Local Ollama path

Prerequisites:

- Ollama running locally at `http://localhost:11434`
- Compatible model pulled locally, for example `phi3:mini`

Example:

```bash
python3 pipeline/04b_classify_ollama.py --model phi3:mini
```

### Anthropic API path

Prerequisites:

- `ANTHROPIC_API_KEY` exported in the environment

Example:

```bash
export ANTHROPIC_API_KEY=your_key_here
python3 pipeline/04b_classify_anthropic.py
```

Notes:

- Local hardware, available models, and API model availability may affect the
  ease of reproducing the exact LLM agreement workflow.
- The final published kappa output is already committed in
  `data/results/cohens_kappa.json`.

## Manual Validation Agreement

The committed validation CSV and final JSON are included in the repository.
Recompute agreement from the committed CSV with:

```bash
python3 pipeline/06c_compute_validation_agreement.py
```

If you separately edit `validation_sheet.xlsx`, sync it back into the CSV first:

```bash
python3 pipeline/06d_sync_validation_sheet.py
python3 pipeline/06c_compute_validation_agreement.py
```

## Included Final Artifacts

The repository already includes:

- `data/results/summary.txt`
- `data/results/classified_bugs.csv`
- `data/results/gap_type_distribution.json`
- `data/results/structural_metrics.json`
- `data/results/mann_whitney.json`
- `data/results/cohens_kappa.json`
- `data/results/manual_validation.json`
- `data/results/figures/`
