# Mind the Gap: Report Brief

Use this file as the paper-facing source of truth for writing the final report.
It consolidates the methodology, current results, safe claims, and limitations
from the pipeline outputs and project docs.

## Project Summary

- Project: Mind the Gap
- Course: CS 563, Software Maintenance and Evolution, Oregon State University,
  Winter 2026
- Team: Jisnu Gujjalapudi, Suvarna Satvika Tiriveedhi
- Deadline: March 12, 2026, 10:00 AM PT

Canonical research question:

What types of semantic test scenarios were missing in Python projects, as
revealed by regression tests added during bug fixes, and how are these gaps
reflected in the structural characteristics of the added tests and corresponding
code fixes?

Do not reframe the project as "why developers do not write tests". That was
explicitly rejected by the professor.

## Methodology, Final Form

Dataset and sampling:

- Dataset: BugsInPy, 493 bugs from 17 Python projects.
- Actual sample used in this repo: convenience sample of the first `N` bugs per
  project, up to 15 per project, ordered by BugsInPy bug ID.
- Final processed sample: 150 bug records, 139 bugs with at least one trigger
  test, 211 trigger tests, 14 projects.
- Paper wording must say convenience sample, not stratified random sample.

Core pipeline:

1. `pipeline/02_extract.py`: extract added or modified trigger tests from fix
   commits.
2. `pipeline/03_metrics.py`: compute AST-derived test metrics.
3. `pipeline/03b_fix_metrics.py`: compute production-side fix metrics from
   non-test files in the fix commit.
4. `pipeline/04_classify.py`: assign one semantic gap type per test using
   priority-ordered deterministic rules.
5. `pipeline/04b_classify_ollama.py` and `pipeline/04b_classify_anthropic.py`:
   LLM second-pass raters for Cohen's kappa.
6. `pipeline/05_analyze.py`: aggregate results and compute Mann-Whitney U.

Classification scheme:

Apply the first matching rule only.

1. `EXCEPTION_HANDLING`
2. `BOUNDARY_CONDITION`
3. `STATE_TRANSITION`
4. `NONE_NULL_HANDLING`
5. `RETURN_VALUE`
6. `TYPE_COERCION`
7. `OTHER`

Important implementation detail:

- Test-side metrics and main gap distributions are computed at the test level.
- Fix-side metrics are computed at the bug level.
- For fix-side comparisons by gap type, `05_analyze.py` deduplicates to one row
  per bug and assigns each bug a single gap type using the modal gap type among
  its trigger tests.
- Mixed-gap bugs exist, so this bug-level assignment is a simplification and
  should be acknowledged in limitations if fix-side findings are emphasized.

## Final Numbers To Use

Overall counts:

- Trigger tests analyzed: 211
- Bugs with trigger tests: 139
- Projects represented: 14

Gap type distribution:

- `RETURN_VALUE`: 94 tests, 44.5%
- `BOUNDARY_CONDITION`: 60 tests, 28.4%
- `NONE_NULL_HANDLING`: 32 tests, 15.2%
- `EXCEPTION_HANDLING`: 15 tests, 7.1%
- `OTHER`: 10 tests, 4.7%
- `STATE_TRANSITION`: 0 observed
- `TYPE_COERCION`: 0 observed

Selected structural metrics, medians:

- `BOUNDARY_CONDITION`: LOC 11.5, assertions 1.5, complexity 2
- `EXCEPTION_HANDLING`: LOC 8, assertions 1, complexity 2
- `NONE_NULL_HANDLING`: LOC 6.5, assertions 1, complexity 1.5
- `RETURN_VALUE`: LOC 6, assertions 2, complexity 2
- `OTHER`: LOC 7.5, assertions 0, complexity 1

Fix-side metrics, bug-level medians:

- `NONE_NULL_HANDLING`: 9 LOC added, 3 LOC deleted, 1 file changed
- `BOUNDARY_CONDITION`: 7 LOC added, 3 LOC deleted, 1 file changed
- `EXCEPTION_HANDLING`: 5 LOC added, 1 LOC deleted, 2 files changed
- `OTHER`: 5.5 LOC added, 1 LOC deleted, 1 file changed
- `RETURN_VALUE`: 4 LOC added, 2 LOC deleted, 1 file changed

LLM agreement:

- `phi3:mini`: kappa 0.2062, agreement 40.8%, `n=211`
- `claude-haiku-4-5-20251001`: kappa 0.2135, agreement 47.9%, `n=211`

Manual validation agreement, completed in `validation_sheet.xlsx`:

- Jisnu vs AST classifier: agreement 88.2%, kappa 0.7952, `n=17`
- Suvarna vs AST classifier: agreement 70.6%, kappa 0.4551, `n=17`
- Jisnu vs Suvarna: agreement 70.6%, kappa 0.5115, `n=17`

Important status note:

- The workbook-based manual ratings have been synced into
  `validation_sheet.csv`.
- `data/results/manual_validation.json` has been generated and matches the
  agreement numbers listed above.

## Safe Findings To Write

These are supported directly by the current results:

- Most observed missing test scenarios fall into `RETURN_VALUE` and
  `BOUNDARY_CONDITION`.
- `NONE_NULL_HANDLING` is a smaller but still substantial category.
- `STATE_TRANSITION` and `TYPE_COERCION` were not observed in the analyzed
  sample.
- Boundary-condition tests are significantly longer than return-value tests
  (Mann-Whitney U, p < 0.05, after correcting the False==0 classifier bug).
- `OTHER` tests contain zero assertions by construction in the current rules.
- `NONE_NULL_HANDLING` is associated with larger production-side fixes than
  `RETURN_VALUE` in the current bug-level fix analysis.
- Independent LLM raters achieve low agreement with the AST classifier, which
  supports the need for strict priority-ordered deterministic rules.

Use caution with wording:

- Say "in this sample" or "in the analyzed BugsInPy subset", not "in Python
  projects generally".
- Say "associated with" or "reflected in", not causal language.
- Do not overclaim the absence of `STATE_TRANSITION` or `TYPE_COERCION` as
  evidence that such gaps do not occur in practice.

## Significant Statistical Results

Test-level Mann-Whitney U, `p < 0.05`:

- LOC:
  `BOUNDARY_CONDITION` vs `NONE_NULL_HANDLING`,
  `BOUNDARY_CONDITION` vs `RETURN_VALUE`
- Assertion count:
  `BOUNDARY_CONDITION` vs `OTHER`,
  `EXCEPTION_HANDLING` vs `OTHER`,
  `EXCEPTION_HANDLING` vs `RETURN_VALUE`,
  `NONE_NULL_HANDLING` vs `OTHER`,
  `OTHER` vs `RETURN_VALUE`
- Cyclomatic complexity:
  `BOUNDARY_CONDITION` vs `NONE_NULL_HANDLING`,
  `BOUNDARY_CONDITION` vs `OTHER`,
  `EXCEPTION_HANDLING` vs `NONE_NULL_HANDLING`,
  `EXCEPTION_HANDLING` vs `OTHER`,
  `NONE_NULL_HANDLING` vs `OTHER`,
  `NONE_NULL_HANDLING` vs `RETURN_VALUE`,
  `OTHER` vs `RETURN_VALUE`
- Fixture count:
  `BOUNDARY_CONDITION` vs `RETURN_VALUE`,
  `EXCEPTION_HANDLING` vs `NONE_NULL_HANDLING`,
  `EXCEPTION_HANDLING` vs `RETURN_VALUE`

Fix-side Mann-Whitney U, bug-level, `p < 0.05`:

- `fix_loc_added`: `NONE_NULL_HANDLING` vs `RETURN_VALUE`
- `fix_loc_deleted`: `BOUNDARY_CONDITION` vs `RETURN_VALUE`,
  `NONE_NULL_HANDLING` vs `OTHER`,
  `NONE_NULL_HANDLING` vs `RETURN_VALUE`

## Figures And How To Use Them

- Fig 1: `fig1_gap_type_distribution` for the headline distribution result.
- Fig 2: `fig2_loc_by_gap_type` for test-size differences.
- Fig 3: `fig3_assertions_by_gap_type` for assertion-count differences.
- Fig 4: `fig4_gap_type_by_project` for sample composition and cross-project
  distribution.
- Fig 5: `fig5_metrics_heatmap` for compact cross-metric comparison.
- Fig 6: `fig6_fix_loc_by_gap_type` for production-side fix-size differences.

Use the figure files from `data/results/figures/` and keep the naming
consistent between the paper and slide deck.

Important:

- The current `fig6_fix_loc_by_gap_type` has been regenerated from bug-level
  deduplicated fix metrics and is now aligned with the written analysis.

## Limitations And Threats To Validity

These should be stated explicitly in the report:

- Sampling is a convenience sample, not random.
- The classifier operates on extracted test-function bodies, so
  `STATE_TRANSITION` is structurally under-observable.
- The `BOUNDARY_CONDITION` heuristic is intentionally broad, so incidental
  literals such as positional `0` can trigger the rule. A bug where Python's
  `False == 0` caused boolean literals to match as boundary values was
  discovered during manual validation and corrected before final analysis.
- LLM second-pass agreement is low, which reflects the difficulty of following
  the taxonomy from natural-language rules alone.
- Fix-side analysis uses a single bug label derived from the modal gap type
  among a bug's trigger tests. Mixed-gap bugs therefore compress multiple test
  categories into one bug-level label.
- The manual validation sheet currently validates sampled extracted tests, not
  the full extraction recall of bugs with empty `trigger_tests`.

## Public Repo Note

- This file is included as a writing and interpretation reference for the
  final methodology and results.
- The source of truth for reproducible numeric outputs remains the JSON, CSV,
  and figure artifacts in `data/results/`.

## Source Files To Cite While Writing

- Current project status:
  `STATUS.md`
- Repro guide:
  `docs/REPRODUCIBILITY.md`
- Analysis summary:
  `data/results/summary.txt`
- Detailed metric tables:
  `data/results/structural_metrics.json`
- Statistical tests:
  `data/results/mann_whitney.json`
- Kappa results:
  `data/results/cohens_kappa.json`
- Manual validation workflow:
  `data/results/validation_instructions.md`
- Figures:
  `data/results/figures/`

If any prose summary conflicts with this file, verify against the result
artifacts above before writing.
