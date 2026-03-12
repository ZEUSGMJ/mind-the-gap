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

## Figure Regeneration

The committed figure set in `data/results/figures/` is generated from
`notebooks/figures.ipynb`. After the main pipeline completes, rerun the
notebook to refresh the PDF and PNG figure files:

```bash
jupyter nbconvert --to notebook --execute notebooks/figures.ipynb --output-dir /tmp --output figures-rerun.ipynb
```

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

Two optional validation paths are supported:

- local Ollama models via `pipeline/04b_classify_ollama.py`
- the Anthropic API via `pipeline/04b_classify_anthropic.py`

See `docs/LLM_VALIDATION.md` for the tested Ollama setup, Docker option,
Anthropic API notes, model-selection guidance, and output details.

Quick examples:

```bash
python3 pipeline/04b_classify_ollama.py --model phi3:mini
```

```bash
export ANTHROPIC_API_KEY=your_key_here
python3 pipeline/04b_classify_anthropic.py
```

Notes:

- The final published kappa output is already committed in
  `data/results/cohens_kappa.json`.
- Local hardware, model availability, and API availability may affect how
  closely a rerun matches the original optional LLM pass.

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
