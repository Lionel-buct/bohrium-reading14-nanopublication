#!/usr/bin/env python3
"""Report whether the current runtime can execute the Nanopublication Skill."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


REQUIRED_COMMANDS = ("python3", "python")
OPTIONAL_COMMANDS = ("pdftotext", "pdftoppm", "pdfinfo", "tesseract")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", default="/input")
    parser.add_argument("--work", default="/app/work")
    parser.add_argument("--output", default="/app/output")
    parser.add_argument(
        "--create-dirs",
        action="store_true",
        help="Create work/output directories and verify they are writable.",
    )
    return parser.parse_args()


def executable_status(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    return {"available": bool(path), "path": path}


def module_status(name: str) -> dict[str, Any]:
    return {"available": importlib.util.find_spec(name) is not None}


def directory_status(path: Path, create: bool, writable_check: bool) -> dict[str, Any]:
    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {
                "path": str(path),
                "exists": path.exists(),
                "writable": False,
                "error": type(exc).__name__,
            }
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_dir(),
        "readable": path.is_dir() and os.access(path, os.R_OK),
        "writable": False,
    }
    if not writable_check or not path.is_dir():
        return result
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path, prefix=".probe-", delete=True
        ) as handle:
            handle.write("ok")
            handle.flush()
        result["writable"] = True
    except OSError as exc:
        result["error"] = type(exc).__name__
    return result


def main() -> int:
    args = parse_args()
    input_root = Path(args.input_root).expanduser().resolve()
    work = Path(args.work).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()

    commands = {
        name: executable_status(name) for name in REQUIRED_COMMANDS + OPTIONAL_COMMANDS
    }
    modules = {name: module_status(name) for name in ("pypdf", "docx")}
    directories = {
        "input": directory_status(input_root, create=False, writable_check=False),
        "work": directory_status(work, create=args.create_dirs, writable_check=True),
        "output": directory_status(output, create=args.create_dirs, writable_check=True),
    }

    python_ok = sys.version_info >= (3, 9)
    pdf_text_ok = modules["pypdf"]["available"] or commands["pdftotext"]["available"]
    pdf_render_ok = commands["pdftoppm"]["available"]
    ocr_ok = commands["tesseract"]["available"]
    case_present = (input_root / "case.json").is_file()
    task_present = (input_root / "task.md").is_file()

    blockers: list[str] = []
    warnings: list[str] = []
    if not python_ok:
        blockers.append("Python 3.9 or newer is required.")
    if not pdf_text_ok:
        blockers.append("Install pypdf or provide pdftotext for PDF text extraction.")
    if not case_present:
        warnings.append("/input/case.json is not present; this is expected outside a case run.")
    if not task_present:
        warnings.append("/input/task.md is not present; this is expected outside a case run.")

    if not pdf_render_ok:
        warnings.append("pdftoppm is unavailable; image-only PDF pages cannot be rendered.")
    if not ocr_ok:
        warnings.append("tesseract is unavailable; use the platform OCR tool or mark pages unresolved.")
    if not modules["docx"]["available"]:
        warnings.append("python-docx is unavailable; DOCX extraction will be marked unresolved.")

    if blockers:
        status = "blocked"
    elif warnings:
        status = "partial"
    else:
        status = "ready"

    report = {
        "status": status,
        "python": {
            "version": ".".join(str(part) for part in sys.version_info[:3]),
            "version_ok": python_ok,
            "executable": sys.executable,
        },
        "capabilities": {
            "pdf_text": pdf_text_ok,
            "pdf_render": pdf_render_ok,
            "ocr": ocr_ok,
            "docx": modules["docx"]["available"],
        },
        "commands": commands,
        "modules": modules,
        "directories": directories,
        "case_inputs": {"case_json": case_present, "task_md": task_present},
        "blockers": blockers,
        "warnings": warnings,
        "human_action": (
            "Resolve blockers first. For warnings, continue with the documented fallback "
            "and record affected pages or files in unresolved."
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
