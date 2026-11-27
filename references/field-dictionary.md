# 字段字典

## 1. 顶层字段

| 字段 | 类型 | 必需 | 含义 |
|---|---|---:|---|
| `schema_version` | string | 是 | 固定为 `nanopublication-result/1.1` |
| `case_id` | string/number | 是 | 必须与输入 `case.json` 中的案例标识类型和值一致 |
| `status` | enum | 是 | `success` / `partial` / `unable` / `refused` |
| `status_reason` | string | 是 | 完成程度、限制和人工接管点 |
| `task_result` | object | 是 | 对题目直接问题的答案或综合结论 |
| `nanopublications` | array | 是 | 原子断言、证据和来源的结构化集合 |
| `sources` | array | 是 | 实际读取的来源元数据和 SHA-256 |
| `unresolved` | array | 是 | 未报告、无法访问、无法判断或缺失字段 |
| `conflicts` | array | 是 | 材料之间或断言与证据之间的冲突 |
| `quality_report` | object | 是 | 机械校验统计，不替代科学评审 |
| `validation` | object | 是 | 校验状态、错误、警告和重复项 |
| `contract_validation` | object | 是 | 原始 `output_contract` 字段检查 |
| `input` | object | 是 | 案例路径、哈希和材料清单 |
| `output_contract` | any | 是 | 原样保留输入中的输出契约 |
| `artifact_manifest` | object | 是 | 输出路径、schema 哈希和证据行数 |
| `schema_validation` | object | 否 | 内部 JSON Schema 检查结果 |
| `change_log` | array | 是 | 版本、修复和结果变化记录 |
| `generated_at` | string | 是 | UTC ISO-8601 时间 |

如果案例契约要求额外字段，必须通过 `contract_fields` 以原字段名并入最终结果的顶层。不得翻译、重命名或省略契约字段。

## 2. Nanopublication 字段

| 字段 | 类型 | 必需 | 含义 |
|---|---|---:|---|
| `nanopub_id` | string | 是 | 稳定标识符；由断言、主体、关系、客体生成 |
| `assertion` | object | 是 | 单一、可独立判断真假的科学断言 |
| `evidence` | array | 是 | 支撑、反驳或限定该断言的最小证据片段 |
| `sources` | array | 是 | 该断言实际依赖的来源元数据 |
| `confidence` | object | 是 | 置信度与依据，不得只写一个无依据的模型分数 |
| `lineage` | object | 是 | 父子关系、替代关系和去重键 |
| `validation` | object | 是 | 本条断言的机械校验结果 |

## 3. Assertion 字段

| 字段 | 类型 | 必需 | 规则 |
|---|---|---:|---|
| `text` | string | 是 | 一个可独立判断真假的断言，不是整段摘要 |
| `subject` | object | 是 | 主体；建议含 `name` 和 `type` |
| `relation` | string | 是 | 必须来自受控关系词表 |
| `relation_detail` | string | 条件 | 仅当 `relation=other` 时填写具体关系 |
| `object` | object | 是 | 客体；与主体方向不能颠倒 |
| `claim_type` | enum | 是 | `empirical` / `causal` / `comparative` / `descriptive` / `methodological` / `negative` / `association` / `limitation` |
| `polarity` | enum | 是 | `supports` / `refutes` / `inconclusive` / `not_applicable` |
| `conditions` | array | 是 | 时间、浓度、样本、对照、实验条件、适用范围 |
| `quantifiers` | array | 是 | 数值、样本量、效应量、置信区间、统计量 |

## 4. Evidence 字段

| 字段 | 类型 | 必需 | 规则 |
|---|---|---:|---|
| `evidence_id` | string | 是 | 稳定证据标识符 |
| `source_id` | string | 是 | 必须对应 `sources.json` 中的来源 |
| `page` | integer/null | 是 | PDF 页码；纯文本可为 1 或 `null` |
| `block_id` | string/null | 是 | 对应 `source_units.jsonl` 的块 |
| `char_start` | integer | 是 | 证据在页面全文中的起始字符偏移 |
| `char_end` | integer | 是 | 证据在页面全文中的结束字符偏移 |
| `quote` | string | 是 | 与来源逐字或经空白规范化后可定位的引文 |
| `relation_to_claim` | enum | 是 | `direct_support` / `indirect_support` / `context` / `contradiction` / `complementary` |
| `minimality` | enum | 是 | `minimal` / `expanded_for_context` / `unresolved` |
| `match` | enum | 是 | `exact` / `whitespace_normalized` / `fuzzy` / `unresolved` |
| `sufficiency_rationale` | string | 是 | 说明该片段为什么足以支持或反驳断言 |
| `locator` | object | 是 | 来源、页码、块和字符区间的机器可读定位 |

## 5. Source 字段

| 字段 | 类型 | 规则 |
|---|---|---|
| `source_id` | string | 运行内稳定 ID，如 `src01` |
| `path` | string | 实际读取的路径 |
| `relative_path` | string | 相对输入根目录的路径 |
| `kind` | string | `pdf` / `docx` / `text` / `image` |
| `role` | string | `paper` / `supplement` / `figure` / `table` / `data` / `material` |
| `sha256` | string | 来源文件内容哈希 |
| `title` | string/null | 仅来自材料或案例元数据 |
| `authors` | array/string/null | 仅来自材料或案例元数据 |
| `year` | integer/null | 缺失时保留 `null` |
| `doi` | string/null | 仅在材料中有依据时填写 |
| `version` | string/null | 材料版本或案例版本 |
| `needs_ocr_pages` | array | 仍依赖 OCR 的页码 |

## 6. 状态判定

- `success`：题目要求的全部主结果已完成，关键断言均有可定位证据，契约字段完整。
- `partial`：有真实结果，但仍有 OCR、缺页、证据不足、字段缺失或人工复核项。
- `unable`：材料无法读取，或关键输入无法获得，不能负责任地生成主结果。
- `refused`：请求超出输入材料、需要编造、需要违反平台规则或无法安全回答。

## 7. 不可接受字段写法

- 断言字段写成整段摘要或整篇结论。
- 证据字段只有论文标题、引用编号或“见原文”。
- 页码、段落或字符区间由模型猜测。
- 把 `correlation` 写成 `causes`。
- 把未报告写成阴性结果。
- 把没有 DOI 的论文补造 DOI。
- 把多个来源的不同结论塞进一个来源字段。
- 只给模型自评置信度，不给证据依据。
- 用示例文本冒充正式案例输出。
