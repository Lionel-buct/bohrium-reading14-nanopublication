---
name: nanopublication-evidence-forge
description: Convert scientific papers or case files into atomic, falsifiable nanopublications with minimal source evidence, page/paragraph locators, provenance metadata, validation findings and machine-readable result.json. Use for nanopublication generation, claim decomposition, evidence binding, source traceability, structured export and evidence-quality checks.
---

# Nanopublication Evidence Forge

## Purpose

Build a minimal, reusable Nanopublication workflow that:

1. reads the actual case input instead of guessing from a label;
2. decomposes conclusions into independently falsifiable assertions;
3. binds each assertion to the smallest sufficient source quote;
4. preserves page, block, character offsets and source identity;
5. exports a machine-readable `result.json` that contains every case-specific `output_contract` field.

The built-in examples are synthetic and illustrative. Never use them as official case answers.

## Use this Skill when

- A case asks for scientific claim extraction, assertion decomposition, evidence binding, source metadata or structured export.
- A PDF/DOCX/text paper must be converted into a dataset of verifiable knowledge units.
- An existing claim list must be checked for over-broad wording, missing evidence, direction errors or duplicate assertions.
- The evaluator supplies `/input/case.json` and `/input/task.md`.

## Non-negotiable rules

- Read `/input/case.json`, `/input/task.md` and every supplied source file before answering.
- Treat case labels, filenames and metadata as claims to verify against the supplied material.
- Never invent page numbers, quotations, results, author names, years, DOIs, scores or software state.
- Never put a whole paragraph into one assertion when it contains multiple independently testable facts.
- Never place a citation as evidence unless the quoted citation text actually supports the assertion.
- Keep association, causation, comparison and absence-of-evidence distinct.
- A claim with no locatable evidence must go to `unresolved`; it must not be reported as successful.
- Preserve the exact names and nesting of case-specific `output_contract` fields.
- The authoritative final deliverable is `/app/output/result.json`.

## Inputs and outputs

Runtime inputs:

- `/input/case.json`: case identifier, questions, materials and output contract.
- `/input/task.md`: task instructions.
- `/input/**`: PDFs, DOCX, text, figures or supplementary files declared by the case.

Runtime outputs:

- `/app/work/case_manifest.json`: parsed case and contract.
- `/app/work/source_units.jsonl`: searchable evidence units with stable locators.
- `/app/work/draft_result.json`: authored answer and nanopublication draft.
- `/app/work/validation.json`: mechanical validation report.
- `/app/output/result.json`: final structured deliverable.
- `/app/output/evidence_ledger.jsonl`: flattened evidence ledger.
- `/app/output/evidence_table.csv`: human-reviewable evidence table.

## Mandatory workflow

### 0. Probe runtime capabilities

```bash
SKILL_DIR="${SKILL_DIR:-/skills/weekly-skill}"
bash "$SKILL_DIR/runtime_probe.sh" --input-root /input --work /app/work --output /app/output --create-dirs
```

The probe is offline and reports Python, PDF text/render, OCR, DOCX and directory capabilities as JSON. Fix `blockers` before extraction. Treat `partial` capabilities as a requirement to use the documented fallback and preserve unresolved pages or files.

### 1. Prepare the case and evidence units

```bash
SKILL_DIR="${SKILL_DIR:-/skills/weekly-skill}"
PYTHON_BIN="$(command -v python3 || command -v python)"
"$PYTHON_BIN" "$SKILL_DIR/scripts/prepare_case.py" \
  --case /input/case.json \
  --input-root /input \
  --work /app/work \
  --render-empty-pages
```

Inspect:

```bash
sed -n '1,220p' /app/work/case_brief.md
sed -n '1,220p' /app/work/case_manifest.json
head -n 40 /app/work/source_units.jsonl
```

The script writes `source_units.jsonl`. Every unit contains `unit_id`, `source_id`, `page`, `block_index`, `char_start`, `char_end` and verbatim `text`. After validation, each evidence locator uses the unit's `unit_id` as `block_id`.

### 2. Handle OCR pages honestly

If `case_manifest.json` lists `ocr_required_for_some_pages`:

1. Inspect the rendered page image under `/app/work/rendered/`.
2. Use the runtime OCR tool or an available OCR command.
3. Save recognized text as UTF-8 at:

```text
/app/work/ocr/<source_id>/p0001.txt
```

4. Merge the OCR text:

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/merge_ocr.py" --work /app/work
```

If OCR is unavailable or unreliable, keep the affected pages in `unresolved` and set the final status to `partial` or `unable`.

### 3. Read the task and output contract

Use the actual `task.md`, `case.json`, `case_manifest.json` and `source_units.jsonl`.

- `output_contract` is authoritative.
- If it requires arbitrary fields, place them under `contract_fields` with their exact original names.
- If it supplies a JSON Schema, honor `required` and `properties`.
- Do not rename fields into a different vocabulary unless the contract explicitly requires it.
- Continue extracting nanopublications even when the case also asks a direct question.

### 4. Author `draft_result.json`

Start from `/app/work/draft_result.template.json` and write `/app/work/draft_result.json`.

Required draft shape:

```json
{
  "case_id": "exact case id",
  "status": "success",
  "status_reason": "What was completed and what remains uncertain.",
  "task_result": {
    "direct_answer": "Case-specific answer, if the task asks for one."
  },
  "nanopublications": [],
  "unresolved": [],
  "conflicts": [],
  "contract_fields": {},
  "change_log": [
    {"at": "ISO-8601 timestamp", "action": "drafted", "detail": "Evidence-bound draft."}
  ]
}
```

Use `status` values strictly:

- `success`: requested output is complete and all key claims have usable evidence.
- `partial`: some output exists but evidence, OCR, access, fields or coverage are incomplete.
- `unable`: the source cannot be accessed or interpreted enough to produce the requested result.
- `refused`: the request is outside the supplied material or cannot be answered without forbidden fabrication.

### 5. Build atomic assertions

Each `nanopublications[]` item must contain:

```json
{
  "assertion": {
    "text": "One independently falsifiable scientific claim.",
    "subject": {"name": "canonical subject", "type": "entity type"},
    "relation": "controlled vocabulary relation",
    "object": {"name": "canonical object", "type": "entity type"},
    "claim_type": "empirical",
    "polarity": "supports",
    "conditions": ["dose", "time", "population", "comparison"],
    "quantifiers": ["effect size", "sample size", "confidence interval"]
  },
  "evidence": [
    {
      "source_id": "src01",
      "page": 3,
      "quote": "Verbatim source quote copied from source_units.jsonl.",
      "relation_to_claim": "direct_support",
      "minimality": "minimal",
      "sufficiency_rationale": "Why this span alone supports the assertion."
    }
  ]
}
```

Use the controlled relations in `references/relation-vocabulary.json`.

Atomicity checklist:

- one subject-relation-object relation per assertion;
- preserve direction and sign;
- preserve conditions and scope;
- preserve modality (`may`, `can`, `is associated with`, `causes`);
- split conjunctions, contrasts and cause/effect chains when each part is independently testable;
- keep negative findings and “not reported” as explicit claims;
- do not convert correlation to causation;
- do not convert a sub-group result into a population-wide result;
- do not remove statistical qualifications.

### 6. Bind minimal evidence

For every evidence item:

- Copy `quote` verbatim from a `source_units.jsonl` `text` field.
- Prefer the smallest span that still supports the full assertion.
- Use `direct_support` for a quote that alone entails the claim.
- Use `indirect_support` when the quote supports the claim only together with another item.
- Use `context` for scope or methods, not as sole support for a result.
- Use `contradiction` when the source conflicts with the assertion.
- For claims spanning figures/tables and captions, provide multiple evidence items rather than inventing one merged quote.
- If two sources conflict, list the conflict in `conflicts`; do not silently choose one.

### 7. Validate mechanically

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/validate_nanopubs.py" \
  --draft /app/work/draft_result.json \
  --work /app/work \
  --strict
```

Fix every validation `errors[]` item and rerun. Warnings require human/agent review; do not silently delete them.

Validation checks include:

- controlled relation and claim type;
- subject/object/relation completeness;
- evidence quote locatability;
- page and block correction;
- atomicity-risk markers;
- evidence quote length;
- duplicate assertions;
- incomplete source metadata;
- dangling, unpublished or nonexistent source identifiers.

Mechanical checks do not prove scientific truth. Semantic review remains required.

The final schema version is `nanopublication-result/1.1`. `finalize_result.py` checks the case contract recursively, validates the internal schema, writes `artifact_manifest`, and records both `mechanical_checks_only` and `semantic_review_required`.
Package release is `1.1.1`; the result schema remains `nanopublication-result/1.1` for compatibility.

### 8. Finalize the contract-compliant result

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/finalize_result.py" \
  --draft /app/work/draft_result.json \
  --work /app/work \
  --out /app/output/result.json
```

The finalizer blocks stale drafts (changed after validation), checks `case_id`, checks every required `output_contract` field, writes the evidence ledger and downgrades an incomplete success to `partial`.

### 9. Final inspection

```bash
"$PYTHON_BIN" - <<'PY'
import json
p = "/app/output/result.json"
r = json.load(open(p, encoding="utf-8"))
print(json.dumps({
    "case_id": r.get("case_id"),
    "status": r.get("status"),
    "nanopublications": len(r.get("nanopublications", [])),
    "contract": r.get("contract_validation"),
    "errors": len(r.get("validation", {}).get("errors", [])),
    "warnings": len(r.get("validation", {}).get("warnings", []))
}, ensure_ascii=False, indent=2))
PY
```

Do not deliver a success claim if `contract_validation.status` is `failed`.

## Source metadata

Record only values present in the supplied material or case metadata:

- title, authors, year, journal, DOI;
- source path and SHA-256;
- page count and OCR-affected pages;
- case/source version if supplied;
- identifiers such as PMID, arXiv ID or dataset ID when present.

If a field is absent, keep it `null` and mention the limitation. Never fill missing metadata from memory.

## Required failure handling

- **No text layer:** render page, run OCR, merge text; otherwise mark the page unresolved.
- **No source access:** status `unable`; say which file or page failed.
- **Evidence not found:** do not fabricate a locator; mark the claim unresolved.
- **Conflicting evidence:** preserve both sources and add a conflict entry.
- **Figure/table evidence:** quote the caption and the relevant surrounding text; provide separate evidence items.
- **Missing output field:** add it to `unresolved` and let the finalizer downgrade status.
- **Unsupported answer format:** preserve the original contract; do not rewrite it silently.
- **Repeated runs:** reuse stable source IDs and dedupe keys; record changes in `change_log`.

## Quality gates

Before calling the result complete, verify:

- all required `output_contract` fields exist;
- every assertion is atomic enough to be independently judged;
- every reported result has at least one usable evidence item;
- every evidence quote occurs in the supplied source;
- page, block and character offsets resolve;
- all conditions and limitations survive extraction;
- source metadata is real or explicitly missing;
- unresolved items and conflicts are visible;
- output parses as UTF-8 JSON with no trailing explanation.

## References

- `references/field-dictionary.md`: field meanings and invariants.
- `references/assertion-rules.md`: decomposition, evidence and dedupe rules.
- `references/relation-vocabulary.json`: controlled relations.
- `references/output-schema.md`: final structure.
- `references/reliability.md`: exceptions and recovery.
- `references/evaluation-matrix.md`: how the workflow maps to the 100-point rubric.
- `references/verification-plan.md`: positive, negative and regression checks.
- `scripts/runtime_probe.py` and `runtime_probe.sh`: offline capability and directory readiness check.
- `GAIN.md`: what the workflow changes and how the gain can be verified without inventing scores.
- `MINIMAL_USAGE.md`: shortest executable workflow.
- `PREDICATES.md`: controlled relation usage.
- `MACHINE_VS_HUMAN.md`: deterministic checks versus semantic review.
- `EXAMPLES.md` and `FIELDS.md`: synthetic examples and compact field map.
- `examples/`: synthetic examples only; clearly not formal case answers.

## Minimal invocation

```bash
SKILL_DIR="${SKILL_DIR:-/skills/weekly-skill}"
PYTHON_BIN="$(command -v python3 || command -v python)"
bash "$SKILL_DIR/runtime_probe.sh" --create-dirs
"$PYTHON_BIN" "$SKILL_DIR/scripts/prepare_case.py" --case /input/case.json --input-root /input --work /app/work --render-empty-pages
# Author /app/work/draft_result.json from the actual sources.
"$PYTHON_BIN" "$SKILL_DIR/scripts/validate_nanopubs.py" --draft /app/work/draft_result.json --work /app/work --strict
"$PYTHON_BIN" "$SKILL_DIR/scripts/finalize_result.py" --draft /app/work/draft_result.json --work /app/work --out /app/output/result.json
```
