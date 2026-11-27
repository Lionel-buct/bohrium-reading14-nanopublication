"""Shared helpers for the nanopublication evidence pipeline."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SUPPORTED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".jsonl",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

NEGATION_CUES = (
    "no ",
    "not ",
    "never",
    "neither",
    "without",
    "failed to",
    "did not",
    "no significant",
    "non-significant",
    "non significant",
    "absence of",
    "lack of",
    "does not",
    "was not",
    "were not",
    "cannot",
    "can't",
    "未",
    "无",
    "没有",
    "并非",
    "不能",
    "无法",
    "不显著",
)
CAUSAL_CUES = (
    "cause",
    "caused",
    "causes",
    "causal",
    "due to",
    "because of",
    "results in",
    "resulted in",
    "leads to",
    "led to",
    "drives",
    "induced",
    "导致",
    "引起",
    "造成",
    "归因于",
    "由于",
)
ASSOCIATION_CUES = (
    "associated with",
    "association",
    "correlated",
    "correlation",
    "related to",
    "predicts",
    "predictive of",
    "may",
    "might",
    "suggests",
    "可能",
    "相关",
    "关联",
    "预测",
    "提示",
)
COMPARATIVE_CUES = (
    "compared with",
    "compared to",
    "relative to",
    "versus",
    " vs ",
    "than",
    "higher",
    "lower",
    "greater",
    "smaller",
    "increase",
    "decrease",
    "outperform",
    "优于",
    "高于",
    "低于",
    "相比",
    "增加",
    "降低",
)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from",
    "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "their",
    "these", "this", "those", "to", "was", "were", "with", "we", "our", "can",
    "may", "might", "also", "after", "before", "under", "over", "among", "between",
    "showed", "show", "shows", "observed", "reported", "using", "used", "use",
}

QUANTITY_RE = re.compile(
    r"(?<![\w.])(?:"
    r"p\s*[=<>≤≥]\s*0?\.\d+(?:e[-+]?\d+)?|"
    r"n\s*=\s*\d+|"
    r"(?:95|99|90|80|68)%\s*(?:CI|confidence interval)|"
    r"[-+]?\d+(?:\.\d+)?(?:\s*(?:%|‰|°C|K|Pa|kPa|MPa|h|hr|hrs|min|s|ms|µs|ns|d|days?|weeks?|months?|years?|fold|times?|mg|g|kg|µg|ng|mL|L|µm|nm|mm|cm|m|M|mM|µM|nM|eV|keV|MeV|Hz|kHz|MHz|GHz))?|"
    r"\d+\s*[-–—]\s*\d+|"
    r"[≤≥<>]\s*\d+(?:\.\d+)?"
    r")"
)



def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: str | Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: str | Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(path)


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8-sig", errors="replace")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: str, length: int = 12) -> str:
    return f"{prefix}-{sha256_text(value)[:length]}"


def compact_text(text: Any) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def iter_strings(value: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_strings(child, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


def normalized_with_map(text: str, casefold: bool = True) -> tuple[str, list[int]]:
    """Normalize whitespace and width while retaining original character offsets."""

    output: list[str] = []
    offsets: list[int] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char in {"-", "\u2010", "\u2011"} and index + 1 < len(text) and text[index + 1].isspace():
            next_index = index + 1
            while next_index < len(text) and text[next_index].isspace():
                next_index += 1
            if next_index < len(text) and output and output[-1].isalpha() and text[next_index].isalpha():
                output.append("-")
                offsets.append(index)
                index = next_index
                continue
        if char.isspace():
            start = index
            while index < len(text) and text[index].isspace():
                index += 1
            if output and output[-1] != " ":
                output.append(" ")
                offsets.append(start)
            continue
        normalized = unicodedata.normalize("NFKC", char)
        if casefold:
            normalized = normalized.casefold()
        for item in normalized:
            output.append(item)
            offsets.append(index)
        index += 1
    return "".join(output), offsets


def locate_quote(text: str, quote: str) -> dict[str, Any] | None:
    """Return the first exact or whitespace-normalized occurrence of a quote."""

    if not text or not quote:
        return None

    exact_start = text.find(quote)
    if exact_start >= 0:
        return {
            "start": exact_start,
            "end": exact_start + len(quote),
            "match": "exact",
        }

    normalized_text, offsets = normalized_with_map(text)
    normalized_quote, _ = normalized_with_map(quote)
    if not normalized_quote:
        return None
    start = normalized_text.find(normalized_quote)
    if start < 0:
        return None
    end = start + len(normalized_quote)
    if not offsets or end <= start:
        return None
    original_start = offsets[start]
    original_end = offsets[end - 1] + 1
    return {
        "start": original_start,
        "end": original_end,
        "match": "whitespace_normalized",
    }


def similarity(left: str, right: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(
        None,
        compact_text(left).casefold(),
        compact_text(right).casefold(),
        autojunk=False,
    ).ratio()


def sentence_count(text: str) -> int:
    pieces = re.split(r"(?<=[.!?。！？])\s+|\n+", compact_text(text))
    return max(1, len([piece for piece in pieces if piece.strip()]))


def sentence_spans(text: str, max_chars: int = 900) -> list[dict[str, Any]]:
    """Split text into sentence-like spans while preserving original offsets."""
    if not text.strip():
        return []
    boundaries = [match.end() for match in re.finditer(r"(?<=[.!?。！？])\s+", text)]
    spans: list[dict[str, Any]] = []
    cursor = 0
    boundary_iter = iter(boundaries)
    next_boundary = next(boundary_iter, None)
    while cursor < len(text):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text):
            break
        while next_boundary is not None and next_boundary <= cursor:
            next_boundary = next(boundary_iter, None)
        limit = min(len(text), cursor + max_chars)
        end = next_boundary if next_boundary is not None and next_boundary <= limit else limit
        if end < len(text) and end > cursor + 40:
            whitespace = text.rfind(" ", cursor + 40, end)
            if whitespace > cursor + 40:
                end = whitespace
        raw = text[cursor:end]
        left_trim = len(raw) - len(raw.lstrip())
        right_trim = len(raw.rstrip())
        start = cursor + left_trim
        end = cursor + right_trim
        if end > start and compact_text(text[start:end]):
            spans.append({"start": start, "end": end, "text": text[start:end]})
        cursor = max(cursor + 1, end)
        while next_boundary is not None and next_boundary <= cursor:
            next_boundary = next(boundary_iter, None)
    return spans


def quantities(text: str) -> list[str]:
    values = [compact_text(match.group(0)) for match in QUANTITY_RE.finditer(str(text or ""))]
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold().replace(" ", "")
        if value and key not in seen:
            seen.add(key)
            ordered.append(value)
    return ordered


def content_terms(text: str) -> list[str]:
    lowered = compact_text(text).casefold()
    terms: list[str] = []
    for token in re.findall(r"[a-z][a-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", lowered):
        if token in STOPWORDS:
            continue
        terms.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{4,}", token):
            terms.extend(token[index : index + 2] for index in range(len(token) - 1))
    return list(dict.fromkeys(terms))


def has_negation(text: str) -> bool:
    lowered = f" {compact_text(text).casefold()} "
    return any(cue in lowered for cue in NEGATION_CUES)


def cue_matches(text: str, cues: tuple[str, ...]) -> list[str]:
    lowered = f" {compact_text(text).casefold()} "
    return [cue.strip() for cue in cues if cue in lowered]


def causal_markers(text: str) -> list[str]:
    return cue_matches(text, CAUSAL_CUES)


def association_markers(text: str) -> list[str]:
    return cue_matches(text, ASSOCIATION_CUES)


def comparative_markers(text: str) -> list[str]:
    return cue_matches(text, COMPARATIVE_CUES)


def overlap_ratio(terms: list[str], text: str) -> float:
    if not terms:
        return 0.0
    evidence_terms = set(content_terms(text))
    return sum(1 for term in terms if term in evidence_terms) / len(terms)



def clause_markers(text: str) -> list[str]:
    markers = [
        ";",
        " and ",
        " because ",
        " whereas ",
        " while ",
        " therefore ",
        " thereby ",
        " leading to ",
        " as well as ",
        "并且",
        "同时",
        "以及",
        "因为",
        "因此",
        "从而",
        "导致",
        "而",
    ]
    lowered = f" {text.casefold()} "
    return [marker for marker in markers if marker.casefold() in lowered]


def coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def object_name(value: Any) -> str:
    if isinstance(value, str):
        return compact_text(value)
    if isinstance(value, dict):
        for key in ("name", "label", "text", "entity", "value", "id"):
            if value.get(key):
                return compact_text(value[key])
    return compact_text(value)


def find_contract(answer_json: Any) -> Any:
    if not isinstance(answer_json, dict):
        return None
    queue: list[tuple[str, Any]] = [("", answer_json)]
    preferred = {
        "output_contract",
        "outputcontract",
        "output_schema",
        "output_format",
        "required_output_fields",
        "required_fields",
        "response_schema",
        "submission_schema",
        "result_schema",
        "answer_schema",
        "schema",
    }
    while queue:
        key_path, value = queue.pop(0)
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = str(key).casefold().replace("-", "_")
                next_path = f"{key_path}.{key}" if key_path else str(key)
                if normalized_key in preferred:
                    return child
                if isinstance(child, (dict, list)):
                    queue.append((next_path, child))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if isinstance(child, (dict, list)):
                    queue.append((f"{key_path}[{index}]", child))
    return None


def contract_required_fields(contract: Any) -> list[str]:
    if contract is None:
        return []
    if isinstance(contract, str):
        return [contract]
    if isinstance(contract, list):
        return [str(item) for item in contract if isinstance(item, str)]
    if not isinstance(contract, dict):
        return []
    required = contract.get("required")
    if isinstance(required, list):
        return [str(item) for item in required if isinstance(item, str)]
# Compatibility note: new pipeline modules import the stricter contract helpers
# from nanopub_contract.py. These legacy functions remain intentionally isolated.

    properties = contract.get("properties")
    if isinstance(properties, dict):
        return [str(key) for key in properties]

    fields = contract.get("fields")
    if isinstance(fields, list):
        result = []
        for field in fields:
            if isinstance(field, str):
                result.append(field)
            elif isinstance(field, dict):
                name = field.get("name") or field.get("field") or field.get("key")
                if name:
                    result.append(str(name))
        return result
    if isinstance(fields, dict):
        return [str(key) for key in fields]

    metadata_keys = {
        "$schema",
        "$id",
        "title",
        "description",
        "type",
        "version",
        "notes",
        "required",
        "properties",
        "additionalproperties",
    }
    return [
        str(key)
        for key in contract
        if str(key).casefold() not in metadata_keys
        and not str(key).startswith("_")
    ]


def _json_type_matches(value: Any, expected: str) -> bool:
    expected = expected.casefold()
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def contract_issues(
    value: Any,
    contract: Any,
    path: str = "$",
    root_schema: Any = None,
) -> list[dict[str, Any]]:
    """Validate the JSON-Schema subset used by challenge output contracts."""
    if root_schema is None:
        root_schema = contract
    if contract is None:
        return []
    if isinstance(contract, bool):
        if not contract:
            return [{"path": path, "code": "schema_false", "message": "Value is forbidden by the contract."}]
        return []
    if not isinstance(contract, dict):
        return []

    issues: list[dict[str, Any]] = []
    if "const" in contract and value != contract["const"]:
        issues.append(
            {"path": path, "code": "const_mismatch", "message": f"Expected constant {contract['const']!r}."}
        )
    enum = contract.get("enum")
    if isinstance(enum, list) and value not in enum:
        issues.append(
            {"path": path, "code": "enum_mismatch", "message": f"Value is not one of {enum!r}."}
        )

    expected_types = contract.get("type")
    if isinstance(expected_types, str):
        expected_types = [expected_types]
    if isinstance(expected_types, list) and expected_types:
        if not any(_json_type_matches(value, str(expected)) for expected in expected_types):
            issues.append(
                {
                    "path": path,
                    "code": "type_mismatch",
                    "message": f"Expected {expected_types!r}; received {type(value).__name__}.",
                }
            )
            return issues

    if isinstance(value, str):
        min_length = contract.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            issues.append(
                {"path": path, "code": "min_length", "message": f"String is shorter than minLength={min_length}."}
            )
        max_length = contract.get("maxLength")
        if isinstance(max_length, int) and len(value) > max_length:
            issues.append(
                {"path": path, "code": "max_length", "message": f"String is longer than maxLength={max_length}."}
            )
        pattern = contract.get("pattern")
        if isinstance(pattern, str):
            try:
                if re.search(pattern, value) is None:
                    issues.append(
                        {
                            "path": path,
                            "code": "pattern_mismatch",
                            "message": f"String does not match pattern {pattern!r}.",
                        }
                    )
            except re.error:
                pass

    if isinstance(value, list):
        min_items = contract.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            issues.append(
                {"path": path, "code": "min_items", "message": f"Array has fewer than minItems={min_items} items."}
            )
        max_items = contract.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            issues.append(
                {"path": path, "code": "max_items", "message": f"Array has more than maxItems={max_items} items."}
            )
        item_contract = contract.get("items")
        if item_contract is not None:
            for index, child in enumerate(value):
                issues.extend(contract_issues(child, item_contract, f"{path}[{index}]", root_schema))

    if isinstance(value, dict):
        required = contract.get("required")
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    issues.append(
                        {
                            "path": f"{path}.{key}",
                            "code": "required_missing",
                            "message": f"Required field `{key}` is missing.",
                        }
                    )
        properties = contract.get("properties")
        if isinstance(properties, dict):
            for key, child_contract in properties.items():
                if key in value:
                    issues.extend(contract_issues(value[key], child_contract, f"{path}.{key}", root_schema))
        if contract.get("additionalProperties") is False and isinstance(properties, dict):
            allowed = {str(key) for key in properties}
            for key in value:
                if str(key) not in allowed:
                    issues.append(
                        {
                            "path": f"{path}.{key}",
                            "code": "additional_property",
                            "message": f"Field `{key}` is not declared in the contract.",
                        }
                    )

    for child in contract.get("allOf", []) if isinstance(contract.get("allOf"), list) else []:
        issues.extend(contract_issues(value, child, path, root_schema))
    return issues


def contract_checklist(contract: Any) -> dict[str, Any]:
    required = contract_required_fields(contract)
    properties: list[dict[str, Any]] = []

    def walk(schema: Any, path: str) -> None:
        if not isinstance(schema, dict):
            return
        child_properties = schema.get("properties")
        if isinstance(child_properties, dict):
            required_children = schema.get("required") if isinstance(schema.get("required"), list) else []
            for key, child in child_properties.items():
                child_path = f"{path}.{key}" if path else str(key)
                properties.append(
                    {
                        "path": child_path,
                        "type": child.get("type") if isinstance(child, dict) else None,
                        "required": key in required_children,
                        "enum": child.get("enum") if isinstance(child, dict) else None,
                        "items_type": (
                            child.get("items", {}).get("type")
                            if isinstance(child, dict) and isinstance(child.get("items"), dict)
                            else None
                        ),
                    }
                )
                walk(child, child_path)

    walk(contract, "$")
    return {"required_top_level": required, "properties": properties}



def infer_case_id(case: Any, fallback: str = "unknown-case") -> Any:
    if isinstance(case, dict):
        for key in (
            "case_id",
            "caseId",
            "task_id",
            "taskId",
            "challenge_id",
            "challengeId",
            "id",
        ):
            value = case.get(key)
            if value not in (None, ""):
                return value
    return fallback


def resolve_path(raw: str, input_root: Path, case_dir: Path) -> Path | None:
    candidate = Path(raw)
    candidates = [candidate]
    if not candidate.is_absolute():
        candidates.extend([input_root / candidate, case_dir / candidate])
    for item in candidates:
        try:
            resolved = item.expanduser().resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


def path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_relpath(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def extract_declared_metadata(case: Any) -> dict[str, Any]:
    if not isinstance(case, dict):
        return {}
    result: dict[str, Any] = {}
    for key in ("paper", "source", "metadata", "document", "publication"):
        value = case.get(key)
        if isinstance(value, dict):
            result.update(value)
    return result


def extract_doi(*values: Any) -> str | None:
    joined = " ".join(str(value) for value in values if value is not None)
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", joined)
    return match.group(0).rstrip(".,;") if match else None


def extract_year(*values: Any) -> int | None:
    joined = " ".join(str(value) for value in values if value is not None)
    years = [int(item) for item in re.findall(r"\b(19\d{2}|20\d{2})\b", joined)]
    return max(years) if years else None


def collect_questions(case: Any, limit: int = 80) -> list[dict[str, Any]]:
    keys = {
        "question",
        "questions",
        "query",
        "queries",
        "prompt",
        "instructions",
        "instruction",
        "task",
        "requirements",
    }
    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(value: Any, path: str, parent_key: str = "") -> None:
        if len(found) >= limit:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{path}.{key}", str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]", parent_key)
        elif isinstance(value, str):
            key = parent_key.casefold()
            if key in keys:
                text = value.strip()
                if text and text not in seen:
                    seen.add(text)
                    found.append({"path": path, "key": parent_key, "text": text})

    visit(case, "$")
    return found
def contract_scaffold(contract: Any, case_id: Any = None) -> Any:
    """Build a shape-only placeholder tree; never invent substantive answers."""
    if contract is None or contract is True or contract is False or not isinstance(contract, dict):
        return None
    if "const" in contract:
        return contract["const"]
    enum = contract.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]

    expected = contract.get("type")
    if isinstance(expected, list):
        expected = expected[0] if expected else None
    if expected == "object" or isinstance(contract.get("properties"), dict):
        required = contract.get("required") if isinstance(contract.get("required"), list) else []
        properties = contract.get("properties") if isinstance(contract.get("properties"), dict) else {}
        result: dict[str, Any] = {}
        for key in required:
            if key == "case_id" and case_id is not None:
                result[key] = case_id
            else:
                result[key] = contract_scaffold(properties.get(key, {}), case_id)
        return result
    if expected == "array" or "items" in contract:
        min_items = contract.get("minItems") if isinstance(contract.get("minItems"), int) else 0
        if min_items > 0:
            return [contract_scaffold(contract.get("items", {}), case_id) for _ in range(min_items)]
        return []
    if expected == "integer":
        return 0
    if expected == "number":
        return 0
    if expected == "boolean":
        return False
    if expected == "null":
        return None
    return ""

