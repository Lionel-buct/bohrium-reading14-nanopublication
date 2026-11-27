#!/usr/bin/env python3
"""Merge a validated draft with the case contract and enforce final quality gates."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from nanopub_common import compact_text, load_json, sha256_file, utc_now, write_json, write_jsonl
from nanopub_contract import (
    contract_checklist,
    contract_issues,
    contract_required_fields,
)


SCHEMA_VERSION = "nanopublication-result/1.1"
PRESERVED_RESULT_FIELDS = {
    "schema_version",
    "case_id",
    "status",
    "status_reason",
    "task_result",
    "nanopublications",
    "sources",
    "unresolved",
    "conflicts",
    "quality_report",
    "validation",
    "contract_validation",
    "input",
    "output_contract",
    "change_log",
    "generated_at",
    "artifact_manifest",
    "schema_validation",
}
STRONG_PARTIAL_WARNINGS = {
    "assertion_too_long",
    "causal_strength_needs_review",
    "duplicate_claims",
    "evidence_not_minimal",
    "fuzzy_evidence_match",
    "incomplete_source_metadata",
    "metadata_not_verbatim_in_source",
    "missing_sufficiency_rationale",
    "missing_comparator",
    "negation_scope_risk",
    "numeric_fidelity_risk",
    "possible_compound_claim",
    "scope_not_preserved",
    "subject_object_low_overlap",
    "unsupported_negation",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, help="Completed draft_result.json")
    parser.add_argument("--validation", default=None, help="validation.json from validate_nanopubs.py")
    parser.add_argument("--work", default="/app/work", help="Directory from prepare_case.py")
    parser.add_argument("--out", default="/app/output/result.json", help="Final result JSON")
    parser.add_argument(
        "--allow-stale-validation",
        action="store_true",
        help="Debug only: allow finalization when the draft changed after validation.",
    )
    return parser.parse_args()


def evidence_rows(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for claim in claims:
        assertion = claim.get("assertion") if isinstance(claim.get("assertion"), dict) else {}
        for evidence in claim.get("evidence", []):
            if not isinstance(evidence, dict):
                continue
            rows.append(
                {
                    "nanopub_id": claim.get("nanopub_id"),
                    "claim": assertion.get("text"),
                    "subject": assertion.get("subject"),
                    "relation": assertion.get("relation"),
                    "object": assertion.get("object"),
                    "evidence_id": evidence.get("evidence_id"),
                    "source_id": evidence.get("source_id"),
                    "page": evidence.get("page"),
                    "block_id": evidence.get("block_id"),
                    "block_kind": evidence.get("block_kind"),
                    "char_start": evidence.get("char_start"),
                    "char_end": evidence.get("char_end"),
                    "match": evidence.get("match"),
                    "similarity": evidence.get("similarity"),
                    "relation_to_claim": evidence.get("relation_to_claim"),
                    "minimality": evidence.get("minimality"),
                    "sufficiency_rationale": evidence.get("sufficiency_rationale"),
                    "quote": evidence.get("quote"),
                    "locator": evidence.get("locator"),
                }
            )
    return rows


def write_evidence_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "nanopub_id",
        "claim",
        "subject",
        "relation",
        "object",
        "evidence_id",
        "source_id",
        "page",
        "block_id",
        "block_kind",
        "char_start",
        "char_end",
        "match",
        "similarity",
        "relation_to_claim",
        "minimality",
        "sufficiency_rationale",
        "quote",
        "locator",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            for key in ("subject", "object", "locator"):
                serialized[key] = (
                    json.dumps(serialized[key], ensure_ascii=False, sort_keys=True)
                    if serialized.get(key) is not None
                    else ""
                )
            writer.writerow(serialized)


def source_summary(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in sources:
        metadata = source.get("metadata", {}) if isinstance(source.get("metadata"), dict) else {}
        result.append(
            {
                "source_id": source.get("source_id"),
                "path": source.get("path"),
                "relative_path": source.get("relative_path"),
                "kind": source.get("kind"),
                "role": source.get("role"),
                "sha256": source.get("sha256"),
                "title": metadata.get("title"),
                "authors": metadata.get("authors"),
                "year": metadata.get("year"),
                "doi": metadata.get("doi"),
                "journal": metadata.get("journal"),
                "version": metadata.get("version"),
                "license": metadata.get("license"),
                "url": metadata.get("url"),
                "pages": len(source.get("pages", [])),
                "needs_ocr_pages": [
                    page.get("page")
                    for page in source.get("pages", [])
                    if page.get("needs_ocr")
                ],
            }
        )
    return result


def validation_warning_codes(validation: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(warning.get("code"))
            for warning in validation.get("warnings", [])
            if isinstance(warning, dict) and warning.get("code")
        }
    )


def normalize_status(
    draft_status: Any,
    validation_status: str,
    contract_failed: bool,
    schema_failed: bool,
    claims: list[dict[str, Any]],
    unresolved: list[Any],
    conflicts: list[Any],
    warning_codes: list[str],
) -> str:
    status = compact_text(draft_status).casefold() or "partial"
    if status not in {"success", "partial", "unable", "refused"}:
        status = "partial"
    if not claims:
        return "unable" if status == "unable" else "partial"
    if status in {"unable", "refused"}:
        return status
    if contract_failed or schema_failed or validation_status in {"invalid", "partial"}:
        return "partial"
    if unresolved or conflicts:
        return "partial"
    if any(code in STRONG_PARTIAL_WARNINGS for code in warning_codes):
        return "partial"
    return status


def collect_contract_fields(
    draft: dict[str, Any],
    required_fields: list[str],
    reserved_fields: set[str],
) -> tuple[dict[str, Any], list[str]]:
    supplied = draft.get("contract_fields")
    contract_fields = dict(supplied) if isinstance(supplied, dict) else {}
    notes: list[str] = []
    for field in required_fields:
        if field in reserved_fields or field in contract_fields:
            continue
        if field in draft:
            contract_fields[field] = draft[field]
            notes.append(f"Promoted `{field}` from the draft root.")
    for field in list(contract_fields):
        if field in reserved_fields:
            notes.append(f"Ignored reserved result field `{field}` from contract_fields.")
            contract_fields.pop(field)
    return contract_fields, notes


def schema_issues_for_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "result.schema.json"
    schema = load_json(schema_path)
    return contract_issues(result, schema, "$", schema)


def issue_messages(issues: list[dict[str, Any]]) -> list[str]:
    return [
        f"{issue.get('path', '$')}: [{issue.get('code', 'schema_issue')}] {issue.get('message', '')}".strip()
        for issue in issues
    ]


def main() -> int:
    args = parse_args()
    draft_path = Path(args.draft).expanduser().resolve()
    work = Path(args.work).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    validation_path = (
        Path(args.validation).expanduser().resolve()
        if args.validation
        else work / "validation.json"
    )

    draft = load_json(draft_path)
    manifest = load_json(work / "case_manifest.json")
    validation = load_json(validation_path)
    sources_document = load_json(work / "sources.json")
    validated_claims_document = load_json(work / "validated_claims.json")
    sources = sources_document.get("sources", [])
    claims = validated_claims_document.get("nanopublications", [])

    contract_errors: list[str] = []
    if not args.allow_stale_validation:
        current_hash = sha256_file(draft_path)
        if current_hash != validation.get("draft_sha256"):
            contract_errors.append(
                "Draft changed after validation. Rerun validate_nanopubs.py on the current draft."
            )

    contract = manifest.get("output_contract")
    required_fields = (
        manifest.get("output_contract_required_fields")
        or contract_required_fields(contract)
    )
    contract_fields, promotion_notes = collect_contract_fields(
        draft, required_fields, PRESERVED_RESULT_FIELDS
    )
    contract_issues_for_case: list[dict[str, Any]] = []
    unresolved = draft.get("unresolved") if isinstance(draft.get("unresolved"), list) else []
    conflicts = draft.get("conflicts") if isinstance(draft.get("conflicts"), list) else []
    warning_codes = validation_warning_codes(validation)

    provisional_status = normalize_status(
        draft.get("status"),
        str(validation.get("status", "partial")),
        bool(contract_errors or contract_issues_for_case),
        False,
        claims,
        unresolved,
        conflicts,
        warning_codes,
    )

    result: dict[str, Any] = dict(contract_fields)
    result.update(
        {
            "schema_version": SCHEMA_VERSION,
            "case_id": draft.get("case_id") if "case_id" in draft else manifest.get("case_id"),
            "status": provisional_status,
            "status_reason": compact_text(draft.get("status_reason")) or "No status reason supplied.",
            "task_result": draft.get("task_result")
            if isinstance(draft.get("task_result"), dict)
            else {},
            "nanopublications": claims,
            "sources": source_summary(sources),
            "unresolved": unresolved,
            "conflicts": conflicts,
            "quality_report": {
                **(validation.get("quality_report", {}) or {}),
                "validation_status": validation.get("status"),
                "errors_count": len(validation.get("errors", [])),
                "warnings_count": len(validation.get("warnings", [])),
                "strong_warning_codes": [
                    code for code in warning_codes if code in STRONG_PARTIAL_WARNINGS
                ],
                "mechanical_checks_only": True,
                "semantic_review_required": True,
            },
            "validation": {
                "status": validation.get("status"),
                "errors": validation.get("errors", []),
                "warnings": validation.get("warnings", []),
                "duplicates": validation.get("duplicates", []),
                "validated_at": validation.get("validated_at"),
                "draft_sha256": validation.get("draft_sha256"),
            },
            "input": {
                "case_id_original": manifest.get("case_id"),
                "case_path": manifest.get("case_path"),
                "case_sha256": manifest.get("case_sha256"),
                "task_path": manifest.get("task_path"),
                "task_sha256": manifest.get("task_sha256"),
                "materials": manifest.get("materials", []),
                "unresolved_inputs": manifest.get("unresolved_inputs", []),
            },
            "output_contract": contract,
            "change_log": draft.get("change_log")
            if isinstance(draft.get("change_log"), list) and draft.get("change_log")
            else [
                {
                    "at": utc_now(),
                    "action": "finalized",
                    "detail": "Result assembled by finalize_result.py.",
                }
            ],
            "generated_at": utc_now(),
        }
    )

    # Keep a declared slot available while the case contract is checked.
    # This matters when a case contract explicitly requires schema_validation.
    result["schema_validation"] = {
        "status": "pending",
        "schema_path": "schemas/result.schema.json",
        "issues": [],
    }

    if "case_id" not in result or result["case_id"] != manifest.get("case_id"):
        contract_errors.append(
            f"case_id mismatch: result={result.get('case_id')!r}, manifest={manifest.get('case_id')!r}"
        )

    for field in required_fields:
        if field not in result:
            contract_errors.append(f"required output_contract field missing: {field}")

    result["artifact_manifest"] = {
        "result_json": str(out_path),
        "evidence_ledger_jsonl": str(out_path.parent / "evidence_ledger.jsonl"),
        "evidence_table_csv": str(out_path.parent / "evidence_table.csv"),
        "result_summary_md": str(out_path.parent / "result_summary.md"),
        "input_case_sha256": manifest.get("case_sha256"),
        "input_task_sha256": manifest.get("task_sha256"),
        "result_schema": str(Path("schemas") / "result.schema.json"),
        "result_schema_sha256": sha256_file(
            Path(__file__).resolve().parent.parent / "schemas" / "result.schema.json"
        ),
        "skill_schema": SCHEMA_VERSION,
        "evidence_row_count": sum(
            len(claim.get("evidence", []))
            for claim in claims
            if isinstance(claim, dict)
        ),
    }

    contract_issues_for_case = contract_issues(result, contract)
    contract_errors.extend(issue_messages(contract_issues_for_case))
    contract_failed = bool(contract_errors)
    result["contract_validation"] = {
        "status": "failed" if contract_failed else "passed",
        "required_fields": required_fields,
        "errors": contract_errors,
        "issues": contract_issues_for_case,
        "checklist": contract_checklist(contract),
        "promotions": promotion_notes,
    }
    schema_issues = schema_issues_for_result(result)
    schema_failed = bool(schema_issues)

    result["status"] = normalize_status(
        result.get("status"),
        str(validation.get("status", "partial")),
        contract_failed,
        schema_failed,
        claims,
        unresolved,
        conflicts,
        warning_codes,
    )
    if result["status"] != "success" and result["status_reason"] == "No status reason supplied.":
        reasons = issue_messages(contract_issues_for_case) + issue_messages(schema_issues)
        if warning_codes:
            reasons.append("validation warnings: " + ", ".join(warning_codes))
        result["status_reason"] = (
            "Result requires review: " + "; ".join(reasons[:8])
            if reasons
            else "Result is partial or unable; inspect validation and unresolved items."
        )

    result["schema_validation"] = {
        "status": "failed" if schema_failed else "passed",
        "schema_path": "schemas/result.schema.json",
        "issues": schema_issues,
    }

    rows = evidence_rows(claims)
    write_json(out_path, result)
    write_jsonl(out_path.parent / "evidence_ledger.jsonl", rows)
    write_evidence_csv(out_path.parent / "evidence_table.csv", rows)
    summary_lines = [
        f"# Result summary: {result['case_id']}",
        "",
        f"- Status: `{result['status']}`",
        f"- Reason: {result['status_reason']}",
        f"- Nanopublications: {len(claims)}",
        f"- Evidence rows: {len(rows)}",
        f"- Validation: `{validation.get('status')}`",
        f"- Contract fields: {', '.join(required_fields) if required_fields else 'none explicitly required'}",
        f"- Contract check: `{result['contract_validation']['status']}`",
        f"- Internal schema check: `{result['schema_validation']['status']}`",
        "",
        "This is a structured summary of the actual run. Consult `result.json` for the authoritative output.",
    ]
    (out_path.parent / "result_summary.md").write_text(
        "\n".join(summary_lines) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "case_id": result["case_id"],
                "nanopublications": len(claims),
                "evidence_rows": len(rows),
                "contract_validation": result["contract_validation"]["status"],
                "schema_validation": result["schema_validation"]["status"],
                "strong_warning_codes": [
                    code for code in warning_codes if code in STRONG_PARTIAL_WARNINGS
                ],
                "out": str(out_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not contract_failed and not schema_failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
