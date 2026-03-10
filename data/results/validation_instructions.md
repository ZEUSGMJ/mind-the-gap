# Manual Validation Instructions

Hey Suvarna, I put together this spreadsheet so we can both validate the classifier's output independently. There are 17 test functions from 15 sampled bugs across 14 projects in our dataset.

What you need to do: read each test's source code and decide which gap type it belongs to, using the rules below.

## Before you start

- Fill in your column (suvarna_label). I'll fill in mine (jisnu_label) separately.
- Please don't look at my column until you're done. We need independent ratings for the paper.
- If you're not sure about one, just go with your best guess and leave a note in suvarna_notes.
- Use the exact type names from the table below (e.g., RETURN_VALUE, not "return value").

## Gap types

Our classifier uses a priority system. It checks the rules top to bottom and assigns the first one that matches. You should do the same: go through the list in order and pick the first rule that fits.

| Priority | Gap Type | What to look for |
|----------|----------|-----------------|
| 1 | EXCEPTION_HANDLING | Test uses `pytest.raises`, `assertRaises`, or `with self.assertRaises` |
| 2 | BOUNDARY_CONDITION | Test inputs include boundary values like 0, -1, sys.maxsize, float('inf'), float('-inf'), or empty containers like [], {}, "", b"" |
| 3 | STATE_TRANSITION | Test uses `@pytest.fixture` with `autouse=True`, or calls setUp/tearDown methods |
| 4 | NONE_NULL_HANDLING | Test inputs or assertions involve `None` or `float('nan')` |
| 5 | RETURN_VALUE | Test asserts on a return value using assertEqual, assert x == y, assertIs, etc. |
| 6 | TYPE_COERCION | Test passes a literal whose type doesn't match the parameter's type annotation |
| 7 | OTHER | Doesn't match any of the above |

## Reading the spreadsheet

- **test_source** has the full Python source of the test function. That's the main thing to read.
- Read the code, then pick the first matching gap type from the priority table above.

## Valid labels

Use one of these exactly:
- EXCEPTION_HANDLING
- BOUNDARY_CONDITION
- STATE_TRANSITION
- NONE_NULL_HANDLING
- RETURN_VALUE
- TYPE_COERCION
- OTHER

## Projects covered

PySnooper, ansible, black, cookiecutter, fastapi, httpie, keras, luigi, matplotlib, pandas, sanic, scrapy, spacy, thefuck

Once we're both done I'll run the agreement script and we can compare results. Should take about 15-20 minutes. Thanks!
