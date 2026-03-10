# Quick Reference: Mind the Gap

## Environment

```bash
source venv/bin/activate
```

## Full Pipeline

```bash
bash pipeline/01_setup.sh               # Clone BugsInPy, verify structure
python3 pipeline/02_extract.py          # Extract trigger tests from fix commits
python3 pipeline/03_metrics.py          # Compute AST structural metrics
python3 pipeline/03b_fix_metrics.py     # Compute production-side fix metrics
python3 pipeline/04_classify.py         # Classify gap types (priority-ordered rules)
python3 pipeline/05_analyze.py          # Stats: distribution, Mann-Whitney U, kappa
```

## Debug Single Bug

```bash
python3 pipeline/02_extract.py --bug pandas_1 --verbose
python3 pipeline/03_metrics.py --bug pandas_1 --verbose
python3 pipeline/03b_fix_metrics.py --bug pandas_1 --verbose
python3 pipeline/04_classify.py --bug pandas_1 --verbose
```

## Force Re-run (Skip Idempotency Check)

```bash
python3 pipeline/02_extract.py --force
python3 pipeline/03_metrics.py --force
python3 pipeline/03b_fix_metrics.py --force
python3 pipeline/04_classify.py --force
```

## Status Checks

```bash
ls data/extracted/ | wc -l             # How many bugs extracted
ls data/classified/ | wc -l            # How many bugs classified
grep -rl '"trigger_tests": \[\]' data/extracted/   # Bugs with no trigger tests found
cat data/results/summary.txt           # Analysis summary
```

## Optional LLM Validation

```bash
python3 pipeline/04b_classify_ollama.py --model phi3:mini
python3 pipeline/04b_classify_anthropic.py
```

## Notebooks

```bash
jupyter notebook notebooks/figures.ipynb
```

## Data Locations

| Stage | Directory |
|-------|-----------|
| BugsInPy clone | `data/raw/bugsinpy/` |
| Final flat CSV | `data/results/classified_bugs.csv` |
| Analysis summary | `data/results/summary.txt` |
| Figures | `data/results/figures/` |
| Repro details | `docs/REPRODUCIBILITY.md` |
