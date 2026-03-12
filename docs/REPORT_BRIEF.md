# Mind the Gap: Methodology and Results Summary

This document summarizes the public-facing methodology, headline results, and
limitations for the reproducibility package.

## Research Question

What types of semantic test scenarios were missing in Python projects, as
revealed by regression tests added during bug fixes, and how are these gaps
reflected in the structural characteristics of the added tests and
corresponding code fixes?

## Dataset and Sampling

- Dataset: BugsInPy, 493 bugs across 17 Python projects
- Sample used in this repo: convenience sample of the first BugsInPy bug IDs,
  capped at 15 bugs per project
- Final processed sample: 150 bug records, 139 bugs with at least one trigger
  test, 211 trigger tests, 14 projects

This sample is not random or stratified, so findings should be interpreted as
results from the analyzed BugsInPy subset rather than the Python ecosystem as a
whole.

## Main Pipeline

The core deterministic pipeline is:

1. `pipeline/02_extract.py`: extract added or modified trigger tests from fix
   commits
2. `pipeline/03_metrics.py`: compute AST-derived test metrics
3. `pipeline/03b_fix_metrics.py`: compute production-side fix metrics from
   non-test files in the same bug-fix commit
4. `pipeline/04_classify.py`: assign one semantic gap type per test using
   priority-ordered deterministic rules
5. `pipeline/05_analyze.py`: aggregate outputs and compute summary statistics

Optional LLM second-pass scripts are included for Cohen's kappa validation:

- `pipeline/04b_classify_ollama.py`
- `pipeline/04b_classify_anthropic.py`

## Classification Scheme

Each trigger test receives exactly one primary gap type. The first matching rule
wins:

1. `EXCEPTION_HANDLING`
2. `BOUNDARY_CONDITION`
3. `STATE_TRANSITION`
4. `NONE_NULL_HANDLING`
5. `RETURN_VALUE`
6. `TYPE_COERCION`
7. `OTHER`

Test-side metrics and gap distributions are analyzed at the test level. Fix-side
metrics are analyzed at the bug level after deduplicating to one row per bug and
assigning each bug a modal gap type.

## Headline Results

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

Selected structural medians:

- `BOUNDARY_CONDITION`: LOC 11.5, assertions 1.5, complexity 2
- `EXCEPTION_HANDLING`: LOC 8, assertions 1, complexity 2
- `NONE_NULL_HANDLING`: LOC 6.5, assertions 1, complexity 1.5
- `RETURN_VALUE`: LOC 6, assertions 2, complexity 2
- `OTHER`: LOC 7.5, assertions 0, complexity 1

Fix-side bug-level medians:

- `NONE_NULL_HANDLING`: 9 LOC added, 3 LOC deleted, 1 file changed
- `BOUNDARY_CONDITION`: 7 LOC added, 3 LOC deleted, 1 file changed
- `EXCEPTION_HANDLING`: 5 LOC added, 1 LOC deleted, 2 files changed
- `OTHER`: 5.5 LOC added, 1 LOC deleted, 1 file changed
- `RETURN_VALUE`: 4 LOC added, 2 LOC deleted, 1 file changed

LLM agreement:

- `phi3:mini`: kappa 0.2062, agreement 40.8%, `n=211`
- `claude-haiku-4-5-20251001`: kappa 0.2135, agreement 47.9%, `n=211`

Manual validation agreement:

- Jisnu vs AST classifier: agreement 88.2%, kappa 0.7952, `n=17`
- Suvarna vs AST classifier: agreement 70.6%, kappa 0.4551, `n=17`
- Jisnu vs Suvarna: agreement 70.6%, kappa 0.5115, `n=17`

## Interpretation Notes

The current results support the following high-level takeaways:

- Most observed missing test scenarios in this sample fall into
  `RETURN_VALUE` and `BOUNDARY_CONDITION`.
- `NONE_NULL_HANDLING` is smaller but still substantial.
- Boundary-condition tests are significantly longer than return-value tests.
- `NONE_NULL_HANDLING` is associated with larger production-side fixes than
  `RETURN_VALUE` in the bug-level fix analysis.
- Independent LLM raters achieve low agreement with the AST classifier, which
  supports the value of deterministic priority-ordered rules.

Use sample-bounded wording when discussing these results: for example, “in this
sample” or “in the analyzed BugsInPy subset,” rather than general claims about
all Python projects.

## Limitations

- Sampling is a convenience sample, not a random sample.
- The classifier operates on extracted test-function bodies, so
  `STATE_TRANSITION` is structurally under-observable.
- The `BOUNDARY_CONDITION` heuristic is intentionally broad, so incidental
  literals can trigger the rule.
- A classifier edge case caused by Python's `False == 0` behavior was corrected
  before the final analysis.
- Fix-side analysis assigns a single modal bug label to mixed-gap bugs, which
  compresses multiple test categories into one bug-level label.
- LLM agreement is low, so the second-pass validation should be read as a
  comparison against the deterministic rules, not as an alternative ground
  truth.

## Result Artifacts

For reproducible outputs, use the committed artifacts in `data/results/`:

- `data/results/summary.txt`
- `data/results/structural_metrics.json`
- `data/results/mann_whitney.json`
- `data/results/cohens_kappa.json`
- `data/results/manual_validation.json`
- `data/results/figures/`
