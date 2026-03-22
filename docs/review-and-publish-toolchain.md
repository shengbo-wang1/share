# 审核与发布工具链（v1 CSV 入库版）

本文把第一版题库的“`candidate.csv -> 人工审核 -> 发布脚本 -> challenge/challenge_day` 入库”链路补成可执行规范。目标是让实现者可以直接按文档写出离线审核与发布工具，而不需要再临场决定 CSV 模板、状态流转和入库边界。

## 1. 工具链目标与边界

### 1.1 工具链职责
第一版审核与发布工具链负责：
- 接收 generator 输出的 `candidate_{generation_batch_id}.csv`
- 约束人工审核后的 `reviewed_candidate_{generation_batch_id}.csv`
- 校验 reviewed CSV
- 将通过审核的 candidate 固化为 `challenge` 与 `challenge_day`
- 输出发布成功 / 失败清单

### 1.2 输入
- `candidate_{generation_batch_id}.csv`
- `reviewed_candidate_{generation_batch_id}.csv`
- `stock_daily_raw`
- `stock_daily_feature`
- 可选：`index_daily_feature`

### 1.3 输出
- `challenge` rows
- `challenge_day` rows
- `publish_success_{publish_batch_id}.csv`
- `publish_failed_{publish_batch_id}.csv`

### 1.4 明确不做
第一版固定不做：
- 审核后台
- `challenge_candidate` 表
- 在线审批流
- 自动上线
- 多轮复杂会签

---

## 2. reviewed CSV 标准模板

## 2.1 必备字段
reviewed CSV 至少包含以下列：

| 字段 | 说明 |
|---|---|
| `candidate_key` | 固定为 `{code}_{start_date}` |
| `code` | 股票代码 |
| `start_date` | 窗口起始交易日 |
| `end_date` | 窗口结束交易日 |
| `primary_tag` | generator 自动生成主标签 |
| `secondary_tag` | generator 自动生成辅标签，可空 |
| `difficulty` | generator 自动生成难度 |
| `score_explain_json` | 特征摘要、命中原因、难度摘要 |
| `rule_flags_json` | 命中标签、冲突信息、排除标记 |
| `generation_batch_id` | 生成批次 |
| `review_status` | 审核状态 |
| `review_comment` | 审核备注 |
| `adjusted_primary_tag` | 人工调整后的主标签，可空 |
| `adjusted_difficulty` | 人工调整后的难度，可空 |
| `reviewer` | 审核人标识 |
| `reviewed_at` | 审核时间 |
| `publish_flag` | 是否进入发布脚本 |

## 2.2 固定枚举
第一版固定枚举如下：

### `review_status`
- `PENDING`
- `APPROVED`
- `REJECTED`
- `REVIEW_REQUIRED`

### `publish_flag`
- `YES`
- `NO`

## 2.3 模板校验规则
- `APPROVED` 才允许进入发布脚本
- `publish_flag = YES` 才允许发布
- `reviewer` 与 `reviewed_at` 在 `APPROVED / REJECTED` 时必须填写
- `adjusted_primary_tag` 与 `adjusted_difficulty` 最多只能填一个
- 若两个都填：
  - 该行必须强制视为 `REJECTED`
  - 不能进入发布脚本

## 2.4 默认 reviewed CSV 文件名
第一版默认：

```text
reviewed_candidate_{generation_batch_id}.csv
```

---

## 3. 审核流程与状态机

## 3.1 固定审核流程
第一版固定流程如下：
1. generator 产出 `candidate.csv`
2. 人工复制 / 编辑为 `reviewed_candidate.csv`
3. 审核人填写状态、备注、可选微调字段
4. 发布脚本读取并校验 reviewed CSV
5. 只有 `APPROVED + YES` 的行进入发布
6. 发布脚本生成 `challenge / challenge_day`
7. 发布结果写入成功 / 失败清单

## 3.2 状态流转
第一版只允许以下流转：
- `PENDING -> APPROVED`
- `PENDING -> REJECTED`
- `REVIEW_REQUIRED -> APPROVED`
- `REVIEW_REQUIRED -> REJECTED`

第一版不支持：
- 发布后再回写审核状态
- `APPROVED -> PENDING`
- `REJECTED -> APPROVED` 的多轮复杂回退

## 3.3 人工调整边界
人工最多只允许调整一项：
- 要么改 `primary_tag`
- 要么改 `difficulty`

若主标签和难度都需要改：
- 说明自动规则稳定性不足
- 该 candidate 必须记为 `REJECTED`
- 不进入正式 challenge

---

## 4. 发布脚本输入输出与主流程伪代码

## 4.1 发布脚本输入
- reviewed CSV
- `stock_daily_raw`
- `stock_daily_feature`
- 可选 `index_daily_feature`

## 4.2 发布脚本输出
- `challenge` rows
- `challenge_day` rows
- `publish_success.csv`
- `publish_failed.csv`

## 4.3 固定核心函数名
第一版文档固定以下函数名：
- `pass_review_gate`
- `normalize_review_row`
- `build_challenge_id`
- `build_challenge_row`
- `build_challenge_day_rows`
- `pass_publish_validation`
- `persist_challenge_bundle`
- `emit_publish_result`

## 4.4 总伪代码
```python
def publish_reviewed_candidates(reviewed_csv, publish_batch_id):
    success_rows = []
    failed_rows = []

    for row in reviewed_csv:
        if not pass_review_gate(row):
            continue

        normalized = normalize_review_row(row)
        challenge_id = build_challenge_id(normalized)

        if already_published(challenge_id):
            failed_rows.append(build_failed_row(row, "CHALLENGE_ID_CONFLICT"))
            continue

        challenge = build_challenge_row(normalized, challenge_id, publish_batch_id)
        challenge_days = build_challenge_day_rows(normalized, challenge_id, publish_batch_id)

        if not pass_publish_validation(challenge, challenge_days):
            failed_rows.append(build_failed_row(row, "PUBLISH_VALIDATION_FAILED"))
            continue

        persist_challenge_bundle(challenge, challenge_days)
        success_rows.append(build_success_row(row, challenge_id))

    emit_publish_result(success_rows, failed_rows, publish_batch_id)
```

## 4.5 review gate 规则
```python
def pass_review_gate(row):
    if row.review_status != "APPROVED":
        return False
    if row.publish_flag != "YES":
        return False
    if not row.reviewer or not row.reviewed_at:
        return False
    if row.adjusted_primary_tag and row.adjusted_difficulty:
        return False
    return True
```

## 4.6 输出文件名
第一版默认：
- `publish_success_{publish_batch_id}.csv`
- `publish_failed_{publish_batch_id}.csv`

---

## 5. challenge / challenge_day 入库规则

## 5.1 challenge 构建规则
`challenge` 行按以下规则固化：
- `challenge_id`：使用既有默认命名规则
- `code`：来自 reviewed CSV
- `start_date / end_date`：来自 reviewed CSV
- `difficulty`：优先用 `adjusted_difficulty`，否则用原 `difficulty`
- `tags_json`：
  - `primaryTag`：优先用 `adjusted_primary_tag`，否则用原 `primary_tag`
  - `secondaryTag`：沿用 `secondary_tag`
  - `tagVersion = v1`
- `generation_batch_id`：来自本次发布批次
- `freeze_status = FROZEN`
- `status = ACTIVE`

## 5.2 challenge_day 构建规则
`challenge_day` 固化规则：
- 固化 20 日主窗口
- 使用已有 `stock_daily_raw + stock_daily_feature`
- 写入：
  - `raw_open / raw_close`
  - `qfq_open / qfq_high / qfq_low / qfq_close`
  - `volume`
  - `ma5 / ma10 / ma20`
  - `k_value / d_value / j_value`
  - `dif / dea / macd`
  - `cap_bucket`
- 不把验证窗口 `t+1 ~ t+3` 写入 `challenge_day`

## 5.3 发布前校验
发布前必须校验：
- 20 日主窗口数据完整
- 原始价 / QFQ / MA / KDJ / MACD 齐全
- `challenge_id` 不冲突
- `primary_tag / difficulty` 不为空
- `challenge_day` 条数必须恰好为 20

## 5.4 失败策略
- 单条失败不影响同批次其他行
- 每条失败必须写入 `publish_failed.csv`
- `publish_failed.csv` 至少包含：
  - `candidate_key`
  - `code`
  - `start_date`
  - `challenge_id`
  - `fail_reason`
  - `fail_message`
- 已成功入库的数据第一版不回滚
- 若未来需要整批事务，再单独升级工具链

---

## 6. 版本与排行榜隔离

## 6.1 version 规则
- 沿用既有 `challenge_id` 默认规则
- 新版本发布：
  - 生成新 `challenge_id`
  - 不覆盖旧 `challenge`
  - `generation_batch_id` 必须变化

## 6.2 排行榜隔离
第一版默认：
- 排行榜按 `challenge_id` 隔离
- 同一 `code + start_date` 的不同版本不合并成绩

## 6.3 首页投放默认规则
第一版默认：
- 新版本可投放首页
- 旧版本保留历史成绩
- 旧版本不再推荐到首页

## 6.4 与已有文档的关系
- `docs/challenge-generator-main-flow.md`
  - 定义 candidate 如何生成、如何进入 reviewed CSV
- `docs/review-and-publish-toolchain.md`
  - 定义 reviewed CSV 如何审核、如何进入发布脚本、如何入库
- `docs/data-init-flow.md`
  - 定义审核与发布工具链位于 Phase E

也就是说：

> **v1 题库发布不是“自动上线”，而是“candidate CSV -> reviewed CSV -> 发布脚本 -> 冻结 challenge/challenge_day”。**
