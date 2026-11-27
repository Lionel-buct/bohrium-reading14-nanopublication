#!/usr/bin/env python3
"""Check the Skill package against the public submission resource limits."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".json",
    ".jsonl",
    ".txt",
    ".csv",
    ".tsv",
    ".yaml",
    ".yml",
    ".toml",
    ".sh",
    ".tex",
}
MAX_TEXT_FILES = 50
MAX_FILE_BYTES = 500 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024

SENSITIVE_PATTERNS = {
    "windows_user_path": re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+"),
    "onedrive_path": re.compile(r"(?i)\b[A-Z]:\\OneDrive\\"),
    "unix_user_path": re.compile(r"(?i)(?:^|[\s\"'])/(?:Users|home)/[^/\s\"']+"),
    "api_key_prefix": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"),
    "assigned_secret": re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*[\"']?[^\s\"']{8,}"
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent.parent),
        help="Submission directory to inspect",
    )
    return parser.parse_args()


def discover_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            files.append(path)
        elif path.is_file() and "__pycache__" not in path.parts:
            files.append(path)
    return files


def inspect_text(path: Path, relative: str, errors: list[dict[str, Any]]) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        if path.suffix.lower() in TEXT_SUFFIXES:
            errors.append(
                {
                    "path": relative,
                    "code": "invalid_utf8",
                    "message": "Text resource must be UTF-8.",
                }
            )
        return False
    for name, pattern in SENSITIVE_PATTERNS.items():
        if pattern.search(text):
            errors.append(
                {
                    "path": relative,
                    "code": name,
                    "message": "Possible personal path, credential, or secret found.",
                }
            )
    return True


def inspect_json(path: Path, relative: str, errors: list[dict[str, Any]]) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(
            {
                "path": relative,
                "code": "invalid_json",
                "message": f"JSON could not be parsed: {type(exc).__name__}.",
            }
        )
        return None


def inspect_skill_frontmatter(root: Path, errors: list[dict[str, Any]]) -> None:
    path = root / "SKILL.md"
    if not path.is_file():
        errors.append({
            "path": "SKILL.md",
            "code": "missing_skill",
            "message": "SKILL.md is required.",
        })
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        errors.append({
            "path": "SKILL.md",
            "code": "invalid_frontmatter",
            "message": "SKILL.md must start with YAML frontmatter.",
        })
        return
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        errors.append({
            "path": "SKILL.md",
            "code": "invalid_frontmatter",
            "message": "SKILL.md frontmatter is not closed.",
        })
        return
    frontmatter = lines[1:end]
    for key in ("name", "description"):
        if not any(line.startswith(f"{key}:") and line.split(":", 1)[1].strip() for line in frontmatter):
            errors.append({
                "path": "SKILL.md",
                "code": "missing_frontmatter_field",
                "message": f"Frontmatter field `{key}` is required.",
            })


def inspect_reusable_examples(root: Path, errors: list[dict[str, Any]]) -> int:
    path = root / "examples" / "assertion-samples.json"
    if not path.is_file():
        errors.append({
            "path": "examples/assertion-samples.json",
            "code": "missing_assertion_samples",
            "message": "The public rubric asks for reusable assertion samples.",
        })
        return 0
    value = inspect_json(path, "examples/assertion-samples.json", errors)
    if not isinstance(value, list):
        errors.append({
            "path": "examples/assertion-samples.json",
            "code": "invalid_assertion_samples",
            "message": "Assertion samples must be a JSON array.",
        })
        return 0
    if len(value) != 20:
        errors.append({
            "path": "examples/assertion-samples.json",
            "code": "assertion_sample_count",
            "message": f"Expected 20 synthetic samples; found {len(value)}.",
        })
    for index, sample in enumerate(value):
        if not isinstance(sample, dict):
            errors.append({
                "path": f"examples/assertion-samples.json[{index}]",
                "code": "invalid_assertion_sample",
                "message": "Each sample must be an object.",
            })
            continue
        if sample.get("illustrative") is not True:
            errors.append({
                "path": f"examples/assertion-samples.json[{index}]",
                "code": "unmarked_example",
                "message": "Every sample must set illustrative=true.",
            })
        assertion = sample.get("assertion")
        evidence = sample.get("evidence")
        if not isinstance(assertion, dict) or not isinstance(evidence, list) or not evidence:
            errors.append({
                "path": f"examples/assertion-samples.json[{index}]",
                "code": "incomplete_assertion_sample",
                "message": "Each sample needs an assertion object and non-empty evidence array.",
            })
    return len(value)


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    paths = discover_files(root)
    cache_paths = [
        path
        for path in root.rglob("*")
        if path.is_file() and ("__pycache__" in path.parts or path.suffix.lower() == ".pyc")
    ]

    symlinks = [path for path in paths if path.is_symlink()]
    regular = [path for path in paths if path.is_file() and not path.is_symlink()]
    text_paths: list[Path] = []
    total_bytes = 0
    json_files = 0
    for path in regular:
        relative = str(path.relative_to(root))
        size = path.stat().st_size
        total_bytes += size
        if "__pycache__" in path.parts or path.suffix.lower() == ".pyc":
            errors.append(
                {
                    "path": relative,
                    "code": "generated_cache",
                    "message": "Remove generated Python cache files from the submission.",
                }
            )
        if size > MAX_FILE_BYTES:
            errors.append(
                {
                    "path": relative,
                    "code": "file_too_large",
                    "message": f"{size} bytes exceeds {MAX_FILE_BYTES}.",
                }
            )
        if path.suffix.lower() in TEXT_SUFFIXES and inspect_text(path, relative, errors):
            text_paths.append(path)
        if path.suffix.lower() == ".json" and inspect_json(path, relative, errors) is not None:
            json_files += 1

    if len(text_paths) > MAX_TEXT_FILES:
        errors.append(
            {
                "path": ".",
                "code": "too_many_text_files",
                "message": f"{len(text_paths)} text files exceeds {MAX_TEXT_FILES}.",
            }
        )
    if total_bytes > MAX_TOTAL_BYTES:
        errors.append(
            {
                "path": ".",
                "code": "total_too_large",
                "message": f"{total_bytes} bytes exceeds {MAX_TOTAL_BYTES}.",
            }
        )
    for path in symlinks:
        errors.append(
            {
                "path": str(path.relative_to(root)),
                "code": "symlink",
                "message": "Symbolic links are not allowed in the submission package.",
            }
        )
    if not (root / "SKILL.md").is_file():
        errors.append({"path": "SKILL.md", "code": "missing_skill", "message": "SKILL.md is required."})
    for path in cache_paths:
        errors.append(
            {
                "path": str(path.relative_to(root)),
                "code": "generated_cache",
                "message": "Remove generated Python cache files from the submission.",
            }
        )
    inspect_skill_frontmatter(root, errors)
    if not (root / "README.md").is_file():
        warnings.append({"path": "README.md", "code": "missing_readme", "message": "README.md is recommended."})
    assertion_sample_count = inspect_reusable_examples(root, errors)
    if not (root / "scripts" / "runtime_probe.py").is_file():
        warnings.append({
            "path": "scripts/runtime_probe.py",
            "code": "missing_runtime_probe",
            "message": "A runtime probe improves deployment reliability.",
        })
    github_path = root / "GITHUB_URL.txt"
    if github_path.is_file():
        first_line = github_path.read_text(encoding="utf-8").splitlines()[0].strip()
        if not re.match(r"^https://github\.com/[^\s]+$", first_line):
            errors.append({
                "path": "GITHUB_URL.txt",
                "code": "invalid_github_url",
                "message": "The first line must be a public https://github.com/ URL.",
            })

    result = {
        "status": "PASS" if not errors else "FAIL",
        "root": str(root),
        "json_files": json_files,
        "assertion_samples": assertion_sample_count,
        "text_files": len(text_paths),
        "text_file_limit": MAX_TEXT_FILES,
        "regular_files": len(regular),
        "total_bytes": total_bytes,
        "total_bytes_limit": MAX_TOTAL_BYTES,
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
