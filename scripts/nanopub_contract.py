"""JSON-Schema subset helpers for case output contracts."""

from __future__ import annotations

import re
from typing import Any


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


def resolve_local_ref(root_schema: Any, reference: str) -> Any:
    if not reference.startswith("#/"):
        return None
    target = root_schema
    for part in reference[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or part not in target:
            return None
        target = target[part]
    return target


def contract_issues(
    value: Any,
    contract: Any,
    path: str = "$",
    root_schema: Any = None,
) -> list[dict[str, Any]]:
    """Validate the JSON-Schema subset used by challenge contracts."""
    return _contract_issues(value, contract, path, root_schema, frozenset())


def _contract_issues(
    value: Any,
    contract: Any,
    path: str,
    root_schema: Any,
    seen_refs: frozenset[str],
) -> list[dict[str, Any]]:
    if root_schema is None:
        root_schema = contract
    if contract is None:
        return []
    if isinstance(contract, bool):
        if contract:
            return []
        return [{"path": path, "code": "schema_false", "message": "Value is forbidden by the contract."}]
    if not isinstance(contract, dict):
        return []

    reference = contract.get("$ref")
    if isinstance(reference, str):
        if reference in seen_refs:
            return [
                {
                    "path": path,
                    "code": "cyclic_ref",
                    "message": f"Schema reference cycle detected at {reference!r}.",
                }
            ]
        target = resolve_local_ref(root_schema, reference)
        if target is None:
            return [
                {
                    "path": path,
                    "code": "unresolved_ref",
                    "message": f"Schema reference {reference!r} could not be resolved.",
                }
            ]
        return _contract_issues(value, target, path, root_schema, seen_refs | {reference})

    issues: list[dict[str, Any]] = []
    if "const" in contract and value != contract["const"]:
        issues.append(
            {"path": path, "code": "const_mismatch", "message": f"Expected constant {contract['const']!r}."}
        )
    enum = contract.get("enum")
    if isinstance(enum, list) and value not in enum:
        issues.append({"path": path, "code": "enum_mismatch", "message": f"Value is not one of {enum!r}."})

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
                issues.extend(_contract_issues(child, item_contract, f"{path}[{index}]", root_schema, seen_refs))

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
                    issues.extend(
                        _contract_issues(value[key], child_contract, f"{path}.{key}", root_schema, seen_refs)
                    )
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
        issues.extend(_contract_issues(value, child, path, root_schema, seen_refs))
    for child in contract.get("anyOf", []) if isinstance(contract.get("anyOf"), list) else []:
        variants = [_contract_issues(value, child, path, root_schema, seen_refs) for child in contract["anyOf"]]
        if variants and all(variant for variant in variants):
            issues.append(
                {
                    "path": path,
                    "code": "any_of_mismatch",
                    "message": "Value does not satisfy any branch of anyOf.",
                }
            )
    for child in contract.get("oneOf", []) if isinstance(contract.get("oneOf"), list) else []:
        variants = [_contract_issues(value, child, path, root_schema, seen_refs) for child in contract["oneOf"]]
        if sum(1 for variant in variants if not variant) != 1:
            issues.append(
                {
                    "path": path,
                    "code": "one_of_mismatch",
                    "message": "Value must satisfy exactly one branch of oneOf.",
                }
            )
    return issues


def contract_required_fields(contract: Any) -> list[str]:
    """Return fields that must be present at the root of the contract."""
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
        "$ref",
        "title",
        "description",
        "type",
        "version",
        "notes",
        "required",
        "properties",
        "additionalproperties",
        "allof",
        "anyof",
        "oneof",
        "$defs",
        "definitions",
        "$comment",
        "deprecated",
        "examples",
        "readonly",
        "writeonly",
        "default",
        "const",
        "enum",
        "minproperties",
        "maxproperties",
        "patternproperties",
        "propertynames",
        "unevaluatedproperties",
        "dependentrequired",
        "dependentschemas",
    }
    return [
        str(key)
        for key in contract
        if str(key).casefold() not in metadata_keys and not str(key).startswith("_")
    ]


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
                        "min_items": child.get("minItems") if isinstance(child, dict) else None,
                        "max_items": child.get("maxItems") if isinstance(child, dict) else None,
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


def contract_scaffold(contract: Any, case_id: Any = None) -> Any:
    """Build a shape-only placeholder tree; never invent substantive answers."""
    if contract is None or isinstance(contract, bool) or not isinstance(contract, dict):
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
