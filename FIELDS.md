# Fields

The authoritative machine schema is `schemas/result.schema.json` (`nanopublication-result/1.1`). This page is the compact field map.

## Root result

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `schema_version` | string | yes | `nanopublication-result/1.1` |
| `case_id` | string or number | yes | Exact input identifier; type is preserved |
| `status` | enum | yes | `success`, `partial`, `unable`, `refused` |
| `status_reason` | string | yes | Completion and limitation explanation |
| `task_result` | object | yes | Direct answer or structured task result |
| `nanopublications` | array | yes | Atomic assertions with evidence and lineage |
| `sources` | array | yes | Actual source registry and metadata |
| `unresolved` | array | yes | Missing, inaccessible or ambiguous items |
| `conflicts` | array | yes | Source or assertion conflicts |
| `quality_report` | object | yes | Mechanical validation statistics |
| `validation` | object | yes | Errors, warnings, duplicates and draft hash |
| `contract_validation` | object | yes | Case `output_contract` check |
| `input` | object | yes | Case path, task path, hashes and materials |
| `output_contract` | any | yes | Original contract, unmodified |
| `change_log` | array | yes | Actual run and revision history |
| `generated_at` | string | yes | UTC ISO-8601 timestamp |
| `artifact_manifest` | object | yes | Output paths, schema hash and evidence count |
| `schema_validation` | object | no | Internal schema check result |

Case-specific required fields are promoted from `draft_result.contract_fields` to the root with their original names. Reserved result fields cannot be overwritten by contract fields.

## Nanopublication

| Field | Required | Meaning |
|---|---:|---|
| `nanopub_id` | yes | Stable claim identifier |
| `assertion` | yes | One independently falsifiable claim |
| `evidence` | yes | One or more locatable evidence items |
| `sources` | yes | Source metadata used by the claim |
| `confidence` | yes | `score` plus at least one `basis` item |
| `lineage` | yes | Parent, supersedes, duplicate and dedupe key |
| `validation` | yes | Per-claim errors, warnings and exact-match flag |

## Assertion and evidence

Assertion requires `text`, `subject`, `relation`, `object`, `claim_type`, `polarity`, `conditions` and `quantifiers`. Evidence requires `evidence_id`, `source_id`, `page`, `block_id`, `char_start`, `char_end`, `quote`, `relation_to_claim`, `minimality`, `match`, `sufficiency_rationale` and `locator`.

A quote must occur in the supplied source. A locator must point to the same source and page. A direct-support rationale must explain why the quote alone is sufficient. The complete definitions and accepted enums are in `references/field-dictionary.md`.
