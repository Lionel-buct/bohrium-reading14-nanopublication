#!/usr/bin/env python3
"""Inspect a case contract and turn its supplied files into evidence units."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from nanopub_contract import (
    contract_checklist,
    contract_issues,
    contract_required_fields,
    contract_scaffold,
)
from typing import Any

from nanopub_common import (
    IMAGE_SUFFIXES,
    SUPPORTED_SUFFIXES,
    association_markers,
    causal_markers,
    collect_questions,
    compact_text,
    comparative_markers,
    content_terms,
    extract_declared_metadata,
    extract_doi,
    extract_year,
    find_contract,
    has_negation,
    infer_case_id,
    iter_strings,
    load_json,
    overlap_ratio,
    path_within,
    quantities,
    read_text,
    resolve_path,
    safe_relpath,
    sentence_spans,
    sha256_file,
    stable_id,
    utc_now,
    write_json,
    write_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, help="Path to /input/case.json")
    parser.add_argument("--input-root", default=None, help="Root containing case materials")
    parser.add_argument("--work", default="/app/work", help="Working directory")
    parser.add_argument(
        "--render-empty-pages",
        action="store_true",
        help="Render PDF pages lacking a text layer for visual/OCR fallback",
    )
    parser.add_argument("--render-dpi", type=int, default=150)
    return parser.parse_args()


def available_command(name: str) -> str | None:
    return shutil.which(name)


def run_pdf_to_text(path: Path, page_number: int) -> str:
    executable = available_command("pdftotext")
    if not executable:
        return ""
    command = [
        executable,
        "-f",
        str(page_number),
        "-l",
        str(page_number),
        "-layout",
        str(path),
        "-",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        return ""
    return completed.stdout.replace("\f", "")


def render_pdf_page(path: Path, page_number: int, destination: Path, dpi: int) -> str | None:
    executable = available_command("pdftoppm")
    if not executable:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    output_base = destination.with_suffix("")
    command = [
        executable,
        "-f",
        str(page_number),
        "-l",
        str(page_number),
        "-r",
        str(dpi),
        "-png",
        "-singlefile",
        str(path),
        str(output_base),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, errors="replace")
    if completed.returncode != 0 or not destination.exists():
        return None
    return str(destination)


def normalized_document_metadata(raw: Any) -> dict[str, Any]:
    aliases = {
        "title": "title",
        "author": "authors",
        "authors": "authors",
        "creator": "creator",
        "subject": "subject",
        "keywords": "keywords",
        "creationdate": "creation_date",
        "moddate": "modification_date",
        "producer": "producer",
    }
    result: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return result
    for key, value in raw.items():
        normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key).lstrip("/").casefold()).strip("_")
        canonical = aliases.get(normalized_key, normalized_key)
        if canonical == "year":
            year = extract_year(value)
            if year is not None:
                result[canonical] = year
            continue
        if canonical == "authors" and isinstance(value, (list, tuple)):
            authors = [compact_text(item) for item in value if compact_text(item)]
            if authors:
                result[canonical] = authors
            continue
        if isinstance(value, (list, tuple)):
            text = ", ".join(compact_text(item) for item in value if compact_text(item))
        else:
            text = compact_text(value)
        if text:
            result[canonical] = text
    return result


def extract_pdf(path: Path, source_id: str) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        reader_metadata = reader.metadata or {}
        metadata.update(normalized_document_metadata(dict(reader_metadata)))
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # noqa: BLE001 - report extraction failure honestly
                text = ""
                metadata[f"page_{index}_extract_error"] = str(exc)
            if not text.strip():
                text = run_pdf_to_text(path, index)
                extraction = "pdftotext"
            else:
                extraction = "pypdf"
            pages.append(
                {
                    "page": index,
                    "text": text,
                    "needs_ocr": not bool(compact_text(text)),
                    "extraction": extraction,
                }
            )
    except Exception as exc:  # noqa: BLE001 - fallback to CLI and keep the error visible
        metadata["pypdf_error"] = str(exc)
        page_count = 0
        pdfinfo = available_command("pdfinfo")
        if pdfinfo:
            completed = subprocess.run(
                [pdfinfo, str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            match = re.search(r"^Pages:\s+(\d+)", completed.stdout, re.MULTILINE)
            if match:
                page_count = int(match.group(1))
        if page_count == 0:
            page_count = 1
        for index in range(1, page_count + 1):
            text = run_pdf_to_text(path, index)
            pages.append(
                {
                    "page": index,
                    "text": text,
                    "needs_ocr": not bool(compact_text(text)),
                    "extraction": "pdftotext",
                }
            )

    return {
        "source_id": source_id,
        "path": str(path),
        "kind": "pdf",
        "sha256": sha256_file(path),
        "metadata": metadata,
        "pages": pages,
    }


def extract_docx(path: Path, source_id: str) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    try:
        from docx import Document

        document = Document(str(path))
        core = document.core_properties
        docx_metadata = normalized_document_metadata(
            {
                "title": core.title,
                "authors": core.author,
                "subject": core.subject,
                "keywords": core.keywords,
                "creation_date": core.created.isoformat() if core.created else None,
                "modification_date": core.modified.isoformat() if core.modified else None,
            }
        )
        for index, paragraph in enumerate(document.paragraphs, start=1):
            text = paragraph.text
            if text.strip():
                blocks.append({"kind": "paragraph", "index": index, "text": text})
        for table_index, table in enumerate(document.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                cells = [cell.text.strip() for cell in row.cells]
                text = " | ".join(cells).strip()
                if text:
                    blocks.append(
                        {
                            "kind": "table_row",
                            "index": f"{table_index}:{row_index}",
                            "text": text,
                        }
                    )
    except Exception as exc:  # noqa: BLE001
        blocks = []
        return {
            "source_id": source_id,
            "path": str(path),
            "kind": "docx",
            "sha256": sha256_file(path),
            "metadata": {"docx_error": str(exc)},
            "pages": [{"page": 1, "text": "", "needs_ocr": False, "extraction": "failed"}],
            "blocks": blocks,
        }
    text = "\n\n".join(block["text"] for block in blocks)
    return {
        "source_id": source_id,
        "path": str(path),
        "kind": "docx",
        "sha256": sha256_file(path),
        "metadata": docx_metadata if "docx_metadata" in locals() else {},
        "pages": [{"page": 1, "text": text, "needs_ocr": False, "extraction": "python-docx"}],
        "blocks": blocks,
    }


def extract_textual(path: Path, source_id: str) -> dict[str, Any]:
    text = read_text(path)
    return {
        "source_id": source_id,
        "path": str(path),
        "kind": path.suffix.lstrip(".").lower() or "text",
        "sha256": sha256_file(path),
        "metadata": {},
        "pages": [{"page": 1, "text": text, "needs_ocr": False, "extraction": "text"}],
    }


def extract_image(path: Path, source_id: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "path": str(path),
        "kind": "image",
        "sha256": sha256_file(path),
        "metadata": {},
        "pages": [
            {
                "page": 1,
                "text": "",
                "needs_ocr": True,
                "extraction": "none",
                "image_path": str(path),
            }
        ],
    }


def split_long_segment(text: str, start: int, target: int = 1200) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    cursor = start
    end = start + len(text)
    sentence_boundaries = [
        start + match.end()
        for match in re.finditer(r"(?<=[.!?。！？])\s+", text)
        if match.end() > 0
    ]
    while cursor < end:
        limit = min(end, cursor + target)
        if limit == end:
            ranges.append((cursor, end))
            break
        candidates = [item for item in sentence_boundaries if cursor < item <= limit]
        cut = candidates[-1] if candidates else limit
        ranges.append((cursor, cut))
        cursor = cut
        while cursor < end and text[cursor].isspace():
            cursor += 1
    return ranges


def paragraph_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for match in re.finditer(r"(?:^|\n\s*\n)(.+?)(?=\n\s*\n|\Z)", text, re.DOTALL):
        segment = match.group(1)
        if not segment.strip():
            continue
        start = match.start(1)
        if len(segment) <= 1500:
            ranges.append((start, match.end(1)))
        else:
            ranges.extend(split_long_segment(segment, start))
    if not ranges and text.strip():
        ranges.append((0, len(text)))
    return ranges


def make_units(source: dict[str, Any]) -> list[dict[str, Any]]:
    source_id = source["source_id"]
    units: list[dict[str, Any]] = []
    explicit_blocks = source.get("blocks")
    if explicit_blocks:
        cursor = 0
        for block in explicit_blocks:
            text = block["text"]
            start = cursor
            units.append(
                {
                    "unit_id": f"{source_id}:b{len(units) + 1:04d}",
                    "source_id": source_id,
                    "page": 1,
                    "block_index": block.get("index"),
                    "block_kind": block.get("kind", "paragraph"),
                    "char_start": start,
                    "char_end": start + len(text),
                    "text": text,
                    "needs_ocr": False,
                }
            )
            cursor = start + len(text) + 2
        return units

    for page in source.get("pages", []):
        page_number = page.get("page")
        text = page.get("text", "")
        if page.get("needs_ocr") or not text.strip():
            units.append(
                {
                    "unit_id": f"{source_id}:p{int(page_number or 1):04d}:ocr",
                    "source_id": source_id,
                    "page": page_number,
                    "block_index": None,
                    "block_kind": "page",
                    "char_start": 0,
                    "char_end": len(text),
                    "text": text,
                    "needs_ocr": True,
                    "rendered_path": page.get("rendered_path"),
                }
            )
            continue
        for block_index, (start, end) in enumerate(paragraph_ranges(text), start=1):
            block_text = text[start:end]
            units.append(
                {
                    "unit_id": f"{source_id}:p{int(page_number or 1):04d}:b{block_index:04d}",
                    "source_id": source_id,
                    "page": page_number,
                    "block_index": block_index,
                    "block_kind": "paragraph",
                    "char_start": start,
                    "char_end": end,
                    "text": block_text,
                    "needs_ocr": False,
                }
            )
    return units


def discover_materials(case: Any, input_root: Path, case_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    materials: dict[Path, dict[str, Any]] = {}
    unresolved: list[str] = []

    generated_artifacts = {
        "case_brief.md",
        "case_manifest.json",
        "claim_worksheet.md",
        "contract_checklist.json",
        "draft_result.json",
        "draft_result.template.json",
        "evidence_candidates.jsonl",
        "evidence_ledger.jsonl",
        "evidence_table.csv",
        "result.json",
        "result_summary.md",
        "source_units.jsonl",
        "sources.json",
        "task_copy.md",
        "validated_claims.json",
        "validation.json",
    }

    def is_generated_artifact(path: Path) -> bool:
        name = path.name.casefold()
        return name in generated_artifacts or name.startswith("draft_") or name.startswith("negative_result")

    key_role_map = {
        "paper": "paper",
        "manuscript": "paper",
        "article": "paper",
        "pdf": "paper",
        "supplement": "supplement",
        "supporting": "supplement",
        "figure": "figure",
        "table": "table",
        "data": "data",
        "material": "material",
    }

    def add_material(raw: str, role: str, declared_at: str | None) -> None:
        resolved = resolve_path(raw, input_root, case_dir)
        if resolved is None:
            unresolved.append(f"{declared_at or '$'}: {raw}")
            return
        if is_generated_artifact(resolved):
            return
        if not path_within(resolved, input_root):
            unresolved.append(f"{declared_at or '$'}: path escapes input root: {raw}")
            return
        materials.setdefault(
            resolved,
            {
                "path": resolved,
                "role": role,
                "declared_at": declared_at,
            },
        )

    def visit_structured(value: Any, path: str) -> None:
        if isinstance(value, dict):
            raw_path = None
            for key in ("path", "file", "filename", "source_path", "material_path"):
                candidate = value.get(key)
                if isinstance(candidate, str) and Path(candidate).suffix.lower() in SUPPORTED_SUFFIXES:
                    raw_path = candidate
                    break
            if raw_path:
                declared_role = compact_text(value.get("role") or value.get("kind") or value.get("type")).casefold()
                role = next((mapped for key, mapped in key_role_map.items() if key in declared_role), "material")
                add_material(raw_path, role, f"{path}.{raw_path}")
            for key, child in value.items():
                visit_structured(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit_structured(child, f"{path}[{index}]")

    visit_structured(case, "$")

    for json_path, value in iter_strings(case):
        if Path(value).suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        resolved = resolve_path(value, input_root, case_dir)
        if resolved is None:
            unresolved.append(f"{json_path}: {value}")
            continue
        if is_generated_artifact(resolved):
            continue
        if not path_within(resolved, input_root):
            unresolved.append(f"{json_path}: path escapes input root: {value}")
            continue
        key_parts = [part.casefold() for part in re.split(r"[^A-Za-z0-9]+", json_path)]
        role = next((mapped for key, mapped in key_role_map.items() if key in key_parts), "material")
        if resolved not in materials:
            materials[resolved] = {
                "path": resolved,
                "role": role,
                "declared_at": json_path,
            }

    for path in sorted(input_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        if is_generated_artifact(path):
            continue
        if path.name.casefold() in {"case.json", "task.md"}:
            continue
        if path not in materials:
            materials[path] = {
                "path": path,
                "role": "material",
                "declared_at": None,
            }

    ordered = list(materials.values())
    ordered.sort(key=lambda item: (0 if item["role"] == "paper" else 1, str(item["path"])))
    return ordered, unresolved


def enrich_metadata(source: dict[str, Any], declared: dict[str, Any]) -> None:
    metadata = normalized_document_metadata(source.setdefault("metadata", {}))
    declared_metadata = normalized_document_metadata(declared)
    for key, value in declared_metadata.items():
        metadata.setdefault(key, value)

    pages = source.get("pages", [])
    front_text = "\n".join(str(page.get("text") or "") for page in pages[:3])
    first_page = str(pages[0].get("text") or "") if pages else ""
    metadata_json = json.dumps(metadata, ensure_ascii=False)
    doi = extract_doi(metadata_json, front_text)
    if doi:
        metadata.setdefault("doi", doi)
    metadata_year = extract_year(metadata_json)
    if metadata_year:
        metadata.setdefault("year", metadata_year)

    for key in ("title", "authors", "journal", "version", "license", "url"):
        if key in metadata and key != "authors" and isinstance(metadata[key], list):
            metadata[key] = ", ".join(str(item) for item in metadata[key])

    candidates: list[dict[str, Any]] = []

    def add_candidate(field: str, value: Any, origin: str, page: int | None, quote: str = "") -> None:
        text = compact_text(value)
        if text:
            candidates.append(
                {
                    "field": field,
                    "value": value,
                    "origin": origin,
                    "page": page,
                    "quote": compact_text(quote)[:500] if quote else None,
                    "verified_by_code": origin != "first_page_layout_heuristic",
                }
            )

    for key, value in declared_metadata.items():
        if key in {"title", "authors", "year", "doi", "journal", "version", "license", "url"}:
            add_candidate(key, value, "case.json", None)
    for key, value in metadata.items():
        if key in {"title", "authors", "year", "doi", "journal", "version", "license", "url"}:
            add_candidate(key, value, "embedded_document_metadata", None)

    for page in pages[:3]:
        page_number = page.get("page")
        text = str(page.get("text") or "")
        for match in re.finditer(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", text):
            context = text[max(0, match.start() - 120) : min(len(text), match.end() + 120)]
            add_candidate("doi", match.group(0).rstrip(".,;"), "source_text", page_number, context)
        for match in re.finditer(r"\b(?:19|20)\d{2}\b", text[:6000]):
            context = text[max(0, match.start() - 80) : min(len(text), match.end() + 80)]
            add_candidate("year", int(match.group(0)), "source_text", page_number, context)

    lines = [compact_text(line) for line in first_page.splitlines() if compact_text(line)]
    title_lines = [
        line
        for line in lines[:18]
        if 12 <= len(line) <= 260
        and not re.search(r"(?i)abstract|keywords|doi|http|www\.|@|copyright|table\s+of\s+contents", line)
    ]
    title_lines.sort(key=lambda item: (abs(len(item) - 90), -len(item)))
    for line in title_lines[:5]:
        add_candidate("title", line, "first_page_layout_heuristic", pages[0].get("page") if pages else None, line)

    metadata["metadata_candidates"] = candidates
    metadata["first_page_lines"] = lines[:20]
    missing = [key for key in ("title", "authors", "year", "doi", "journal") if not metadata.get(key)]
    metadata["missing_metadata"] = missing
    source["metadata"] = metadata



def build_evidence_candidates(
    units: list[dict[str, Any]], questions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    question_text = " ".join(compact_text(item.get("text")) for item in questions)
    question_terms = content_terms(question_text)
    candidates: list[dict[str, Any]] = []

    for unit in units:
        if unit.get("needs_ocr") or not compact_text(unit.get("text")):
            continue
        unit_text = str(unit.get("text") or "")
        unit_start = int(unit.get("char_start") or 0)
        for sentence_index, span in enumerate(sentence_spans(unit_text), start=1):
            quote = compact_text(span["text"])
            if len(quote) < 18 or re.fullmatch(r"[\W_\s]+", quote):
                continue
            quantity_values = quantities(quote)
            causal = causal_markers(quote)
            association = association_markers(quote)
            comparative = comparative_markers(quote)
            negation = has_negation(quote)
            overlap = overlap_ratio(question_terms, quote) if question_terms else 0.0
            score = 1.0 + min(3.0, overlap * 6.0)
            if 40 <= len(quote) <= 360:
                score += 1.5
            if quantity_values:
                score += min(3.0, 1.0 + 0.4 * len(quantity_values))
            if comparative:
                score += 1.25
            if negation:
                score += 0.75
            if causal:
                score += 0.75
            if association:
                score += 0.5
            if re.search(r"(?i)references|bibliography|acknowledg", quote):
                score -= 3.0
            if len(quote) > 650:
                score -= 2.0
            char_start = unit_start + int(span["start"])
            char_end = unit_start + int(span["end"])
            candidate_id = stable_id(
                "ec",
                f"{unit.get('source_id')}|{unit.get('page')}|{unit.get('unit_id')}|{char_start}|{char_end}",
                10,
            )
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "source_id": unit.get("source_id"),
                    "page": unit.get("page"),
                    "block_id": unit.get("unit_id"),
                    "block_kind": unit.get("block_kind"),
                    "sentence_index": sentence_index,
                    "char_start": char_start,
                    "char_end": char_end,
                    "quote": quote,
                    "quantities": quantity_values,
                    "negation": negation,
                    "causal_markers": causal,
                    "association_markers": association,
                    "comparative_markers": comparative,
                    "question_overlap": round(overlap, 4),
                    "claim_potential_score": round(score, 3),
                    "candidate_note": "Candidate evidence only; semantic entailment and canonical subject/object require review.",
                }
            )

    candidates.sort(
        key=lambda item: (
            -float(item.get("claim_potential_score") or 0),
            str(item.get("source_id")),
            int(item.get("page") or 0),
            int(item.get("char_start") or 0),
        )
    )
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank
    return candidates


def build_claim_worksheet(
    manifest: dict[str, Any],
    sources: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> str:
    lines = [
        f"# Claim worksheet: {manifest['case_id']}",
        "",
        "This worksheet ranks candidate evidence spans. A candidate is not a finished claim.",
        "For every claim, verify entailment, canonical subject/object, direction, conditions and limitations.",
        "",
        "## Contract checklist",
        "",
        "```json",
        json.dumps(manifest.get("contract_checklist", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## Source metadata candidates",
        "",
    ]
    for source in sources:
        metadata = source.get("metadata", {})
        lines.append(
            f"- `{source['source_id']}` `{source.get('relative_path')}`: "
            f"title={metadata.get('title')!r}, authors={metadata.get('authors')!r}, "
            f"year={metadata.get('year')!r}, doi={metadata.get('doi')!r}, "
            f"missing={metadata.get('missing_metadata', [])}"
        )
    lines.extend(["", "## Highest-potential evidence spans", ""])
    for candidate in candidates[:80]:
        lines.append(
            f"### {candidate['candidate_id']} | rank {candidate['rank']} | score {candidate['claim_potential_score']}"
        )
        lines.append(
            f"- Locator: source={candidate['source_id']}, page={candidate['page']}, "
            f"block={candidate['block_id']}, chars={candidate['char_start']}-{candidate['char_end']}"
        )
        flags: list[str] = []
        if candidate["quantities"]:
            flags.append("quantities=" + ", ".join(candidate["quantities"][:6]))
        if candidate["negation"]:
            flags.append("negation")
        if candidate["causal_markers"]:
            flags.append("causal=" + ", ".join(candidate["causal_markers"]))
        if candidate["association_markers"]:
            flags.append("association=" + ", ".join(candidate["association_markers"]))
        if candidate["comparative_markers"]:
            flags.append("comparative=" + ", ".join(candidate["comparative_markers"]))
        if flags:
            lines.append("- Signals: " + "; ".join(flags))
        lines.append(f"- Quote: {candidate['quote']}")
        lines.append("")
    lines.extend(
        [
            "## Authoring checklist",
            "",
            "1. Select and split candidates that answer the actual task; omit irrelevant bibliographic lines.",
            "2. Keep one testable relation per assertion and copy the shortest sufficient quote.",
            "3. Preserve numbers, units, conditions, comparison baseline and epistemic strength.",
            "4. Run validate_nanopubs.py; inspect semantic warnings, not only errors.",
            "5. Promote only evidence-backed metadata into draft_result.source_metadata.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_case_brief(
    manifest: dict[str, Any], sources: list[dict[str, Any]], units: list[dict[str, Any]]
) -> str:
    lines = [
        f"# Case {manifest['case_id']}",
        "",
        f"- Generated: {manifest['generated_at']}",
        f"- Case file: `{manifest['case_path']}`",
        f"- Input root: `{manifest['input_root']}`",
        f"- Output contract found: {manifest['output_contract_found']}",
        "",
        "## Declared questions and instructions",
        "",
    ]
    if manifest["questions"]:
        for item in manifest["questions"]:
            lines.append(f"- `{item['path']}`: {compact_text(item['text'])[:1200]}")
    else:
        lines.append("- No explicit question key was found. Read `task.md` and the original case JSON before answering.")
    lines.extend(["", "## Sources", ""])
    for source in sources:
        pages = source.get("pages", [])
        ocr_pages = [str(page.get("page")) for page in pages if page.get("needs_ocr")]
        lines.append(
            f"- `{source['source_id']}`: `{source['path']}` ({source['kind']}, "
            f"{len(pages)} page(s), OCR needed: {', '.join(ocr_pages) if ocr_pages else 'none'})"
        )
    lines.extend(["", "## Evidence units", ""])
    lines.append(f"- `{len(units)}` units were written to `source_units.jsonl`.")
    lines.append(
        f"- `{manifest.get('evidence_candidate_count', 0)}` sentence-level candidates were written to `evidence_candidates.jsonl`."
    )
    lines.append("- Ranked authoring prompts are in `claim_worksheet.md`; contract types are in `contract_checklist.json`.")
    lines.extend(
        [
            "",
            "## Required workflow",
            "",
            "1. Read the original case and `task.md`; do not infer answers from case labels.",
            "2. Build `draft_result.json` and copy evidence quotes verbatim from `source_units.jsonl`.",
            "3. Run `validate_nanopubs.py`, fix every error, and rerun.",
            "4. Run `finalize_result.py` to produce `/app/output/result.json`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    case_path = Path(args.case).expanduser().resolve()
    case = load_json(case_path)
    input_root = Path(args.input_root).expanduser().resolve() if args.input_root else case_path.parent
    work = Path(args.work).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)

    declared_metadata = extract_declared_metadata(case)
    materials, unresolved = discover_materials(case, input_root, case_path.parent)
    sources: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []

    for index, material in enumerate(materials, start=1):
        path = material["path"]
        source_id = f"src{index:02d}"
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            source = extract_pdf(path, source_id)
        elif suffix == ".docx":
            source = extract_docx(path, source_id)
        elif suffix in IMAGE_SUFFIXES:
            source = extract_image(path, source_id)
        else:
            source = extract_textual(path, source_id)
        source["role"] = material["role"]
        source["declared_at"] = material["declared_at"]
        source["relative_path"] = safe_relpath(path, input_root)
        enrich_metadata(source, declared_metadata)
        if args.render_empty_pages and suffix == ".pdf":
            for page in source.get("pages", []):
                if page.get("needs_ocr"):
                    destination = work / "rendered" / f"{source_id}_p{int(page.get('page') or 1):04d}.png"
                    rendered = render_pdf_page(path, int(page.get("page") or 1), destination, args.render_dpi)
                    if rendered:
                        page["rendered_path"] = rendered
        sources.append(source)
        units.extend(make_units(source))

    task_path = input_root / "task.md"
    task_text = read_text(task_path) if task_path.exists() else ""
    contract = find_contract(case)
    contract_fields = contract_required_fields(contract)
    case_id = infer_case_id(case, fallback=case_path.parent.name or "unknown-case")
    questions = collect_questions(case)
    checklist = contract_checklist(contract)
    scaffold = contract_scaffold(contract, case_id)
    reserved_result_fields = {
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
    contract_field_scaffold = (
        {
            key: value
            for key, value in scaffold.items()
            if key not in reserved_result_fields
        }
        if isinstance(scaffold, dict)
        else {}
    )
    candidates = build_evidence_candidates(units, questions)
    manifest = {
        "schema_version": "nanopublication-case-manifest/1.1",
        "generated_at": utc_now(),
        "case_id": case_id,
        "case_path": str(case_path),
        "case_sha256": sha256_file(case_path),
        "input_root": str(input_root),
        "task_path": str(task_path) if task_path.exists() else None,
        "task_sha256": sha256_file(task_path) if task_path.exists() else None,
        "questions": questions,
        "output_contract_found": contract is not None,
        "output_contract": contract,
        "output_contract_required_fields": contract_fields,
        "contract_field_scaffold": contract_field_scaffold,
        "contract_checklist": checklist,
        "evidence_candidate_count": len(candidates),
        "declared_metadata": declared_metadata,
        "materials": [
            {
                "source_id": source["source_id"],
                "path": source["path"],
                "relative_path": source["relative_path"],
                "kind": source["kind"],
                "role": source["role"],
                "sha256": source["sha256"],
                "declared_at": source["declared_at"],
                "pages": len(source.get("pages", [])),
                "needs_ocr_pages": [
                    page.get("page") for page in source.get("pages", []) if page.get("needs_ocr")
                ],
            }
            for source in sources
        ],
        "unresolved_inputs": unresolved,
        "warnings": [],
    }

    if not sources:
        manifest["warnings"].append("no_materials_found")
    if any(page.get("needs_ocr") for source in sources for page in source.get("pages", [])):
        manifest["warnings"].append("ocr_required_for_some_pages")
    if contract is None:
        manifest["warnings"].append("no_output_contract_found")

    draft_template = {
        "_instructions": [
            "Replace every placeholder with results derived from the actual case materials.",
            "Copy evidence quotes verbatim from source_units.jsonl.",
            "Do not include formal test answers supplied by the platform.",
            "Put case-specific contract fields in contract_fields using their exact names.",
            "Use evidence_candidates.jsonl as locator-preserving candidate spans, then decide entailment.",
            "Fill sufficiency_rationale for every evidence item and preserve all numbers and qualifiers.",
        ],
        "case_id": case_id,
        "status": "partial",
        "status_reason": "Template not yet completed.",
        "task_result": {},
        "nanopublications": [],
        "unresolved": [],
        "conflicts": [],
        "source_metadata": {},
        "contract_fields": contract_field_scaffold,
        "change_log": [
            {"at": utc_now(), "action": "initialized", "detail": "Draft template generated by prepare_case.py."}
        ],
    }

    write_json(work / "case_manifest.json", manifest)
    write_json(work / "sources.json", {"generated_at": utc_now(), "sources": sources})
    write_jsonl(work / "source_units.jsonl", units)
    write_jsonl(work / "evidence_candidates.jsonl", candidates)
    write_json(work / "draft_result.template.json", draft_template)
    write_json(work / "contract_checklist.json", checklist)
    (work / "claim_worksheet.md").write_text(
        build_claim_worksheet(manifest, sources, candidates), encoding="utf-8"
    )
    (work / "case_brief.md").write_text(build_case_brief(manifest, sources, units), encoding="utf-8")
    if task_text:
        (work / "task_copy.md").write_text(task_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "case_id": case_id,
                "materials": len(sources),
                "evidence_units": len(units),
                "evidence_candidates": len(candidates),
                "ocr_pages": sum(
                    1 for source in sources for page in source.get("pages", []) if page.get("needs_ocr")
                ),
                "output_contract_found": contract is not None,
                "warnings": manifest["warnings"],
                "work": str(work),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
