#!/usr/bin/env python3
"""Mechanically validate atomic claims, evidence alignment and source locators."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from nanopub_common import (
    clause_markers,
    association_markers,
    comparative_markers,
    causal_markers,
    coerce_list,
    compact_text,
    content_terms,
    has_negation,
    load_json,
    locate_quote,
    object_name,
    overlap_ratio,
    quantities,
    sentence_count,
    sha256_file,
    sha256_text,
    similarity,
    stable_id,
    utc_now,
    write_json,
)


ALLOWED_CLAIM_TYPES = {
    "empirical",
    "causal",
    "comparative",
    "descriptive",
    "methodological",
    "negative",
    "association",
    "limitation",
}
ALLOWED_EVIDENCE_RELATIONS = {
    "direct_support",
    "indirect_support",
    "context",
    "contradiction",
    "complementary",
}
ALLOWED_POLARITY = {"supports", "refutes", "inconclusive", "not_applicable"}
ALLOWED_MINIMALITY = {"minimal", "expanded_for_context", "unresolved"}
SCOPE_CUES = (
    "in vitro",
    "in vivo",
    "ex vivo",
    "in mice",
    "in rats",
    "in humans",
    "participants",
    "patients",
    "cell line",
    "subgroup",
    "dose range",
    "concentration range",
    "tested range",
    "at ph ",
    "at room temperature",
    "under ",
    "among ",
    "in this cohort",
    "in this study",
    "only in",
)


def scope_markers(text: str) -> list[str]:
    lowered = f" {compact_text(text).casefold()} "
    return [cue.strip() for cue in SCOPE_CUES if cue in lowered]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, help="Draft result JSON")
    parser.add_argument("--work", default="/app/work", help="Directory from prepare_case.py")
    parser.add_argument(
        "--vocabulary",
        default=str(Path(__file__).resolve().parent.parent / "references" / "relation-vocabulary.json"),
    )
    parser.add_argument("--out", default=None, help="Validation JSON path")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero on validation errors")
    return parser.parse_args()


def normalize_subject(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {"name": compact_text(value), "type": "unspecified"}


def normalize_relation(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("canonical") or value.get("type") or value.get("label")
    return compact_text(value).casefold().replace(" ", "_")


def normalize_evidence_list(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in coerce_list(value):
        if isinstance(item, str):
            result.append({"quote": item})
        elif isinstance(item, dict):
            result.append(dict(item))
    return result


def normalize_claims(draft: Any) -> list[dict[str, Any]]:
    if not isinstance(draft, dict):
        return []
    raw = draft.get("nanopublications")
    if raw is None:
        raw = draft.get("claims")
    if raw is None and isinstance(draft.get("task_result"), dict):
        raw = draft["task_result"].get("nanopublications")
    return [dict(item) for item in coerce_list(raw) if isinstance(item, dict)]


def page_texts(source: dict[str, Any]) -> dict[int, str]:
    return {
        int(page.get("page") or 1): page.get("text", "")
        for page in source.get("pages", [])
        if page.get("page") is not None
    }


def number_signatures(text: str) -> set[str]:
    signatures: set[str] = set()
    for value in quantities(text):
        for number in re.findall(r"\d+(?:\.\d+)?", value):
            try:
                normalized = format(float(number), ".12g")
            except ValueError:
                normalized = number
            signatures.add(normalized)
    return signatures


def best_unit_match(quote: str, units: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], float] | None:
    best: tuple[dict[str, Any], dict[str, Any], float] | None = None
    for unit in units:
        location = locate_quote(unit.get("text", ""), quote)
        if location:
            score = 1.0 if location["match"] == "exact" else 0.99
            return unit, location, score
        score = similarity(unit.get("text", ""), quote)
        if best is None or score > best[2]:
            best = (unit, {}, score)
    if best and best[2] >= 0.88:
        return best
    return None


def build_source_index(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(source["source_id"]): source for source in sources}


def validate_claim(
    claim: dict[str, Any],
    claim_index: int,
    source_by_id: dict[str, dict[str, Any]],
    units_by_source: dict[str, list[dict[str, Any]]],
    relation_vocabulary: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    normalized = dict(claim)
    assertion = claim.get("assertion")
    if not isinstance(assertion, dict):
        assertion = {"text": compact_text(assertion)}
    assertion = dict(assertion)
    claim_text = compact_text(assertion.get("text") or claim.get("claim") or claim.get("text"))
    subject = normalize_subject(assertion.get("subject") or claim.get("subject"))
    obj = normalize_subject(assertion.get("object") or claim.get("object"))
    relation = normalize_relation(assertion.get("relation") or claim.get("relation"))
    claim_type = compact_text(assertion.get("claim_type") or claim.get("claim_type") or "empirical").casefold()
    polarity = compact_text(assertion.get("polarity") or claim.get("polarity") or "supports").casefold()

    claim_id = compact_text(claim.get("nanopub_id") or claim.get("claim_id"))
    if not claim_id:
        claim_id = stable_id("np", "|".join([claim_text, object_name(subject), relation, object_name(obj)]))
    if not claim_text:
        errors.append({"code": "missing_assertion_text", "message": "assertion.text is required"})
    if not object_name(subject):
        errors.append({"code": "missing_subject", "message": "assertion.subject is required"})
    if not object_name(obj):
        errors.append({"code": "missing_object", "message": "assertion.object is required"})
    if not relation:
        errors.append({"code": "missing_relation", "message": "assertion.relation is required"})
    elif relation not in relation_vocabulary:
        errors.append(
            {
                "code": "unmapped_relation",
                "message": f"relation `{relation}` is not in the controlled vocabulary",
                "allowed": sorted(relation_vocabulary),
            }
        )
    if claim_type not in ALLOWED_CLAIM_TYPES:
        errors.append(
            {
                "code": "invalid_claim_type",
                "message": f"claim_type `{claim_type}` is not allowed",
                "allowed": sorted(ALLOWED_CLAIM_TYPES),
            }
        )
    if polarity not in ALLOWED_POLARITY:
        errors.append(
            {
                "code": "invalid_polarity",
                "message": f"polarity `{polarity}` is not allowed",
                "allowed": sorted(ALLOWED_POLARITY),
            }
        )

    if relation == "other" and not compact_text(assertion.get("relation_detail") or claim.get("relation_detail")):
        errors.append(
            {
                "code": "missing_relation_detail",
                "message": "assertion.relation_detail is required when relation is `other`.",
            }
        )

    markers = clause_markers(claim_text)
    if len(claim_text) > 420:
        warnings.append(
            {
                "code": "assertion_too_long",
                "message": "Assertion exceeds 420 characters; check whether it contains multiple claims.",
                "length": len(claim_text),
            }
        )
    if markers:
        warnings.append(
            {
                "code": "possible_compound_claim",
                "message": "Compound-clause markers found; confirm this is one independently falsifiable assertion.",
                "markers": markers,
            }
        )

    raw_evidence = claim.get("evidence")
    evidence_items = normalize_evidence_list(raw_evidence)
    if not evidence_items:
        errors.append({"code": "missing_evidence", "message": "At least one evidence item is required"})

    validated_evidence: list[dict[str, Any]] = []
    for evidence_index, evidence in enumerate(evidence_items, start=1):
        quote = compact_text(evidence.get("quote") or evidence.get("text"))
        item_errors: list[dict[str, Any]] = []
        if not quote:
            errors.append(
                {
                    "code": "missing_evidence_quote",
                    "message": "evidence.quote is required",
                    "evidence_index": evidence_index,
                }
            )
            continue

        source_id = compact_text(evidence.get("source_id"))
        candidate_units: list[dict[str, Any]] = []
        if source_id:
            if source_id not in source_by_id:
                errors.append(
                    {
                        "code": "unknown_source_id",
                        "message": f"source_id `{source_id}` does not exist",
                        "evidence_index": evidence_index,
                    }
                )
                continue
            candidate_units = units_by_source.get(source_id, [])
        else:
            candidate_units = [unit for source_units in units_by_source.values() for unit in source_units]

        match = best_unit_match(quote, candidate_units)
        location: dict[str, Any] = {}
        matched_unit: dict[str, Any] | None = None
        match_score = 0.0
        if match:
            matched_unit, location, match_score = match

        if match_score < 0.88 or matched_unit is None:
            errors.append(
                {
                    "code": "evidence_not_found",
                    "message": "Evidence quote could not be located in the supplied material.",
                    "evidence_index": evidence_index,
                    "quote_preview": quote[:240],
                }
            )
            continue

        if not source_id:
            source_id = str(matched_unit["source_id"])
        source = source_by_id[source_id]
        page_number = evidence.get("page")
        if page_number is not None:
            try:
                page_number = int(page_number)
            except (TypeError, ValueError):
                page_number = None
        if page_number is not None and matched_unit.get("page") is not None:
            if int(matched_unit["page"]) != page_number:
                warnings.append(
                    {
                        "code": "page_locator_corrected",
                        "message": f"Evidence page was {page_number}; match is on page {matched_unit['page']}.",
                        "evidence_index": evidence_index,
                    }
                )
        page_number = matched_unit.get("page")

        if location.get("match") == "exact":
            evidence_match = "exact"
        elif location.get("match") == "whitespace_normalized":
            evidence_match = "whitespace_normalized"
        elif match_score >= 0.88:
            evidence_match = "fuzzy"
            warnings.append(
                {
                    "code": "fuzzy_evidence_match",
                    "message": "Evidence is only a fuzzy match; copy the exact source quote before finalizing.",
                    "evidence_index": evidence_index,
                    "similarity": round(match_score, 4),
                }
            )
        else:
            evidence_match = "unresolved"

        relation_to_claim = compact_text(evidence.get("relation_to_claim") or "direct_support").casefold()
        if relation_to_claim not in ALLOWED_EVIDENCE_RELATIONS:
            errors.append(
                {
                    "code": "invalid_evidence_relation",
                    "message": f"relation_to_claim `{relation_to_claim}` is not allowed",
                    "allowed": sorted(ALLOWED_EVIDENCE_RELATIONS),
                    "evidence_index": evidence_index,
                }
            )
        minimality = compact_text(evidence.get("minimality") or "minimal").casefold()
        if minimality not in ALLOWED_MINIMALITY:
            errors.append(
                {
                    "code": "invalid_minimality",
                    "message": f"minimality `{minimality}` is not allowed",
                    "allowed": sorted(ALLOWED_MINIMALITY),
                    "evidence_index": evidence_index,
                }
            )
        if len(quote) > 500 or sentence_count(quote) > 2:
            warnings.append(
                {
                    "code": "evidence_not_minimal",
                    "message": "Evidence quote is long; reduce it to the smallest sufficient span.",
                    "evidence_index": evidence_index,
                    "characters": len(quote),
                    "sentences": sentence_count(quote),
                }
            )

        page_full_text = page_texts(source).get(int(page_number or 1), "")
        page_location = locate_quote(page_full_text, quote) if page_full_text else None
        if page_location:
            full_start = page_location["start"]
            full_end = page_location["end"]
        else:
            full_start = matched_unit.get("char_start", 0) + location.get("start", 0)
            full_end = matched_unit.get("char_start", 0) + location.get("end", len(quote))

        item = dict(evidence)
        item.update(
            {
                "evidence_id": compact_text(evidence.get("evidence_id"))
                or stable_id("ev", f"{claim_id}|{source_id}|{page_number}|{full_start}|{full_end}"),
                "source_id": source_id,
                "quote": quote,
                "page": page_number,
                "block_id": matched_unit.get("unit_id"),
                "block_kind": matched_unit.get("block_kind"),
                "char_start": full_start,
                "char_end": full_end,
                "match": evidence_match,
                "similarity": round(match_score, 4),
                "relation_to_claim": relation_to_claim,
                "minimality": minimality,
                "sufficiency_rationale": compact_text(evidence.get("sufficiency_rationale")),
                "locator": {
                    "source_id": source_id,
                    "page": page_number,
                    "block_id": matched_unit.get("unit_id"),
                    "char_start": full_start,
                    "char_end": full_end,
                },
            }
        )
        if relation_to_claim in {"direct_support", "contradiction", "complementary"} and len(
            item["sufficiency_rationale"]
        ) < 18:
            warnings.append(
                {
                    "code": "missing_sufficiency_rationale",
                    "message": "Explain why this exact span is sufficient for the assertion.",
                    "evidence_index": evidence_index,
                }
            )
        if item_errors:
            errors.extend(item_errors)
        validated_evidence.append(item)

    evidence_text = " ".join(item["quote"] for item in validated_evidence)
    required_quantities = assertion.get("quantifiers") or claim.get("quantifiers") or []
    required_numeric_text = " ".join(
        [claim_text, *[compact_text(value) for value in coerce_list(required_quantities)]]
    )
    missing_numbers = sorted(number_signatures(required_numeric_text) - number_signatures(evidence_text))
    if missing_numbers:
        warnings.append(
            {
                "code": "numeric_fidelity_risk",
                "message": "Numbers in the assertion or quantifiers were not found in the bound evidence.",
                "missing_values": missing_numbers,
            }
        )

    claim_negated = has_negation(claim_text)
    evidence_negated = has_negation(evidence_text)
    if claim_negated and not evidence_negated:
        warnings.append(
            {
                "code": "unsupported_negation",
                "message": "The assertion is negated but the bound evidence has no negation cue.",
            }
        )
    elif evidence_negated and not claim_negated and relation in {"increases", "decreases", "inhibits", "causes"}:
        warnings.append(
            {
                "code": "negation_scope_risk",
                "message": "The evidence contains negation but the directional assertion does not preserve it.",
            }
        )

    evidence_association = association_markers(evidence_text)
    evidence_causal = causal_markers(evidence_text)
    if relation == "causes" or claim_type == "causal":
        if evidence_association and not evidence_causal:
            errors.append(
                {
                    "code": "unsupported_causal_strength",
                    "message": "Evidence uses association or hedging language; a causal assertion is not supported.",
                    "markers": evidence_association,
                }
            )
        elif not evidence_causal:
            warnings.append(
                {
                    "code": "causal_strength_needs_review",
                    "message": "No explicit causal cue was found; verify that the study design supports causality.",
                }
            )

    subject_object_terms = list(
        dict.fromkeys(content_terms(object_name(subject)) + content_terms(object_name(obj)))
    )
    entity_overlap = overlap_ratio(subject_object_terms, evidence_text) if subject_object_terms else 0.0
    if validated_evidence and entity_overlap < 0.15:
        warnings.append(
            {
                "code": "subject_object_low_overlap",
                "message": "Subject/object wording has low overlap with the evidence; check entity substitution or reversal.",
                "overlap": round(entity_overlap, 4),
            }
        )

    conditions = assertion.get("conditions") or claim.get("conditions") or []
    if not isinstance(conditions, list):
        errors.append({"code": "invalid_conditions", "message": "assertion.conditions must be an array."})
    if not isinstance(required_quantities, list):
        errors.append({"code": "invalid_quantifiers", "message": "assertion.quantifiers must be an array."})

    claim_comparative = comparative_markers(claim_text)
    evidence_comparative = comparative_markers(evidence_text)
    if validated_evidence and (claim_type == "comparative" or claim_comparative):
        if not evidence_comparative:
            warnings.append(
                {
                    "code": "missing_comparator",
                    "message": "Comparative claim has no explicit comparator or baseline cue in its evidence.",
                }
            )

    evidence_scope = scope_markers(evidence_text)
    claim_scope = scope_markers(claim_text)
    missing_scope = sorted(set(evidence_scope) - set(claim_scope))
    condition_overlap: dict[str, float] = {}
    if validated_evidence and isinstance(conditions, list):
        for condition in conditions:
            condition_text = compact_text(condition)
            condition_terms = content_terms(condition_text)
            if not condition_text or not condition_terms:
                continue
            score = overlap_ratio(condition_terms, evidence_text)
            condition_overlap[condition_text] = round(score, 4)
            if score < 0.34:
                warnings.append(
                    {
                        "code": "scope_not_preserved",
                        "message": "An assertion condition is not visibly preserved in the bound evidence.",
                        "condition": condition_text,
                        "overlap": round(score, 4),
                    }
                )
    if validated_evidence and missing_scope:
        warnings.append(
            {
                "code": "scope_not_preserved",
                "message": "The evidence carries scope qualifiers that the assertion does not preserve.",
                "evidence_scope": evidence_scope,
                "claim_scope": claim_scope,
            }
        )

    semantic_checks = {
        "entity_overlap": round(entity_overlap, 4),
        "numbers_required": sorted(number_signatures(required_numeric_text)),
        "numbers_missing": missing_numbers,
        "claim_negated": claim_negated,
        "evidence_negated": evidence_negated,
        "evidence_association_markers": evidence_association,
        "evidence_causal_markers": evidence_causal,
        "claim_comparative_markers": claim_comparative,
        "evidence_comparative_markers": evidence_comparative,
        "evidence_scope_markers": evidence_scope,
        "claim_scope_markers": claim_scope,
        "missing_scope_markers": missing_scope,
        "condition_overlap": condition_overlap,
    }

    if not validated_evidence and evidence_items:
        errors.append(
            {
                "code": "no_usable_evidence",
                "message": "No supplied evidence item could be aligned to a source location.",
            }
        )

    source_ids = sorted({item["source_id"] for item in validated_evidence})
    source_metadata = []
    for source_id in source_ids:
        source = source_by_id[source_id]
        metadata = source.get("metadata", {})
        missing = [key for key in ("title", "authors", "year") if not metadata.get(key)]
        if missing:
            warnings.append(
                {
                    "code": "incomplete_source_metadata",
                    "message": "Source metadata is incomplete; do not invent it.",
                    "source_id": source_id,
                    "missing": missing,
                }
            )
        source_metadata.append(
            {
                "source_id": source_id,
                "path": source.get("path"),
                "relative_path": source.get("relative_path"),
                "kind": source.get("kind"),
                "role": source.get("role"),
                "title": metadata.get("title"),
                "authors": metadata.get("authors"),
                "year": metadata.get("year"),
                "doi": metadata.get("doi"),
                "version": metadata.get("version"),
                "pages": len(source.get("pages", [])),
                "needs_ocr_pages": [
                    page.get("page")
                    for page in source.get("pages", [])
                    if page.get("needs_ocr")
                ],
                "sha256": source.get("sha256"),
            }
        )

    normalized.update(
        {
            "nanopub_id": claim_id,
            "assertion": {
                **assertion,
                "text": claim_text,
                "subject": subject,
                "relation": relation,
                "object": obj,
                "claim_type": claim_type,
                "polarity": polarity,
                "conditions": assertion.get("conditions") or claim.get("conditions") or [],
                "quantifiers": assertion.get("quantifiers") or claim.get("quantifiers") or [],
            },
            "evidence": validated_evidence,
            "sources": source_metadata,
            "semantic_checks": semantic_checks,
            "confidence": claim.get("confidence")
            or {
                "score": None,
                "basis": ["mechanical_evidence_match_only", "semantic_judgement_required"],
            },
            "lineage": claim.get("lineage")
            or {
                "parent_nanopub_id": None,
                "supersedes": [],
                "duplicate_of": None,
                "dedupe_key": sha256_text(
                    "|".join([claim_text.casefold(), object_name(subject), relation, object_name(obj)])
                ),
            },
            "validation": {
                "errors": errors,
                "warnings": warnings,
                "evidence_exact": all(item["match"] in {"exact", "whitespace_normalized"} for item in validated_evidence),
            },
        }
    )
    return normalized, errors, warnings


def apply_source_metadata_overrides(
    sources: list[dict[str, Any]], draft: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    overrides = draft.get("source_metadata") if isinstance(draft, dict) else None
    if not isinstance(overrides, dict):
        return errors, warnings
    allowed = {"title", "authors", "year", "doi", "journal", "version", "license", "url"}
    for source in sources:
        source_id = str(source.get("source_id"))
        values = overrides.get(source_id)
        if values is None:
            continue
        if not isinstance(values, dict):
            errors.append({"code": "invalid_source_metadata", "source_id": source_id, "message": "source_metadata entries must be objects."})
            continue
        metadata = source.setdefault("metadata", {})
        source_text = "\n".join(str(page.get("text") or "") for page in source.get("pages", []))
        for key, value in values.items():
            if key not in allowed:
                warnings.append({"code": "unknown_source_metadata_field", "source_id": source_id, "field": key})
                continue
            if value in (None, "", []):
                continue
            if key == "year" and not isinstance(value, int):
                errors.append({"code": "invalid_metadata_year", "source_id": source_id, "message": "year must be an integer."})
                continue
            metadata[key] = value
            search_value = ", ".join(str(item) for item in value) if isinstance(value, list) else str(value)
            if key in {"title", "authors", "year", "doi", "journal"} and not locate_quote(source_text, search_value):
                warnings.append(
                    {
                        "code": "metadata_not_verbatim_in_source",
                        "message": "Metadata override was not found verbatim in the source text; cite its origin or remove it.",
                        "source_id": source_id,
                        "field": key,
                    }
                )
    return errors, warnings


def main() -> int:
    args = parse_args()
    draft_path = Path(args.draft).expanduser().resolve()
    work = Path(args.work).expanduser().resolve()
    draft = load_json(draft_path)
    manifest = load_json(work / "case_manifest.json")
    sources_document = load_json(work / "sources.json")
    sources = sources_document.get("sources", [])
    units: list[dict[str, Any]] = []
    with (work / "source_units.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                units.append(json.loads(line))
    vocabulary_document = load_json(args.vocabulary)
    relation_vocabulary = {
        key: value for key, value in vocabulary_document.items() if not key.startswith("_")
    }

    source_by_id = build_source_index(sources)
    units_by_source: dict[str, list[dict[str, Any]]] = {}
    for unit in units:
        units_by_source.setdefault(str(unit["source_id"]), []).append(unit)

    metadata_errors, metadata_warnings = apply_source_metadata_overrides(sources, draft)
    # Persist validated metadata overrides so finalize_result.py reads the same
    # source registry that the validator checked, instead of stale prepare output.
    write_json(
        work / "sources.json",
        {
            "generated_at": utc_now(),
            "sources": sources,
            "metadata_validation": {
                "errors": metadata_errors,
                "warnings": metadata_warnings,
            },
        },
    )
    claims = normalize_claims(draft)
    validated_claims: list[dict[str, Any]] = []
    all_errors: list[dict[str, Any]] = []
    all_warnings: list[dict[str, Any]] = []
    all_errors.extend(metadata_errors)
    all_warnings.extend(metadata_warnings)
    dedupe: dict[str, str] = {}
    duplicates: list[dict[str, Any]] = []

    for index, claim in enumerate(claims, start=1):
        normalized, errors, warnings = validate_claim(
            claim,
            index,
            source_by_id,
            units_by_source,
            relation_vocabulary,
        )
        for issue in errors:
            issue.setdefault("claim_index", index)
            issue.setdefault("nanopub_id", normalized.get("nanopub_id"))
        for issue in warnings:
            issue.setdefault("claim_index", index)
            issue.setdefault("nanopub_id", normalized.get("nanopub_id"))
        all_errors.extend(errors)
        all_warnings.extend(warnings)
        dedupe_key = normalized["lineage"]["dedupe_key"]
        if dedupe_key in dedupe:
            duplicates.append(
                {
                    "nanopub_id": normalized["nanopub_id"],
                    "duplicate_of": dedupe[dedupe_key],
                    "dedupe_key": dedupe_key,
                }
            )
        else:
            dedupe[dedupe_key] = normalized["nanopub_id"]
        validated_claims.append(normalized)

    if not claims:
        all_errors.append({"code": "no_nanopublications", "message": "Draft contains no nanopublications"})
    if duplicates:
        all_warnings.append(
            {
                "code": "duplicate_claims",
                "message": "Duplicate assertions were detected; merge them or document why they are separate.",
                "duplicates": duplicates,
            }
        )

    evidence_total = sum(len(item.get("evidence", [])) for item in validated_claims)
    exact_total = sum(
        1
        for item in validated_claims
        for evidence in item.get("evidence", [])
        if evidence.get("match") in {"exact", "whitespace_normalized"}
    )
    claims_with_compound_flags = sum(
        1
        for item in validated_claims
        if any(
            issue.get("code") == "possible_compound_claim"
            for issue in item.get("validation", {}).get("warnings", [])
        )
    )
    unresolved = draft.get("unresolved") or []
    claims_with_quantities = sum(
        1
        for item in validated_claims
        if number_signatures(
            " ".join(
                [
                    item.get("assertion", {}).get("text", ""),
                    *[compact_text(value) for value in item.get("assertion", {}).get("quantifiers", [])],
                ]
            )
        )
    )
    quantities_preserved = sum(
        1
        for item in validated_claims
        if number_signatures(
            " ".join(
                [
                    item.get("assertion", {}).get("text", ""),
                    *[compact_text(value) for value in item.get("assertion", {}).get("quantifiers", [])],
                ]
            )
        )
        and not item.get("semantic_checks", {}).get("numbers_missing")
    )
    rationale_ready = sum(
        1
        for item in validated_claims
        if all(
            len(compact_text(evidence.get("sufficiency_rationale"))) >= 18
            for evidence in item.get("evidence", [])
            if evidence.get("relation_to_claim") in {"direct_support", "contradiction", "complementary"}
        )
    )
    evidence_minimal = sum(
        1
        for item in validated_claims
        for evidence in item.get("evidence", [])
        if len(evidence.get("quote", "")) <= 500 and sentence_count(evidence.get("quote", "")) <= 2
    )
    risk_counts: dict[str, int] = {}
    for warning in all_warnings:
        code = str(warning.get("code", "unknown"))
        risk_counts[code] = risk_counts.get(code, 0) + 1

    status = "invalid" if all_errors else ("partial" if all_warnings or unresolved else "success")
    validation = {
        "schema_version": "nanopublication-validation/1.0",
        "validated_at": utc_now(),
        "draft_path": str(draft_path),
        "draft_sha256": sha256_file(draft_path),
        "case_id": manifest.get("case_id"),
        "status": status,
        "mechanical_checks_only": True,
        "semantic_review_required": True,
        "claims_count": len(validated_claims),
        "evidence_count": evidence_total,
        "errors": all_errors,
        "warnings": all_warnings,
        "duplicates": duplicates,
        "quality_report": {
            "claim_count": len(validated_claims),
            "evidence_count": evidence_total,
            "exact_evidence_rate": round(exact_total / evidence_total, 4) if evidence_total else 0.0,
            "claims_with_compound_flags": claims_with_compound_flags,
            "atomicity_flag_rate": round(claims_with_compound_flags / len(validated_claims), 4)
            if validated_claims
            else 0.0,
            "source_count": len({item for claim in validated_claims for item in [ev["source_id"] for ev in claim.get("evidence", [])]}),
            "unresolved_count": len(unresolved),
            "claims_with_quantities": claims_with_quantities,
            "quantity_preservation_rate": round(quantities_preserved / claims_with_quantities, 4)
            if claims_with_quantities
            else 1.0,
            "sufficiency_rationale_rate": round(rationale_ready / len(validated_claims), 4)
            if validated_claims
            else 0.0,
            "minimal_evidence_rate": round(evidence_minimal / evidence_total, 4) if evidence_total else 0.0,
            "semantic_risk_counts": risk_counts,
        },
    }

    out_path = Path(args.out).expanduser().resolve() if args.out else work / "validation.json"
    write_json(out_path, validation)
    write_json(
        work / "validated_claims.json",
        {
            "schema_version": "nanopublication-validated-claims/1.0",
            "case_id": manifest.get("case_id"),
            "validation_status": status,
            "nanopublications": validated_claims,
        },
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    if args.strict and all_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
