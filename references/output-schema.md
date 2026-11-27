# 输出结构规范

## 1. 根对象

```json
{
  "schema_version": "nanopublication-result/1.1",
  "case_id": "string-or-number",
  "status": "success",
  "status_reason": "string",
  "task_result": {},
  "nanopublications": [],
  "sources": [],
  "unresolved": [],
  "conflicts": [],
  "quality_report": {},
  "validation": {},
  "contract_validation": {},
  "input": {},
  "output_contract": {},
  "change_log": [],
    "artifact_manifest": {},
    "schema_validation": {},
  "generated_at": "YYYY-MM-DDTHH:MM:SS+00:00"
}
```

`case_id` 类型与输入保持一致；如果输入是数字而结果统一写成字符串，必须在 `input.case_id_original` 保留原值。

## 2. `task_result`
## 1.1 `artifact_manifest` and schema checks

`artifact_manifest` records the output paths, result schema hash, schema version and evidence row count. `schema_validation` records the internal contract check. Neither field is a substitute for case-specific `output_contract` validation.

用于回答案例直接提出的问题，不替代 `nanopublications`。

```json
{
  "direct_answer": "简洁答案",
  "structured_result": {},
  "limitations": []
}
```

如果 `output_contract` 规定其他字段，以契约字段名为准，并同时放入 `contract_fields` 供最终器提升到顶层。

## 3. `nanopublications`

```json
[
  {
    "nanopub_id": "np-0123456789ab",
    "assertion": {
      "text": "Single falsifiable claim.",
      "subject": {"name": "subject", "type": "intervention"},
      "relation": "decreases",
      "object": {"name": "object", "type": "measurement"},
      "claim_type": "empirical",
      "polarity": "supports",
      "conditions": ["24 h"],
      "quantifiers": ["18%", "p = 0.03"]
    },
    "evidence": [
      {
        "evidence_id": "ev-0123456789ab",
        "source_id": "src01",
        "page": 3,
        "block_id": "src01:p0003:b0004",
        "char_start": 120,
        "char_end": 286,
        "quote": "Verbatim source quote.",
        "relation_to_claim": "direct_support",
        "minimality": "minimal",
        "match": "exact",
        "sufficiency_rationale": "Why this span supports the assertion.",
        "locator": {
          "source_id": "src01",
          "page": 3,
          "block_id": "src01:p0003:b0004",
          "char_start": 120,
          "char_end": 286
        }
      }
    ],
    "sources": [
      {
        "source_id": "src01",
        "title": null,
        "authors": null,
        "year": null,
        "doi": null,
        "sha256": "..."
      }
    ],
    "confidence": {
      "score": null,
      "basis": ["exact_evidence_match", "source_scope_checked"]
    },
    "lineage": {
      "parent_nanopub_id": null,
      "supersedes": [],
      "duplicate_of": null,
      "dedupe_key": "..."
    },
    "validation": {
      "errors": [],
      "warnings": [],
      "evidence_exact": true
    }
  }
]
```

## 4. `sources`

来源元数据必须反映实际输入。无法确认时使用 `null`，不得补造。

```json
{
  "source_id": "src01",
  "path": "/input/paper.pdf",
  "relative_path": "paper.pdf",
  "kind": "pdf",
  "role": "paper",
  "sha256": "...",
  "title": null,
  "authors": null,
  "year": null,
  "doi": null,
  "journal": null,
  "version": null,
  "pages": 14,
  "needs_ocr_pages": []
}
```

## 5. `unresolved`

```json
[
  {
    "type": "missing_evidence",
    "target": "assertion or requested field",
    "reason": "No source span supports the claim.",
    "source_id": "src01",
    "page": 7,
    "human_action": "Check the figure caption or supplementary file."
  }
]
```

允许的 `type` 包括：

- `missing_evidence`
- `ocr_required`
- `source_inaccessible`
- `ambiguous_relation`
- `conflicting_evidence`
- `missing_output_field`
- `unsupported_schema`
- `partial_coverage`
- `manual_review`

## 6. `conflicts`

```json
[
  {
    "type": "direction_conflict",
    "assertion_ref": "np-...",
    "evidence_refs": ["ev-...", "ev-..."],
    "description": "Source A reports an increase; source B reports no change.",
    "resolution": "Reported as inconclusive and referred for human review."
  }
]
```

## 7. `quality_report`

至少包含：

- `claim_count`
- `evidence_count`
- `exact_evidence_rate`
- `claims_with_compound_flags`
- `atomicity_flag_rate`
- `source_count`
- `unresolved_count`
- `validation_status`
- `errors_count`
- `warnings_count`
- `mechanical_checks_only`
- `semantic_review_required`

## 8. 序列化约束

- UTF-8，无 BOM 更佳。
- 顶层和数组字段必须是 JSON 原生类型。
- 不使用 NaN、Infinity、Python `None` 或未加引号的日期。
- 不输出尾随注释或自然语言包围 JSON。
- 数值保留来源精度；不要为了格式美观四舍五入。
- 证据引文中的换行可保留在字符串转义中，但不要改动语义。

## 9. 契约优先规则

如果输入 `output_contract` 要求：

- `required`：最终结果顶层必须包含全部字段。
- `properties`：字段类型应匹配。
- `fields`：按字段名和顺序保留。
- 其他自定义结构：原样放入 `contract_fields`，最终器会提升到结果顶层。

`finalize_result.py` 会把缺失契约字段写入 `contract_validation.errors`，并把错误的 `success` 降级为 `partial`。
