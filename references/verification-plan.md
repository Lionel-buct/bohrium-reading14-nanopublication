# 验证计划

## 1. 自动验证

在本地运行：

```bash
PYTHON_BIN="$(command -v python3 || command -v python)"
"$PYTHON_BIN" scripts/smoke_test.py
"$PYTHON_BIN" scripts/regression_test.py
"$PYTHON_BIN" scripts/check_submission.py
bash runtime_probe.sh --create-dirs
```

必须输出：

```json
{
  "status": "PASS",
  "count": 8
}
```

检查项：

1. `prepare_case`：能读取案例和材料。
2. `positive_validation`：完全存在的证据可通过。
3. `contract_projection`：案例契约字段能进入最终 JSON。
4. `negative_evidence_detection`：不存在的证据被拒绝。
5. `negative_partial_output`：负例只输出 partial，不伪装 success。
6. `stale_validation_guard`：草稿变更后旧校验失效。
7. `ocr_merge`：待识别页面合并 OCR 文本后重建证据单元。
8. `empty_ocr_is_partial`：空 OCR 文本不会被当作成功，并保留待人工接管页。

`regression_test.py` 另提供 12 项回归，覆盖运行时探测、数字 `case_id`、数值丢失、范围丢失、否定反转、因果过强、缺少理由、来源元数据持久化、`schema_validation` 契约、嵌套契约类型、比较基线、草稿产物排除和 OCR 重建。

## 2. PDF 页级验证

使用真实 PDF 或渲染 PDF：

```bash
"$PYTHON_BIN" scripts/prepare_case.py \
  --case /input/case.json \
  --input-root /input \
  --work /app/work \
  --render-empty-pages
```

检查：

- `source_units.jsonl` 包含 `page`、`block_index` 和 `unit_id`；
- 页数大于 0；
- 文本不是全空；
- 无文本页进入 `needs_ocr_pages`；
- 证据定位能映射到页面全文的 `char_start/char_end`；
- 行尾连字符和换行不影响定位。

## 3. 负例测试

应至少覆盖：

### 3.1 证据不存在

把 evidence quote 改成材料中不存在的句子。

预期：

- `validate_nanopubs.py --strict` 返回非零；
- `validation.errors` 含 `evidence_not_found`；
- 最终状态不能是 `success`。

### 3.2 关系不在词表

把 `relation` 改为 `made_better`。

预期：

- `validation.errors` 含 `unmapped_relation`；
- 修复为词表关系后可通过。

### 3.3 缺少证据

删除全部 evidence。

预期：

- `validation.errors` 含 `missing_evidence`；
- 最终状态必须 `partial` 或下游未完成。

### 3.4 缺少契约字段

从 `contract_fields` 删除必需字段。

预期：

- `contract_validation.status = failed`；
- 最终状态降级为 `partial`。

### 3.5 陈旧校验

校验后修改 `draft_result.json`，不改哈希直接 finalize。

预期：

- finalizer 报告 stale draft；
- 不生成通过契约的最终结果，或写入失败状态。

## 4. 断词与 PDF 噪声

使用含以下情况的页面：

- `Time-\nResolved`
- 全角/半角标点
- 页眉页脚
- 双栏排版
- 表格单元换行
- 图注和正文分离

预期：

- 至少能定位到正确页面；
- 若无法定位，明确进入 `unresolved`；
- 不通过修改引文或页码强行通过。

## 5. 重复与冲突

构造两次相同断言：

- 预期 `duplicates[]` 记录；
- 不能自动生成两个无说明的重复 nanopublication。

构造两个相反来源：

- 预期 `conflicts[]` 记录；
- 断言极性为 `inconclusive` 或范围受限；
- 最终状态为 `partial`。

## 6. 输出质量检查

最终文件必须：

- 能被 `json.loads` 解析；
- 是 UTF-8；
- 有 `case_id`；
- 有 `status`；
- 有 `nanopublications`；
- 有 `sources`；
- 有 `unresolved`；
- 有 `output_contract`；
- 有 `contract_validation`。

## 7. 资源约束检查

提交前检查：

- 文本文件数不超过 50；
- 单文件不超过 500 KB；
- 总大小不超过 2 MB；
- 无符号链接；
- 不包含个人敏感路径、Token、密码、API key；
- 示例均明确标注为合成示例。

## 8. 版本与回归

每次修改规则、词表或脚本后：

1. 运行 smoke test；
2. 用一份真实 PDF 重跑准备流程；
3. 比较 `result.json` 的断言数、证据精确定位率和未解决数；
4. 更新 `README.md` 的维护记录；
5. 不删除旧变更记录，使用 `change_log` 或版本说明。
