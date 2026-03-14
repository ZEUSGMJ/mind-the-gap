# Mind the Gap

Empirical characterization of semantic test gaps in Python projects using
regression tests from the BugsInPy dataset.

## Research Question

What types of semantic test scenarios were missing in Python projects, as
revealed by regression tests added during bug fixes, and how are these gaps
reflected in the structural characteristics of the added tests and
corresponding code fixes?

## What This Repository Contains

This repository is the clean, reproducible code and results package for the
project. It includes:

- the pipeline used to extract, measure, classify, and analyze regression tests
- the final aggregated result artifacts used in the report
- the figure files used in the paper and slides
- optional LLM second-pass scripts for classification accuracy validation

This repository does **not** include the raw BugsInPy clone or large
intermediate extraction/classification directories. Those are regenerated
locally after cloning.

## Quick Start

```bash
git clone <your-github-url> mind-the-gap-repro
cd mind-the-gap-repro
bash setup.sh
source venv/bin/activate
```

## Main Reproduction Workflow

The deterministic rule-based pipeline is the main workflow for reproducing the
study.

```bash
bash pipeline/01_setup.sh
python3 pipeline/02_extract.py
python3 pipeline/03_metrics.py
python3 pipeline/03b_fix_metrics.py
python3 pipeline/04_classify.py
python3 pipeline/05_analyze.py
```

`pipeline/04_classify.py` is deterministic only. Optional LLM agreement runs
are handled separately by the `pipeline/04b_*` scripts.

Expected headline outputs after the full run:

- `211` trigger tests
- `139` bugs with trigger tests
- `14` projects represented

The main generated artifacts are written to `data/results/`.

## Included Final Artifacts

This repository already includes the final result artifacts for immediate
inspection:

- `data/results/summary.txt`
- `data/results/classified_bugs.csv`
- `data/results/gap_type_distribution.json`
- `data/results/structural_metrics.json`
- `data/results/mann_whitney.json`
- `data/results/cohens_kappa.json` (LLM agreement/accuracy results; low kappa supports need for deterministic rules)
- `data/results/manual_validation.json`
- `data/results/figures/`

The committed figure set can be regenerated from `notebooks/figures.ipynb`
after running the main pipeline.

## Optional Reproduction Paths

The LLM second-pass agreement scripts are included, but they are **not** part
of the default rerun flow:

- `pipeline/04b_classify_ollama.py` for local Ollama models
- `pipeline/04b_classify_anthropic.py` for Anthropic API-based runs

These optional scripts install from `requirements.txt`, but still need their
runtime prerequisites:

- Ollama running locally for `pipeline/04b_classify_ollama.py`
- `ANTHROPIC_API_KEY` for `pipeline/04b_classify_anthropic.py`

The final LLM agreement output is already committed in `data/results/cohens_kappa.json`,
so rerunning the LLM pass is optional.

Manual validation agreement can also be recomputed from the committed
`data/results/validation_sheet.csv` using `pipeline/06c_compute_validation_agreement.py`.

## Documentation

- `CHEATSHEET.md`: quick command reference
- `docs/REPRODUCIBILITY.md`: detailed rerun instructions, optional LLM paths,
  and validation workflow
- `docs/REPORT_BRIEF.md`: methodology and results summary for the public repo
- `docs/LLM_VALIDATION.md`: local Ollama setup, Anthropic API notes, Docker
  option, and `llmfit` model-selection guidance
- `STATUS.md`: current result snapshot and repository status

## Dataset

This project uses [BugsInPy](https://github.com/soarsmu/BugsInPy), a benchmark
of real-world Python bugs with bug-fix commits and trigger tests.
