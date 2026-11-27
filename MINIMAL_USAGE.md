# Minimal Usage

This is the shortest supported invocation. It is a workflow example, not a formal case answer.

## Runtime inputs

```text
/input/case.json
/input/task.md
/input/<declared paper and supporting files>
```

## Commands

```bash
SKILL_DIR="${SKILL_DIR:-/skills/weekly-skill}"
PYTHON_BIN="$(command -v python3 || command -v python)"

bash "$SKILL_DIR/runtime_probe.sh" --create-dirs

"$PYTHON_BIN" "$SKILL_DIR/scripts/prepare_case.py" \
  --case /input/case.json \
  --input-root /input \
  --work /app/work \
  --render-empty-pages
```

Read the generated `case_brief.md`, `case_manifest.json`, `source_units.jsonl` and `claim_worksheet.md`. Put the actual answer and evidence-bound nanopublications in `/app/work/draft_result.json`.

If a page has no text layer, follow `references/reliability.md`, place OCR text under `/app/work/ocr/<source_id>/p0001.txt`, and run:

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/merge_ocr.py" --work /app/work
```

Validate and finalize:

```bash
"$PYTHON_BIN" "$SKILL_DIR/scripts/validate_nanopubs.py" \
  --draft /app/work/draft_result.json \
  --work /app/work \
  --strict

"$PYTHON_BIN" "$SKILL_DIR/scripts/finalize_result.py" \
  --draft /app/work/draft_result.json \
  --work /app/work \
  --out /app/output/result.json
```

## Expected output

```text
/app/output/result.json
/app/output/evidence_ledger.jsonl
/app/output/evidence_table.csv
/app/output/result_summary.md
```

`result.json` retains the input `case_id` without changing its JSON type and contains every required `output_contract` field. Validation warnings are not hidden: strong risks downgrade the result to `partial`.

## Synthetic example

`examples/demo_case.json` and `examples/illustrative-output.json` show the field shape. Both are synthetic and must not be submitted as an official answer. Run the package checks with:

```bash
"$PYTHON_BIN" scripts/smoke_test.py
"$PYTHON_BIN" scripts/regression_test.py
"$PYTHON_BIN" scripts/check_submission.py
```
