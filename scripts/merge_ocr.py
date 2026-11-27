#!/usr/bin/env python3
"""Merge externally produced OCR text into the prepared source workspace."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from nanopub_common import load_json, read_text, utc_now, write_json, write_jsonl
from prepare_case import build_claim_worksheet, build_evidence_candidates, make_units


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", default="/app/work", help="Directory from prepare_case.py")
    parser.add_argument("--ocr-root", default=None, help="Directory containing OCR text files")
    parser.add_argument(
        "--auto-tesseract",
        action="store_true",
        help="Try tesseract on rendered pages when matching OCR text files are absent",
    )
    return parser.parse_args()


def candidate_paths(ocr_root: Path, source_id: str, page_number: int) -> list[Path]:
    return [
        ocr_root / source_id / f"p{page_number:04d}.txt",
        ocr_root / source_id / f"{page_number}.txt",
        ocr_root / f"{source_id}_p{page_number:04d}.txt",
        ocr_root / f"{source_id}_{page_number}.txt",
    ]


def run_tesseract(image_path: Path, destination: Path) -> bool:
    executable = shutil.which("tesseract")
    if not executable or not image_path.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [executable, str(image_path), str(destination.with_suffix("")), "-l", "eng+chi_sim"]
    completed = subprocess.run(command, capture_output=True, text=True, errors="replace")
    return completed.returncode == 0 and destination.exists()


def main() -> int:
    args = parse_args()
    work = Path(args.work).expanduser().resolve()
    ocr_root = Path(args.ocr_root).expanduser().resolve() if args.ocr_root else work / "ocr"
    sources_path = work / "sources.json"
    manifest_path = work / "case_manifest.json"
    sources_document = load_json(sources_path)
    manifest = load_json(manifest_path)
    sources: list[dict[str, Any]] = sources_document.get("sources", [])
    merged: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for source in sources:
        for page in source.get("pages", []):
            if not page.get("needs_ocr"):
                continue
            page_number = int(page.get("page") or 1)
            selected: Path | None = next(
                (path for path in candidate_paths(ocr_root, source["source_id"], page_number) if path.exists()),
                None,
            )
            rendered_path = page.get("rendered_path") or page.get("image_path")
            if selected is None and args.auto_tesseract and rendered_path:
                destination = ocr_root / source["source_id"] / f"p{page_number:04d}.txt"
                if run_tesseract(Path(rendered_path), destination):
                    selected = destination
            if selected is None:
                missing.append({"source_id": source["source_id"], "page": page_number})
                continue
            text = read_text(selected)
            page["text"] = text
            page["needs_ocr"] = bool(not text.strip())
            page["extraction"] = "ocr"
            page["ocr_text_path"] = str(selected)
            if text.strip():
                merged.append(
                    {
                        "source_id": source["source_id"],
                        "page": page_number,
                        "path": str(selected),
                        "characters": len(text),
                    }
                )
            else:
                missing.append(
                    {
                        "source_id": source["source_id"],
                        "page": page_number,
                        "path": str(selected),
                        "reason": "empty_ocr_text",
                    }
                )

    units: list[dict[str, Any]] = []
    for source in sources:
        units.extend(make_units(source))

    write_json(sources_path, {"generated_at": utc_now(), "sources": sources})
    candidates = build_evidence_candidates(units, manifest.get("questions", []))
    worksheet = build_claim_worksheet(manifest, sources, candidates)
    write_jsonl(work / "source_units.jsonl", units)
    write_jsonl(work / "evidence_candidates.jsonl", candidates)
    (work / "claim_worksheet.md").write_text(worksheet, encoding="utf-8")
    write_json(work / "ocr_merge.json", {"generated_at": utc_now(), "merged": merged, "missing": missing})

    material_by_id = {item["source_id"]: item for item in manifest.get("materials", [])}
    for source in sources:
        material = material_by_id.get(source["source_id"])
        if material:
            material["needs_ocr_pages"] = [
                page.get("page") for page in source.get("pages", []) if page.get("needs_ocr")
            ]
            material["pages"] = len(source.get("pages", []))
    still_missing = [
        page for source in sources for page in source.get("pages", []) if page.get("needs_ocr")
    ]
    warnings = [warning for warning in manifest.get("warnings", []) if warning != "ocr_required_for_some_pages"]
    if still_missing:
        warnings.append("ocr_required_for_some_pages")
    if merged:
        warnings.append("ocr_text_merged")
    manifest["warnings"] = list(dict.fromkeys(warnings))
    manifest["ocr_updated_at"] = utc_now()
    manifest["evidence_candidate_count"] = len(candidates)
    write_json(manifest_path, manifest)

    print(
        json.dumps(
            {
                "status": "ok" if not missing and not still_missing else "partial",
                "merged": merged,
                "missing": missing,
                "evidence_units": len(units),
                "evidence_candidates": len(candidates),
                "remaining_ocr_pages": len(still_missing),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not missing and not still_missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
