# Examples

All examples in this directory are synthetic. They are not formal case results, hidden answers, or benchmark evidence.

## Files

| File | Purpose |
|---|---|
| `demo_case.json` | Minimal case and `output_contract` shape |
| `demo_source.txt` | Synthetic source with 20 sentence-like statements |
| `assertion-samples.json` | 20 assertions showing atomicity, conditions and evidence shape |
| `illustrative-output.json` | Two-claim result showing final field organization |

## How to use them

1. Run `scripts/smoke_test.py` to confirm the positive and negative paths.
2. Read `demo_source.txt` and compare it with `assertion-samples.json`.
3. Inspect `illustrative-output.json` for field names, locator shape and review metadata.
4. Run the pipeline on the actual `/input` materials. Do not copy synthetic text into an official result.

## Minimal falsification drill

For a synthetic sentence such as:

```text
Treatment X reduced biomarker Y relative to vehicle after 24 h.
```

The evidence-bound assertion should preserve:

- subject: `Treatment X`;
- direction: `reduces`;
- object: `biomarker Y`;
- comparator: `vehicle`;
- time: `after 24 h`;
- claim type: `empirical`;
- quote and locator: exactly the source sentence.

Changing any of those elements, or replacing the quote with a paper title, should make the assertion unresolved or fail validation.

## Example quality gate

The illustrative output is intentionally marked `illustrative: true`. A valid formal result is produced only by `finalize_result.py` from a case-specific draft, with `contract_validation.status = passed` and `schema_validation.status = passed`.
