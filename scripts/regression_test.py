#!/usr/bin/env python3
"""Regression checks for contracts, semantic safeguards and material discovery."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_TEXT = (
    "In mice, Treatment X reduced biomarker Y relative to vehicle after 24 h.\n\n"
    "Treatment X was associated with lower biomarker Z after 24 h.\n\n"
    "No significant change in body weight was observed.\n\n"
    "In mice, Treatment X changed biomarker W after 24 h.\n"
)
NEUTRAL_RATIONALE = (
    "The quoted source span contains the entities, direction and conditions needed for review."
)


def run(script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT_DIR / script), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_fixture(
    root: Path,
    name: str,
    case_id: Any = "regression-case",
    contract: dict[str, Any] | None = None,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    input_root = root / name / "input"
    work = root / name / "work"
    output = root / name / "output"
    input_root.mkdir(parents=True)
    work.mkdir()
    output.mkdir()
    (input_root / "paper.txt").write_text(SOURCE_TEXT, encoding="utf-8")
    case = {
        "case_id": case_id,
        "question": "Which evidence-bound changes were reported?",
        "materials": [{"role": "paper", "path": "paper.txt"}],
        "metadata": {
            "title": "Synthetic regression source",
            "authors": ["Regression Fixture"],
            "year": 2026,
            "version": "synthetic-regression-v1",
        },
        "output_contract": contract
        or {
            "required": [
                "case_id",
                "status",
                "nanopublications",
                "unresolved",
                "answers",
            ],
            "properties": {
                "answers": {"type": "array"},
                "nanopublications": {"type": "array"},
            },
        },
    }
    case_path = input_root / "case.json"
    write_json(case_path, case)
    (input_root / "task.md").write_text(
        "Extract atomic claims with verbatim evidence and honest limitations.\n",
        encoding="utf-8",
    )
    prepared = run(
        "prepare_case.py",
        "--case",
        str(case_path),
        "--input-root",
        str(input_root),
        "--work",
        str(work),
    )
    if prepared.returncode != 0:
        raise AssertionError(f"prepare_case failed: {prepared.stdout}\n{prepared.stderr}")
    return input_root, work, output, case


def base_draft(case: dict[str, Any], claim: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "status": "success",
        "status_reason": "The synthetic regression case was processed.",
        "task_result": {"answer": "One evidence-bound observation was reported."},
        "contract_fields": {
            "answers": [
                {
                    "question": case["question"],
                    "answer": "Treatment X reduced biomarker Y in the tested setting.",
                }
            ]
        },
        "nanopublications": [claim or valid_claim()],
        "unresolved": [],
        "conflicts": [],
        "change_log": [
            {"at": "2026-01-01T00:00:00+00:00", "action": "regression_fixture"}
        ],
    }


def valid_claim(
    text: str = "Treatment X reduced biomarker Y in mice after 24 h.",
    relation: str = "decreases",
    claim_type: str = "empirical",
    evidence_quote: str = "In mice, Treatment X reduced biomarker Y relative to vehicle after 24 h.",
    conditions: list[str] | None = None,
    include_rationale: bool = True,
) -> dict[str, Any]:
    evidence = {
        "quote": evidence_quote,
        "source_id": "src01",
        "relation_to_claim": "direct_support",
        "minimality": "minimal",
    }
    if include_rationale:
        evidence["sufficiency_rationale"] = NEUTRAL_RATIONALE
    return {
        "assertion": {
            "text": text,
            "subject": {"name": "treatment X", "type": "intervention"},
            "relation": relation,
            "object": {"name": "biomarker Y", "type": "measurement"},
            "claim_type": claim_type,
            "polarity": "supports",
            "conditions": conditions if conditions is not None else ["in mice", "after 24 h"],
            "quantifiers": [],
        },
        "evidence": [evidence],
    }


def validate_and_finalize(
    work: Path,
    output: Path,
    draft: dict[str, Any],
    name: str = "draft_result.json",
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str], dict[str, Any], dict[str, Any]]:
    draft_path = work / name
    write_json(draft_path, draft)
    validated = run(
        "validate_nanopubs.py",
        "--draft",
        str(draft_path),
        "--work",
        str(work),
        "--strict",
    )
    finalized = run(
        "finalize_result.py",
        "--draft",
        str(draft_path),
        "--work",
        str(work),
        "--out",
        str(output / "result.json"),
    )
    validation = load_json(work / "validation.json")
    result = load_json(output / "result.json") if (output / "result.json").exists() else {}
    return validated, finalized, validation, result


def warning_codes(validation: dict[str, Any]) -> set[str]:
    return {
        str(item.get("code"))
        for item in validation.get("warnings", [])
        if isinstance(item, dict)
    }


def main() -> int:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nanopub-regression-") as temporary:
        root = Path(temporary)

        input_root, work, output, case = prepare_fixture(root, "int-case-id", case_id=917)
        write_json(
            input_root / "draft_result.json",
            {"must_not_be": "treated as source material"},
        )
        rerun = run(
            "prepare_case.py",
            "--case",
            str(input_root / "case.json"),
            "--input-root",
            str(input_root),
            "--work",
            str(work),
        )
        if rerun.returncode != 0:
            raise AssertionError(rerun.stdout + rerun.stderr)
        sources = load_json(work / "sources.json")["sources"]
        assert all("draft_result.json" not in str(source.get("relative_path")) for source in sources)
        probe = run(
            "runtime_probe.py",
            "--input-root",
            str(input_root),
            "--work",
            str(work),
            "--output",
            str(output),
            "--create-dirs",
        )
        assert probe.returncode == 0
        probe_report = json.loads(probe.stdout)
        assert probe_report["status"] in {"ready", "partial"}
        assert probe_report["directories"]["work"]["writable"] is True
        assert probe_report["directories"]["output"]["writable"] is True
        checks.append("runtime_probe")
        checks.append("draft_artifacts_excluded")

        validated, finalized, validation, result = validate_and_finalize(
            work, output, base_draft(case)
        )
        assert validated.returncode == 0
        assert finalized.returncode == 0
        assert result["case_id"] == 917 and isinstance(result["case_id"], int)
        assert result["input"]["case_id_original"] == 917
        assert result["status"] == "success"
        checks.append("numeric_case_id_preserved")

        _, work_num, out_num, case_num = prepare_fixture(
            root,
            "numeric-loss",
            contract={
                "required": ["case_id", "status", "nanopublications", "unresolved", "answers"],
                "properties": {"answers": {"type": "array"}},
            },
        )
        numeric_claim = valid_claim(
            text="Treatment X reduced biomarker Y by 18% in mice after 24 h.",
            conditions=["in mice", "after 24 h"],
        )
        _, numeric_final, numeric_validation, numeric_result = validate_and_finalize(
            work_num, out_num, base_draft(case_num, numeric_claim), "numeric.json"
        )
        assert "numeric_fidelity_risk" in warning_codes(numeric_validation)
        assert numeric_final.returncode == 0
        assert numeric_result["status"] == "partial"
        checks.append("numeric_loss_detected")

        _, work_scope, out_scope, case_scope = prepare_fixture(root, "scope-loss")
        scope_claim = valid_claim(
            text="Treatment X reduced biomarker Y after 24 h.",
            conditions=["after 24 h"],
        )
        _, _, scope_validation, scope_result = validate_and_finalize(
            work_scope, out_scope, base_draft(case_scope, scope_claim), "scope.json"
        )
        assert "scope_not_preserved" in warning_codes(scope_validation)
        assert scope_result["status"] == "partial"
        checks.append("scope_loss_detected")

        _, work_negation, out_negation, case_negation = prepare_fixture(
            root, "negation-reversal"
        )
        negation_claim = valid_claim(
            text="Treatment X did not reduce biomarker Y in mice after 24 h.",
            evidence_quote="In mice, Treatment X reduced biomarker Y relative to vehicle after 24 h.",
        )
        _, _, negation_validation, negation_result = validate_and_finalize(
            work_negation,
            out_negation,
            base_draft(case_negation, negation_claim),
            "negation.json",
        )
        assert "unsupported_negation" in warning_codes(negation_validation)
        assert negation_result["status"] == "partial"
        checks.append("negation_reversal_detected")

        _, work_causal, out_causal, case_causal = prepare_fixture(root, "causal-overclaim")
        causal_claim = valid_claim(
            text="Treatment X causes a reduction in biomarker Z.",
            relation="causes",
            claim_type="causal",
            evidence_quote="Treatment X was associated with lower biomarker Z after 24 h.",
            conditions=["after 24 h"],
        )
        causal_claim["assertion"]["object"] = {"name": "biomarker Z", "type": "measurement"}
        causal_validated, _, causal_validation, causal_result = validate_and_finalize(
            work_causal, out_causal, base_draft(case_causal, causal_claim), "causal.json"
        )
        assert causal_validated.returncode != 0
        assert any(
            item.get("code") == "unsupported_causal_strength"
            for item in causal_validation.get("errors", [])
        )
        assert causal_result["status"] == "partial"
        checks.append("causal_overclaim_rejected")

        _, work_rationale, out_rationale, case_rationale = prepare_fixture(
            root, "missing-rationale"
        )
        rationale_claim = valid_claim(include_rationale=False)
        _, rationale_final, rationale_validation, rationale_result = validate_and_finalize(
            work_rationale,
            out_rationale,
            base_draft(case_rationale, rationale_claim),
            "rationale.json",
        )
        assert "missing_sufficiency_rationale" in warning_codes(rationale_validation)
        assert rationale_final.returncode == 1
        assert rationale_result["status"] == "partial"
        checks.append("missing_rationale_detected")

        _, work_metadata, out_metadata, case_metadata = prepare_fixture(
            root, "metadata-override"
        )
        metadata_draft = base_draft(case_metadata)
        metadata_draft["source_metadata"] = {
            "src01": {"version": "synthetic-override-v2"}
        }
        _, metadata_final, metadata_validation, metadata_result = validate_and_finalize(
            work_metadata,
            out_metadata,
            metadata_draft,
            "metadata.json",
        )
        assert metadata_validation["status"] == "success"
        assert metadata_final.returncode == 0
        assert metadata_result["sources"][0]["version"] == "synthetic-override-v2"
        checks.append("metadata_override_persisted")

        schema_contract = {
            "type": "object",
            "required": [
                "case_id",
                "status",
                "nanopublications",
                "unresolved",
                "schema_validation",
                "answers",
            ],
            "properties": {
                "schema_validation": {
                    "type": "object",
                    "required": ["status"],
                    "properties": {"status": {"type": "string"}},
                },
                "answers": {"type": "array"},
            },
        }
        _, work_schema_contract, out_schema_contract, case_schema_contract = prepare_fixture(
            root, "schema-validation-contract", contract=schema_contract
        )
        _, schema_contract_final, _, schema_contract_result = validate_and_finalize(
            work_schema_contract,
            out_schema_contract,
            base_draft(case_schema_contract),
            "schema-contract.json",
        )
        assert schema_contract_final.returncode == 0
        assert schema_contract_result["contract_validation"]["status"] == "passed"
        assert schema_contract_result["schema_validation"]["status"] == "passed"
        assert schema_contract_result["status"] == "success"
        checks.append("schema_validation_contract_checked")

        nested_contract = {
            "type": "object",
            "required": [
                "case_id",
                "status",
                "nanopublications",
                "unresolved",
                "structured",
            ],
            "properties": {
                "case_id": {"type": ["string", "number"]},
                "status": {"type": "string"},
                "nanopublications": {"type": "array"},
                "unresolved": {"type": "array"},
                "structured": {
                    "type": "object",
                    "required": ["items"],
                    "properties": {
                        "items": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "required": ["label", "score"],
                                "properties": {
                                    "label": {"type": "string"},
                                    "score": {"type": "integer"},
                                },
                            },
                        }
                    },
                },
            },
        }
        _, work_nested, out_nested, case_nested = prepare_fixture(
            root, "nested-contract", contract=nested_contract
        )
        nested_draft = base_draft(case_nested)
        nested_draft["contract_fields"] = {
            "structured": {"items": [{"label": "finding", "score": "high"}]}
        }
        _, nested_final, _, nested_result = validate_and_finalize(
            work_nested, out_nested, nested_draft, "nested.json"
        )
        assert nested_final.returncode == 1
        assert nested_result["contract_validation"]["status"] == "failed"
        assert any(
            issue.get("path") == "$.structured.items[0].score"
            and issue.get("code") == "type_mismatch"
            for issue in nested_result["contract_validation"]["issues"]
        )
        assert nested_result["status"] == "partial"
        checks.append("nested_contract_type_checked")

        _, work_compare, out_compare, case_compare = prepare_fixture(
            root, "missing-comparator"
        )
        compare_claim = valid_claim(
            text="Treatment X is superior for changing biomarker W.",
            relation="outperforms",
            claim_type="comparative",
            evidence_quote="In mice, Treatment X changed biomarker W after 24 h.",
            conditions=["in mice", "after 24 h"],
        )
        compare_claim["assertion"]["object"] = {"name": "biomarker W", "type": "measurement"}
        _, _, compare_validation, compare_result = validate_and_finalize(
            work_compare,
            out_compare,
            base_draft(case_compare, compare_claim),
            "compare.json",
        )
        assert "missing_comparator" in warning_codes(compare_validation)
        assert compare_result["status"] == "partial"
        checks.append("comparator_scope_checked")

    print(
        json.dumps(
            {"status": "PASS", "checks": checks, "count": len(checks)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
