# Mind the Gap: Repository Snapshot

**Last updated:** 2026-03-12 PT
**State:** Final analysis artifacts included, raw/intermediate data excluded from version control

---

## Pipeline Stages

| Stage | Script | Status | Output |
|-------|--------|--------|--------|
| 1. Setup | `pipeline/01_setup.sh` | DONE | `data/raw/bugsinpy/` (17 projects cloned) |
| 2. Extract | `pipeline/02_extract.py` | DONE | `data/extracted/*.json` (150 files, 139 with tests) |
| 3. Metrics | `pipeline/03_metrics.py` | DONE | Metrics added to classified JSONs |
| 3b. Fix Metrics | `pipeline/03b_fix_metrics.py` | DONE | fix_metrics added to all 150 classified JSONs |
| 4. Classify | `pipeline/04_classify.py` | DONE | `data/classified/*.json` (150 files) |
| 4b. Kappa (Ollama) | `pipeline/04b_classify_ollama.py` | DONE (phi3:mini only) | `data/results/cohens_kappa.json` |
| 4b. Kappa (Anthropic) | `pipeline/04b_classify_anthropic.py` | DONE | Haiku results merged into kappa JSON |
| 5. Analyze | `pipeline/05_analyze.py` | DONE | `data/results/summary.txt`, CSV, JSONs |
| 6. Figures | `notebooks/figures.ipynb` | DONE | `data/results/figures/` (6 figs, PDF+PNG) |

## Results Snapshot

- **211 tests**, **139 bugs**, **14 projects**
- Gap types: RETURN_VALUE 44.5%, BOUNDARY_CONDITION 28.4%, NONE_NULL_HANDLING 15.2%, EXCEPTION_HANDLING 7.1%, OTHER 4.7%
- No STATE_TRANSITION or TYPE_COERCION instances observed
- Cohen's kappa: phi3:mini = 0.2062 (40.8%), Claude Haiku = 0.2135 (47.9%)
- Manual validation agreement: Jisnu vs AST = 88.2% (kappa 0.7952), Suvarna vs AST = 70.6% (kappa 0.4551), Jisnu vs Suvarna = 70.6% (kappa 0.5115)
- Mann-Whitney U: significant differences found across LOC, assertion count, complexity, fixtures, and fix-side metrics (see summary.txt)
- Fix-side metrics (bug-level): None/Null bugs need largest fixes (median 9 LOC added), Exception bugs smallest (median 5)
- Fix-side Mann-Whitney now computed at bug level (deduplicated), 3 significant pairs

## Known Issues and Limitations

1. **Sampling is NOT random/stratified.** `02_extract.py` takes the first N bugs per project (up to 15). Paper must describe this accurately as a convenience sample.
2. **STATE_TRANSITION is structurally unobservable.** Classifier only sees extracted test function bodies, not surrounding class context or file-level fixtures. Note in Threats to Validity.
3. **BOUNDARY_CONDITION rule is broad.** Incidental literals (e.g., `insert(0, ...)`) can trigger classification. Acknowledge as heuristic limitation.
4. **Low kappa scores.** Both LLMs over-classify as RETURN_VALUE and do not reliably follow the priority ordering. This supports using deterministic AST rules, but should be discussed cautiously.
5. **11 bugs with empty trigger_tests:** ansible_3, ansible_9, luigi_2, luigi_3, scrapy_1/6/9/11/12/13/14

## Bugs Fixed During Development

- `02_extract.py`: repo_url read from wrong file (bug.info vs project.info)
- `02_extract.py`: trailing slash in httpie URL caused PyDriller error
- `02_extract.py`: originally only extracted NEW tests; fixed to also capture MODIFIED tests
- `03_metrics.py` + `04_classify.py`: indented class method source caused ast.parse failure; fixed with textwrap.dedent (79 tests were misclassified)
- `04_classify.py`: float('nan') was in boundary checker, removed (1 test affected, no distribution change)
- `05_analyze.py`: numpy bool not JSON serializable; wrapped with bool()
- `05_analyze.py`: kappa JSON format mismatch (old single-model vs new multi-model); fixed
- `05_analyze.py`: fix metrics were duplicated per test (bug-level metrics repeated for multi-test bugs); fixed to deduplicate to one row per bug for fix-metric stats and Mann-Whitney
- `06b_generate_validation_sheet.py`: validation sheet was not blinded (showed classifier answers); fixed to separate answer key from rater sheet

## Reproduction Notes

- The main reproducible workflow is the deterministic AST pipeline in `pipeline/01_setup.sh` through `pipeline/05_analyze.py`.
- `pipeline/04_classify.py` is deterministic only; LLM agreement runs live in `pipeline/04b_classify_ollama.py` and `pipeline/04b_classify_anthropic.py`.
- The LLM second-pass scripts are optional and are not required to regenerate the main study outputs.
- The optional LLM scripts install from `requirements.txt` but still require Ollama or `ANTHROPIC_API_KEY` at runtime.
- `data/results/` contains the final small artifacts needed for inspection without rerunning the entire study.

## File Locations

| What | Path |
|------|------|
| Pipeline scripts | `pipeline/01_setup.sh` through `pipeline/05_analyze.py` (includes `03b_fix_metrics.py`) |
| Validation scripts | `pipeline/06b_generate_validation_sheet.py`, `pipeline/06c_compute_validation_agreement.py`, `pipeline/06d_sync_validation_sheet.py` |
| Validation data | `data/results/validation_sheet.csv`, `validation_sheet.xlsx`, `validation_answer_key.csv`, `validation_instructions.md`, `manual_validation.json` |
| Methodology summary | `docs/REPORT_BRIEF.md` |
| Repro guide | `docs/REPRODUCIBILITY.md` |
| LLM validation note | `docs/LLM_VALIDATION.md` |
| Kappa scripts | `pipeline/04b_classify_ollama.py`, `pipeline/04b_classify_anthropic.py` |
| Results | `data/results/` (CSV, summary.txt, JSONs) |
| Figures | `data/results/figures/` (PDF + PNG) |
| Notebook | `notebooks/figures.ipynb` |
| API-based LLM rerun | `pipeline/04b_classify_anthropic.py` (requires `ANTHROPIC_API_KEY`) |
