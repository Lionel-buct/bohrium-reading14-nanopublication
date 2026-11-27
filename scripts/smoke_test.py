#!/usr/bin/env python3
"""Run a positive and a negative end-to-end test without network access."""

from __future__ import annotations

import json
import subprocess
import os
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


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


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nanopub-smoke-") as temporary:
        root = Path(temporary)
        input_root = root / "input"
        work = root / "work"
        output = root / "output"
        input_root.mkdir()
        work.mkdir()
        output.mkdir()

        source = input_root / "paper.txt"
        source.write_text(
            "Treatment X reduced biomarker Y relative to vehicle after 24 h.\n\n"
            "No significant change in body weight was observed.\n",
            encoding="utf-8",
        )
        case = {
            "case_id": "smoke-case",
            "question": "What changed after treatment X?",
            "materials": [{"role": "paper", "path": "paper.txt"}],
            "metadata": {
                "title": "Illustrative smoke-test source",
                "authors": ["Example Author"],
                "year": 2026,
                "version": "synthetic-v1",
            },
            "output_contract": {
                "required": ["case_id", "status", "nanopublications", "unresolved", "answers"],
                "properties": {
                    "answers": {"type": "array"},
                    "nanopublications": {"type": "array"},
                },
            },
        }
        case_path = input_root / "case.json"
        write_json(case_path, case)
        (input_root / "task.md").write_text("Return evidence-bound nanopublications.\n", encoding="utf-8")

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
            print(prepared.stdout)
            print(prepared.stderr)
            raise SystemExit("prepare_case.py failed")
        checks.append("prepare_case")

        draft = {
            "case_id": "smoke-case",
            "status": "success",
            "status_reason": "Synthetic smoke-test input was fully processed.",
            "task_result": {"question": case["question"], "summary": "Two findings were extracted."},
            "contract_fields": {
                "answers": [
                    {
                        "question": case["question"],
                        "answer": "Biomarker Y decreased; body weight did not significantly change.",
                    }
                ]
            },
            "nanopublications": [
                {
                    "assertion": {
                        "text": "Treatment X reduced biomarker Y relative to vehicle after 24 h.",
                        "subject": {"name": "treatment X", "type": "intervention"},
                        "relation": "decreases",
                        "object": {"name": "biomarker Y", "type": "measurement"},
                        "claim_type": "empirical",
                        "polarity": "supports",
                        "conditions": ["relative to vehicle", "after 24 h"],
                    },
                    "evidence": [
                        {
                            "quote": "Treatment X reduced biomarker Y relative to vehicle after 24 h.",
                            "relation_to_claim": "direct_support",
                            "minimality": "minimal",
                            "sufficiency_rationale": "The sentence directly states the intervention, comparator, direction and time point.",
                        }
                    ],
                },
                {
                    "assertion": {
                        "text": "Treatment X did not significantly change body weight.",
                        "subject": {"name": "treatment X", "type": "intervention"},
                        "relation": "no_change",
                        "object": {"name": "body weight", "type": "measurement"},
                        "claim_type": "negative",
                        "polarity": "supports",
                        "conditions": [],
                    },
                    "evidence": [
                        {
                            "quote": "No significant change in body weight was observed.",
                            "sufficiency_rationale": "The sentence directly reports the tested outcome and its statistical qualification.",
                            "relation_to_claim": "direct_support",
                            "minimality": "minimal",
                        }
                    ],
                },
            ],
            "unresolved": [],
            "conflicts": [],
            "change_log": [{"at": "2026-01-01T00:00:00+00:00", "action": "smoke_test"}],
        }
        draft_path = work / "draft_result.json"
        write_json(draft_path, draft)

        validated = run("validate_nanopubs.py", "--draft", str(draft_path), "--work", str(work), "--strict")
        if validated.returncode != 0:
            print(validated.stdout)
            print(validated.stderr)
            raise SystemExit("positive validation failed")
        checks.append("positive_validation")

        finalized = run(
            "finalize_result.py",
            "--draft",
            str(draft_path),
            "--work",
            str(work),
            "--out",
            str(output / "result.json"),
        )
        if finalized.returncode != 0:
            print((output / "result.json").read_text(encoding="utf-8"))
            print(finalized.stdout)
            print(finalized.stderr)
            raise SystemExit("positive finalization failed")
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        assert result["case_id"] == "smoke-case"
        assert result["status"] == "success"
        assert result["contract_validation"]["status"] == "passed"
        assert result["answers"][0]["question"] == case["question"]
        assert len(result["nanopublications"]) == 2
        assert all(item["evidence"][0]["match"] == "exact" for item in result["nanopublications"])
        checks.append("contract_projection")

        negative = json.loads(json.dumps(draft))
        negative["nanopublications"][0]["evidence"][0]["quote"] = "This sentence is absent from the source."
        negative_path = work / "draft_negative.json"
        write_json(negative_path, negative)
        negative_validation = run(
            "validate_nanopubs.py",
            "--draft",
            str(negative_path),
            "--work",
            str(work),
            "--strict",
        )
        if negative_validation.returncode == 0:
            raise SystemExit("negative validation unexpectedly passed")
        validation_data = json.loads((work / "validation.json").read_text(encoding="utf-8"))
        assert any(error["code"] == "evidence_not_found" for error in validation_data["errors"])
        checks.append("negative_evidence_detection")

        negative_final = run(
            "finalize_result.py",
            "--draft",
            str(negative_path),
            "--work",
            str(work),
            "--out",
            str(output / "negative_result.json"),
        )
        negative_result = json.loads((output / "negative_result.json").read_text(encoding="utf-8"))
        assert negative_final.returncode in {0, 1}
        assert negative_result["status"] == "partial"
        assert negative_result["validation"]["status"] == "invalid"
        checks.append("negative_partial_output")

        stale = json.loads(json.dumps(draft))
        stale["status_reason"] = "Changed after validation."
        stale_path = work / "draft_stale.json"
        write_json(stale_path, stale)
        stale_final = run(
            "finalize_result.py",
            "--draft",
            str(stale_path),
            "--work",
            str(work),
            "--out",
            str(output / "stale_result.json"),
        )
        assert stale_final.returncode == 1
        stale_result = json.loads((output / "stale_result.json").read_text(encoding="utf-8"))
        assert stale_result["contract_validation"]["status"] == "failed"
        checks.append("stale_validation_guard")

        ocr_input = root / "ocr-input"
        ocr_work = root / "ocr-work"
        ocr_input.mkdir()
        (ocr_input / "scan.png").write_bytes(b"\x89PNG\r\n\x1a\nsynthetic-image-fixture")
        ocr_case = {
            "case_id": "ocr-smoke",
            "question": "What did the scanned page report?",
            "materials": [{"role": "paper", "path": "scan.png"}],
        }
        ocr_case_path = ocr_input / "case.json"
        write_json(ocr_case_path, ocr_case)
        (ocr_input / "task.md").write_text("Read the scanned page.\n", encoding="utf-8")
        ocr_prepared = run(
            "prepare_case.py",
            "--case",
            str(ocr_case_path),
            "--input-root",
            str(ocr_input),
            "--work",
            str(ocr_work),
        )
        if ocr_prepared.returncode != 0:
            print(ocr_prepared.stdout)
            print(ocr_prepared.stderr)
            raise SystemExit("OCR prepare_case.py failed")
        ocr_sources = json.loads((ocr_work / "sources.json").read_text(encoding="utf-8"))
        ocr_source_id = ocr_sources["sources"][0]["source_id"]
        ocr_root = ocr_work / "ocr"
        ocr_page = ocr_root / ocr_source_id / "p0001.txt"
        ocr_page.parent.mkdir(parents=True)
        ocr_page.write_text("Treatment Z reduced marker Q after 2 h.\n", encoding="utf-8")
        merged = run(
            "merge_ocr.py",
            "--work",
            str(ocr_work),
            "--ocr-root",
            str(ocr_root),
        )
        if merged.returncode != 0:
            print(merged.stdout)
            print(merged.stderr)
            raise SystemExit("merge_ocr.py failed")
        ocr_manifest = json.loads((ocr_work / "case_manifest.json").read_text(encoding="utf-8"))
        ocr_units = [
            json.loads(line)
            for line in (ocr_work / "source_units.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert ocr_manifest["materials"][0]["needs_ocr_pages"] == []
        assert "ocr_text_merged" in ocr_manifest["warnings"]
        assert len(ocr_units) == 1
        assert ocr_units[0]["needs_ocr"] is False
        assert ocr_units[0]["text"].strip() == "Treatment Z reduced marker Q after 2 h."
        ocr_candidates = [
            json.loads(line)
            for line in (ocr_work / "evidence_candidates.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert ocr_candidates
        assert ocr_manifest["evidence_candidate_count"] == len(ocr_candidates)
        assert "Treatment Z reduced marker Q" in (ocr_work / "claim_worksheet.md").read_text(encoding="utf-8")
        checks.append("ocr_merge")

        ocr_sources["sources"][0]["pages"][0]["text"] = ""
        ocr_sources["sources"][0]["pages"][0]["needs_ocr"] = True
        write_json(ocr_work / "sources.json", ocr_sources)
        ocr_page.write_text("", encoding="utf-8")
        empty_ocr = run(
            "merge_ocr.py",
            "--work",
            str(ocr_work),
            "--ocr-root",
            str(ocr_root),
        )
        assert empty_ocr.returncode == 2
        empty_report = json.loads((ocr_work / "ocr_merge.json").read_text(encoding="utf-8"))
        assert any(item.get("reason") == "empty_ocr_text" for item in empty_report["missing"])
        empty_manifest = json.loads((ocr_work / "case_manifest.json").read_text(encoding="utf-8"))
        assert empty_manifest["materials"][0]["needs_ocr_pages"] == [1]
        checks.append("empty_ocr_is_partial")

    print(json.dumps({"status": "PASS", "checks": checks, "count": len(checks)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
