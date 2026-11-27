# Machine Checks vs Human Review

The pipeline deliberately separates deterministic checks from scientific judgment.

## Machine checks

`validate_nanopubs.py` can verify:

- quote presence and source ID existence;
- exact or whitespace-normalized quote location;
- page, block ID and character offsets;
- required assertion and evidence fields;
- controlled relation, claim type, polarity and evidence relation;
- duplicate dedupe keys;
- numeric fidelity between assertion and evidence;
- negation direction and basic causal-strength risk;
- comparison marker presence;
- scope and condition overlap;
- source metadata completeness;
- stale draft detection before finalization;
- the case-specific `output_contract` and internal `schemas/result.schema.json`.

These checks produce machine-readable `errors[]`, `warnings[]`, `quality_report` and `semantic_risk_counts`.

## Human or evaluator review

A human or evaluator must still decide:

- whether the subject and object are canonical and scientifically equivalent;
- whether the quote entails the entire assertion;
- whether the study design justifies a causal or comparative wording;
- whether a figure, table or OCR fragment was interpreted correctly;
- whether two sources genuinely conflict rather than measuring different constructs;
- whether the selected evidence is the smallest sufficient span.

These decisions cannot be proven by string matching. The final output therefore always keeps:

```json
{
  "mechanical_checks_only": true,
  "semantic_review_required": true
}
```

## Failure behavior

- Mechanical `errors` make the validation invalid and the final status at most `partial`.
- Strong warnings such as missing rationale, numeric loss, scope loss, negation reversal, missing comparator or duplicate claims also downgrade success to `partial`.
- Soft metadata warnings remain visible and do not get rewritten as facts.
- A missing source or unrecoverable OCR page goes to `unresolved` with a human action.
- A result is never labeled `success` merely because the JSON schema passes.
