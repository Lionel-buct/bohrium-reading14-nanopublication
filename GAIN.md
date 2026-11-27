# Measurable Gain

This document describes what the Skill changes in the workflow and how those changes can be verified. It does not claim a benchmark score, a hidden-case result, or a comparison number that was not produced by the platform.

## Quality gain

The pipeline adds four enforceable gates before a result is called `success`:

1. Each nanopublication must contain an assertion with a subject, relation, object, claim type, polarity, conditions and quantifiers.
2. Each result-bearing assertion must have a locatable evidence item with a source ID, page, block ID, character offsets and a sufficiency rationale.
3. Numbers, negation, comparison baselines, scope markers and causal strength are checked against the bound evidence.
4. A case-specific `output_contract` is recursively checked against the final JSON.

The expected gain over a free-form summary is that a downstream reader can inspect the exact source span for every reported result. The actual quality gain is measured by the platform's fixed cases and baseline comparison, not by this document.

## Efficiency gain

The repeatable path is:

```text
input -> source registry -> evidence units -> candidate spans -> draft -> validation -> final result
```

`prepare_case.py` performs source extraction, page/block registration, candidate ranking and contract scaffolding in one run. `validate_nanopubs.py` then locates quotes and fills stable locators automatically. `finalize_result.py` writes the final JSON and review artifacts in one run.

## Gain verification

Reviewers can verify the mechanism with:

- `scripts/smoke_test.py`: positive and negative end-to-end behavior.
- `scripts/regression_test.py`: contract, semantic-risk and material-discovery regressions.
- `validation.json`: exact evidence rate, quantity preservation, rationale coverage and risk warning codes.
- `evidence_ledger.jsonl` and `evidence_table.csv`: flattened evidence rows.
- `sources.json`: source paths, hashes, page counts and OCR pages.
- `case_manifest.json`: parsed contract, materials and unresolved inputs.

The comparison itself remains a platform responsibility. This repository does not fabricate a baseline agent result or whiteboard.

## Scope boundary

The Skill improves structured extraction and mechanical review. It does not establish scientific truth by itself. Domain semantics, relationship correctness and evidence sufficiency still require human or evaluator review. That boundary is recorded in `quality_report.semantic_review_required` and `MACHINE_VS_HUMAN.md`.
