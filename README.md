# Nanopublication Evidence Forge

一个面向科研阅读与知识结构化的可调用 Skill。它把论文或案例材料转换为原子、可验证、可回溯的 Nanopublication：

- 独立可判断真假的断言；
- 最小充分证据片段；
- 页码、块、字符区间定位；
- 论文/作者/年份/版本/哈希来源链；
- 机器可读 `result.json`；
- 错误、冲突、不确定性和人工接管点。

## 适用场景

- 将论文段落拆成科学断言；
- 为每条断言绑定原文证据；
- 生成可复核的 Nanopublication 数据；
- 校验已有断言是否过宽、无证据、方向错误或重复；
- 导出可被下游程序消费的结构化结果；
- 平台固定案例要求读取实际 PDF/DOCX/文本材料。

## 快速开始

```bash
SKILL_DIR="${SKILL_DIR:-/skills/weekly-skill}"
PYTHON_BIN="$(command -v python3 || command -v python)"
"$PYTHON_BIN" "$SKILL_DIR/scripts/prepare_case.py" \
  --case /input/case.json \
  --input-root /input \
  --work /app/work \
  --render-empty-pages

# 阅读 /app/work/case_brief.md、case_manifest.json、source_units.jsonl
# 根据实际材料完成 /app/work/draft_result.json

"$PYTHON_BIN" "$SKILL_DIR/scripts/validate_nanopubs.py" \
  --draft /app/work/draft_result.json \
  --work /app/work \
  --strict

"$PYTHON_BIN" "$SKILL_DIR/scripts/finalize_result.py" \
  --draft /app/work/draft_result.json \
  --work /app/work \
  --out /app/output/result.json
```

## 文件说明

```text
submission/
├── SKILL.md
├── README.md
├── runtime_probe.sh
├── GAIN.md
├── MINIMAL_USAGE.md
├── PREDICATES.md
├── MACHINE_VS_HUMAN.md
├── EXAMPLES.md
├── FIELDS.md
├── config/
│   └── defaults.json
├── references/
│   ├── assertion-rules.md
│   ├── evaluation-matrix.md
│   ├── field-dictionary.md
│   ├── output-schema.md
│   ├── relation-vocabulary.json
│   ├── reliability.md
│   └── verification-plan.md
├── scripts/
│   ├── nanopub_contract.py
│   ├── nanopub_common.py
│   ├── prepare_case.py
│   ├── merge_ocr.py
│   ├── validate_nanopubs.py
│   ├── finalize_result.py
│   ├── runtime_probe.py
│   ├── smoke_test.py
│   ├── regression_test.py
│   └── check_submission.py
└── examples/
    ├── README.md
    ├── assertion-samples.json
    ├── demo_case.json
    ├── demo_source.txt
    └── illustrative-output.json
```

## 方法
## 运行前检查

```bash
bash runtime_probe.sh --create-dirs
```

脚本只输出 JSON，不联网、不读取凭证。它检查 Python 版本、PDF 文本/渲染、OCR、DOCX 能力、输入文件以及 `/app/work`、`/app/output` 可写性。`blocked` 必须先修复；`partial` 表示应使用已声明的降级路径。


### 1. 契约优先

首先解析 `/input/case.json` 的 `output_contract`。最终 `result.json` 必须包含契约要求的字段，字段名不得翻译、缩写或改写。

### 2. 证据单元化

- PDF：按页抽取文本，保留页码和字符偏移。
- DOCX：按段落和表格行切分。
- 文本：按段落切分。
- 图片/扫描页：需要 OCR；无法可靠识别时进入 `unresolved`。

### 3. 原子断言

采用“主体 -> 关系 -> 客体”的结构。条件、时间、剂量、样本范围、统计量和方向必须保留。

### 4. 最小证据

优先单一完整句子或表格行。跨图表、跨页或需要上下文的证据拆成多个 evidence 项。

### 5. 机械校验

校验器检查：

- 受控关系；
- 必需字段；
- 证据可定位性；
- 页码/块/字符偏移；
- 可能的复合断言；
- 重复断言；
- 来源元数据完整性；
- 输出契约。

### 6. 最终封装

最终器检查草稿在校验后是否被修改，检查 `case_id` 与契约字段，输出：

- `result.json`
- `evidence_ledger.jsonl`
- `evidence_table.csv`
- `result_summary.md`

## 最小示例

`examples/` 中的内容全部是**合成示例**，不包含正式案例答案。

- `demo_source.txt`：虚构的 20 句研究材料；
- `assertion-samples.json`：20 条断言样例；
- `illustrative-output.json`：示意输出；
- `demo_case.json`：示意输入契约。

## 依赖

- Python 3.9+
- 可选：`pypdf`
- 可选：`python-docx`
- 可选：`pdftotext`、`pdftoppm`
- 可选：`tesseract` 或平台 OCR 工具

缺少可选 PDF 工具时，程序必须明确记录失败页，不得补造文本。

## 限制

- 机械校验不能证明科学结论为真。
- 复杂多栏 PDF 的文本顺序可能错误，必须结合页面图复核。
- OCR 公式、化学式、表格和上下标可能失真。
- 作者、年份、DOI 缺失时不补造。
- 断言关系仍需领域语义判断。
- 同一论文的不同版本必须作为不同来源记录。

## 异常边界

| 情况 | 处理 |
|---|---|
| PDF 无文本层 | 渲染、OCR、合并；否则 `partial` |
| 文件不可访问 | `unable`/`partial`，记录缺失路径 |
| 证据找不到 | `unresolved`，不得伪造定位 |
| 证据冲突 | `conflicts`，状态降级 |
| 跨图表 | 多个 evidence 项 |
| 输出字段缺失 | `contract_validation=failed`，状态降级 |
| 关系不在词表 | 校验失败，必须映射或标为 `other` |

## 自测

```bash
PYTHON_BIN="$(command -v python3 || command -v python)"
"$PYTHON_BIN" scripts/smoke_test.py
```

当前测试覆盖：

- 正例全流程；
- 契约字段提升；
- 不存在证据的负例；
- 负例不会被标记为 success；
- 草稿变更后的陈旧校验保护；
- 扫描页 OCR 文本合并与证据单元重建。
- 数值、范围、比较基线、否定和因果风险检测；
- 来源元数据持久化、OCR 合并后候选证据重建；
- 提交资源、UTF-8、符号链接和敏感路径检查。
- 空 OCR 文本降级和 `schema_validation` 契约字段检查；
- JSON 语法、SKILL frontmatter、20 条示例和运行环境探测。

## 维护

- 版本：`1.1.1`
- 词表版本：`1.1.0`
- 修改关系词表后，必须重跑 smoke test 和真实 PDF 页级测试。
- 新增字段时同步更新 `references/field-dictionary.md` 和 `references/output-schema.md`。
- 保持示例为合成内容，并明确标注。
- 不写入个人路径、Token、密码或平台私有材料。

### 1.1.1

- 增加离线运行时探测和目录可写性检查。
- OCR 合并后重建证据候选与作者工作表，空 OCR 明确降级。
- 来源元数据覆盖持久化，修正 `schema_validation` 契约字段检查。
- 提交检查新增 JSON、frontmatter、20 条示例、缓存和 GitHub 链接校验。
