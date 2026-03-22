# 脚本实跑与联调手册（runbook）

这份文档用于把三段离线脚本的**真实运行方式、输出目录约定、联调顺序、调试记录**固定下来，方便后续任何人在同一路径下复现。

## 1. 统一约定
### 1.1 执行目录
所有示例命令默认都从仓库根目录执行：

```bash
cd /Users/wangshengbo/Desktop/java-share-app
```

不要默认先进入 `share/` 再执行，否则容易和 `output/` 路径口径混淆。

### 1.2 输出目录
三段脚本统一输出到仓库根目录下的 `output/`：
- `output/akshare_bootstrap/`
- `output/challenge_generator/`
- `output/review_publish/`

### 1.3 MySQL 连接方式
MySQL 连接信息只允许通过以下两种方式提供：
- 命令行参数：`--mysql-dsn`
- 环境变量：`SHARE_MYSQL_DSN`

示例：

```bash
export SHARE_MYSQL_DSN='mysql+pymysql://<user>:<password>@43.143.210.196:3306/<db>'
```

说明：
- 当前开发阶段可先按公网 IP：`43.143.210.196`
- 云上部署后切私网：`10.2.0.14`
- 不要把数据库地址、账号、密码写死在代码或公开文档中

## 2. 执行前准备
### 2.1 Python 版本
建议使用：
- Python 3.10+

### 2.2 依赖安装
最小依赖安装命令：

```bash
python3 -m pip install pandas akshare sqlalchemy pymysql
```

如需隔离环境，建议：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install pandas akshare sqlalchemy pymysql
```

### 2.3 入口检查
先确认三段脚本入口可用：

```bash
python3 share/scripts/akshare_bootstrap.py --help
python3 share/scripts/challenge_generator.py --help
python3 share/scripts/review_publish.py --help
```

如果这里就失败，先不要继续跑真实数据。

---

## 3. 阶段 1：bootstrap 实跑
### 3.1 推荐首轮命令
第一轮先只跑 CSV，不接 MySQL：

```bash
python3 share/scripts/akshare_bootstrap.py \
  --symbols 600519 300750 \
  --start-date 2024-01-01 \
  --end-date 2024-03-31 \
  --output-dir output/akshare_bootstrap
```

如需抓请求级诊断日志，追加：

```bash
python3 share/scripts/akshare_bootstrap.py \
  --symbols 600519 \
  --start-date 2023-10-01 \
  --end-date 2024-03-31 \
  --output-dir output/akshare_bootstrap \
  --fetch-debug
```

如需测试 MySQL：

```bash
python3 share/scripts/akshare_bootstrap.py \
  --symbols 600519 300750 \
  --start-date 2024-01-01 \
  --end-date 2024-03-31 \
  --output-dir output/akshare_bootstrap \
  --mysql-dsn "$SHARE_MYSQL_DSN"
```

### 3.2 预期输出
执行成功后，`output/akshare_bootstrap/` 下应新增一个最新批次目录，目录内至少包含：
- `stock_basic.csv`
- `stock_basic_snapshot_log.csv`
- `trading_calendar.csv`
- `stock_daily_raw.csv`
- `stock_daily_feature.csv`
- `index_daily_raw.csv`
- `index_daily_feature.csv`
- `staging_raw.csv`
- `job_run_log.csv`
- `data_quality_check.csv`
- `fetch_attempt_log.csv`
- `fetch_debug_log.jsonl`（仅 `--fetch-debug` 开启时生成）
- `symbol_run_log.csv`
- `index_fetch_log.csv`

补充说明：
- `stock_basic` 优先来自交易所股票列表接口
- 若股票列表接口失败，脚本会尝试用 `stock_zh_a_spot_em()` 作为股票池 / 名称 fallback
- 本地会维护一个 `stock_basic` 快照缓存，用于列表接口失败时兜底

### 3.3 检查点
重点检查：
- 是否生成了新的批次目录
- 是否产出了上述核心 CSV
- `stock_basic.csv` 的 `list_date` 是否已落地，不再大面积为空
- `trading_calendar.csv` 是否存在 `SH / SZ / BJ` 三套开市日记录
- `index_daily_feature.csv` 是否可提供：
  - `pct_change_1d`
  - `drawdown_5d`
  - `vol_ratio_1d_5d`
  - `panic_flag`
- 若抓取失败，`fetch_attempt_log.csv` 是否保留了每次 attempt 的错误类型、耗时与错误摘要
- 若开启 `--fetch-debug`，`fetch_debug_log.jsonl` 是否保留了 method / URL / timeout / headers 摘要 / 是否拿到 response / status / body preview
- `symbol_run_log.csv` 是否能看出 raw / qfq / share 三段分别成功还是失败
- `symbol_run_log.csv` 中 `share_status` 预期为 `NOT_USED`，因为主链路已不再依赖 `stock_zh_a_daily`
- `stock_daily_raw.csv` 与 `stock_daily_feature.csv` 是否有合理行数
- `trade_date` 是否连续且排序正确
- `raw` 与 `feature` 是否按相同日期对齐
- 是否存在明显空列、整列 NaN、或日期错位
- `data_quality_check.csv` 是否出现大面积失败项

### 3.4 常用检查命令
```bash
find output/akshare_bootstrap -maxdepth 2 -type f | sort
ls -lah output/akshare_bootstrap
head -n 5 output/akshare_bootstrap/<latest_batch>/stock_daily_raw.csv
head -n 5 output/akshare_bootstrap/<latest_batch>/stock_daily_feature.csv
```

---

## 4. 阶段 2：generator 实跑
### 4.1 推荐命令
默认读取 `output/akshare_bootstrap/` 下**最新成功批次**目录（`job_run_log.csv` 状态为 `SUCCESS / PARTIAL_SUCCESS`）：

```bash
python3 share/scripts/challenge_generator.py \
  --bootstrap-output-dir output/akshare_bootstrap \
  --output-dir output/challenge_generator
```

如需限定扫描起止日期：

```bash
python3 share/scripts/challenge_generator.py \
  --bootstrap-output-dir output/akshare_bootstrap \
  --output-dir output/challenge_generator \
  --trade-date-from 2024-01-01 \
  --trade-date-to 2024-03-31
```

如需在联调阶段避免“自动识别批次”带来的歧义，仍建议显式指定成功批次文件路径：

```bash
python3 share/scripts/challenge_generator.py \
  --stock-basic-csv output/akshare_bootstrap/<success_batch>/stock_basic.csv \
  --raw-csv output/akshare_bootstrap/<success_batch>/stock_daily_raw.csv \
  --feature-csv output/akshare_bootstrap/<success_batch>/stock_daily_feature.csv \
  --output-dir output/challenge_generator
```

### 4.2 预期输出
执行成功后，`output/challenge_generator/` 下应新增：
- `candidate_{generation_batch_id}.csv`
- `generator_debug_{generation_batch_id}.csv`
- `generator_run_log_{generation_batch_id}.csv`

### 4.3 检查点
重点检查：
- 是否生成 `candidate_*.csv`
- 若未生成 candidate，是否仍生成 `generator_debug_*.csv` 与 `generator_run_log_*.csv`
- 是否包含文档约定字段：
  - `candidate_key`
  - `code`
  - `start_date`
  - `end_date`
  - `primary_tag`
  - `secondary_tag`
  - `difficulty`
  - `score_explain_json`
  - `rule_flags_json`
  - `review_status`
  - `generation_batch_id`
- `review_status` 是否只出现 `PENDING / REVIEW_REQUIRED`
- 当缺少指数数据时，第 5 类标签是否被跳过而不是整批失败
- `score_explain_json` 与 `rule_flags_json` 是否可正常解析
- 若出现 `0 candidate`，先看 `generator_debug_*.csv` 中的 `reason` 聚合，再看 `generator_run_log_*.csv` 的 `top_reject_reasons_json`
- 若规则看起来没命中，重点看 `generator_debug_*.csv` 中新增的 `stage=tag_rule`：
  - `tag_hit_<标签名>`：该标签命中
  - `tag_miss_<标签名>`：该标签未命中
  - `detail_json` 中应能看到 `matched_conditions / missed_conditions / exclusion_reasons`
- 若 `review_status = REVIEW_REQUIRED`，优先检查：
  - `rule_flags_json.conflict_flags`
  - `generator_debug_*.csv` 中同窗口的 `tag_rule` 与 `candidate_emit`
- 单股 + 单月样本可能只有约 22 个交易日，不满足 `20 + 3` 的最小窗口要求，这种情况下 `0 candidate` 属于预期现象之一

### 4.4 常用检查命令
```bash
find output/challenge_generator -maxdepth 1 -type f | sort
head -n 5 output/challenge_generator/candidate_<generation_batch_id>.csv
```

如需快速查看字段头：

```bash
python3 - <<'PY'
import csv
with open('output/challenge_generator/candidate_<generation_batch_id>.csv', newline='') as f:
    print(next(csv.reader(f)))
PY
```

---

## 5. 阶段 3：review / publish 实跑
### 5.1 reviewed CSV 最小调试方法
第一轮不要全量审核，先用最小样本联调：
1. 复制 generator 产出的 candidate CSV
2. 文件名改为：

```text
reviewed_candidate_{generation_batch_id}.csv
```

3. 至少补齐以下列值：
- `review_status`
- `review_comment`
- `reviewer`
- `reviewed_at`
- `publish_flag`

4. 第一轮建议只保留少量 `APPROVED + YES` 行，例如 1~3 行
5. 不要同时填写：
- `adjusted_primary_tag`
- `adjusted_difficulty`

### 5.2 最小示例
对准备发布的行，至少改成：
- `review_status = APPROVED`
- `review_comment = first dry run`
- `reviewer = manual-debug`
- `reviewed_at = 2026-03-22 20:00:00`
- `publish_flag = YES`

其余不发布的行可保持：
- `publish_flag = NO`
- 或 `review_status = REJECTED`

### 5.3 推荐命令
```bash
python3 share/scripts/review_publish.py \
  --generator-output-dir output/challenge_generator \
  --bootstrap-output-dir output/akshare_bootstrap \
  --output-dir output/review_publish
```

如需测试 MySQL：

```bash
python3 share/scripts/review_publish.py \
  --generator-output-dir output/challenge_generator \
  --bootstrap-output-dir output/akshare_bootstrap \
  --output-dir output/review_publish \
  --mysql-dsn "$SHARE_MYSQL_DSN"
```

### 5.4 预期输出
执行成功后，`output/review_publish/` 下应新增：
- `challenge_{publish_batch_id}.csv`
- `challenge_day_{publish_batch_id}.csv`
- `publish_success_{publish_batch_id}.csv`
- `publish_failed_{publish_batch_id}.csv`
- `publish_run_log_{publish_batch_id}.csv`

### 5.5 检查点
重点检查：
- 是否生成 `challenge_*.csv`
- 是否生成 `challenge_day_*.csv`
- 是否生成 success / failed 清单
- 是否生成 `publish_run_log_*.csv`，并可看到 `success_count / failed_count / top_fail_reasons_json`
- `challenge.csv` 的 `challenge_id` 是否符合：
  - `{code}_{start_date}_{primaryTagShort}_v1`
- `challenge_day.csv` 每个 `challenge_id` 是否恰好 20 行
- `publish_failed.csv` 是否包含：
  - `candidate_key`
  - `code`
  - `start_date`
  - `challenge_id`
  - `fail_reason`
  - `fail_message`

### 5.6 常用检查命令
```bash
find output/review_publish -maxdepth 1 -type f | sort
head -n 5 output/review_publish/challenge_<publish_batch_id>.csv
head -n 5 output/review_publish/publish_failed_<publish_batch_id>.csv
```

如需检查每题是否 20 行：

```bash
python3 - <<'PY'
import csv
from collections import Counter
path = 'output/review_publish/challenge_day_<publish_batch_id>.csv'
counter = Counter()
with open(path, newline='') as f:
    for row in csv.DictReader(f):
        counter[row['challenge_id']] += 1
print(counter)
PY
```

---

## 6. 固定 CSV 闭环联调
当 bootstrap 因上游风控暂时不可用时，可直接使用 repo 内固定夹具，重复跑通 generator / publish。

### 6.1 夹具位置
- `share/scripts/testdata/fixed_e2e_fixture/bootstrap_output/bootstrap-fixture-e2e/`
- `share/scripts/testdata/fixed_e2e_fixture/reviewed_candidate_fixture-e2e.csv`

说明：
- 这套夹具只用于**后链路闭环联调**
- 不用于替代真实抓取，也不是规则覆盖全集
- 若后续 generator 规则调整导致 candidate 漂移，需要同步更新 reviewed fixture 和测试

### 6.2 generator 固定命令
```bash
python3 share/scripts/challenge_generator.py \
  --generation-batch-id fixture-e2e \
  --bootstrap-output-dir share/scripts/testdata/fixed_e2e_fixture/bootstrap_output \
  --output-dir output/challenge_generator
```

预期：
- 生成 `candidate_fixture-e2e.csv`
- 仅 1 条 candidate
- 主标签固定为 `放量突破 vs 假突破`

推荐低噪声版本（只扫固定窗口，减少 `window_incomplete` 调试噪音）：

```bash
python3 share/scripts/challenge_generator.py \
  --generation-batch-id fixture-e2e \
  --bootstrap-output-dir share/scripts/testdata/fixed_e2e_fixture/bootstrap_output \
  --trade-date-from 2024-01-02 \
  --trade-date-to 2024-01-02 \
  --output-dir output/challenge_generator
```

说明：
- 不限日期版本：适合观察 debug 全量行为
- 限定日期版本：适合快速 smoke，且只扫描 `2024-01-02` 这个固定窗口

### 6.3 publish 固定命令
```bash
python3 share/scripts/review_publish.py \
  --publish-batch-id fixture-publish-e2e \
  --reviewed-csv share/scripts/testdata/fixed_e2e_fixture/reviewed_candidate_fixture-e2e.csv \
  --raw-csv share/scripts/testdata/fixed_e2e_fixture/bootstrap_output/bootstrap-fixture-e2e/stock_daily_raw.csv \
  --feature-csv share/scripts/testdata/fixed_e2e_fixture/bootstrap_output/bootstrap-fixture-e2e/stock_daily_feature.csv \
  --output-dir output/review_publish
```

预期：
- 生成 1 条 `challenge`
- 生成 20 条 `challenge_day`
- `publish_success_fixture-publish-e2e.csv` 有 1 行
- `publish_failed_fixture-publish-e2e.csv` 为空
- repo 内静态 `reviewed_candidate_fixture-e2e.csv` 只作为人工联调样本；测试链路会优先从 generator 实时产出的 candidate 派生 reviewed CSV，避免和 generator explain JSON 漂移

---

## 7. 固定失败样本调试（publish failure fixtures）
当你要排查 `review_publish.py` 的失败口径时，可直接使用固定失败样本，不依赖实时抓取。

### 7.1 夹具位置
- `share/scripts/testdata/publish_failure_fixture/manifest.json`
- `share/scripts/testdata/publish_failure_fixture/reviewed_cases/`

当前第一轮覆盖：
- `REVIEWED_CSV_MISSING_COLUMNS`
- `DUAL_ADJUSTMENT_NOT_ALLOWED`
- `CHALLENGE_ID_CONFLICT`
- `PUBLISH_BUILD_FAILED`

这些样本共享使用：
- `share/scripts/testdata/fixed_e2e_fixture/bootstrap_output/bootstrap-fixture-e2e/stock_daily_raw.csv`
- `share/scripts/testdata/fixed_e2e_fixture/bootstrap_output/bootstrap-fixture-e2e/stock_daily_feature.csv`

### 7.2 单独复现某个失败样本
以 `DUAL_ADJUSTMENT_NOT_ALLOWED` 为例：

```bash
python3 share/scripts/review_publish.py \
  --publish-batch-id fixture-publish-fail-dual-adjustment \
  --reviewed-csv share/scripts/testdata/publish_failure_fixture/reviewed_cases/reviewed_dual_adjustment.csv \
  --raw-csv share/scripts/testdata/fixed_e2e_fixture/bootstrap_output/bootstrap-fixture-e2e/stock_daily_raw.csv \
  --feature-csv share/scripts/testdata/fixed_e2e_fixture/bootstrap_output/bootstrap-fixture-e2e/stock_daily_feature.csv \
  --output-dir output/review_publish
```

预期：
- `publish_failed_*.csv` 中出现 `DUAL_ADJUSTMENT_NOT_ALLOWED`
- `publish_run_log_*.csv` 状态为 `FAILED`

### 7.3 challenge_id 冲突复现
这个样本需要先在输出目录中放一个同 `challenge_id` 的历史文件，例如：

```bash
mkdir -p output/review_publish
cat > output/review_publish/challenge_preseed.csv <<'CSV'
challenge_id,code,start_date,end_date
600519.SH_2024-01-02_breakout_v1,600519.SH,2024-01-02,2024-01-29
CSV
```

然后再执行：

```bash
python3 share/scripts/review_publish.py \
  --publish-batch-id fixture-publish-fail-challenge-id-conflict \
  --reviewed-csv share/scripts/testdata/publish_failure_fixture/reviewed_cases/reviewed_challenge_id_conflict.csv \
  --raw-csv share/scripts/testdata/fixed_e2e_fixture/bootstrap_output/bootstrap-fixture-e2e/stock_daily_raw.csv \
  --feature-csv share/scripts/testdata/fixed_e2e_fixture/bootstrap_output/bootstrap-fixture-e2e/stock_daily_feature.csv \
  --output-dir output/review_publish
```

预期：
- `publish_failed_*.csv` 中出现 `CHALLENGE_ID_CONFLICT`

说明：
- 这套 failure fixtures 是 `review_publish` 的离线诊断样本
- 不代表真实人工审核流中的全部错误组合

---

## 8. 固定失败样本调试（generator failure fixtures）
当你要排查 `challenge_generator.py` 的失败/半失败口径时，可直接使用固定 generator 失败样本。

### 8.1 夹具位置
- `share/scripts/testdata/generator_failure_fixture/manifest.json`
- `share/scripts/testdata/generator_failure_fixture/bootstrap_cases/`

当前第一轮覆盖：
- `review_required`
- `no_candidate`
- `insufficient_trade_days`
- `unresolvable_tag_conflict`

### 8.2 单独复现某个 generator 失败样本
以 `review_required` 为例：

```bash
python3 share/scripts/challenge_generator.py \
  --generation-batch-id fixture-generator-fail-review-required \
  --stock-basic-csv share/scripts/testdata/generator_failure_fixture/bootstrap_cases/review_required/stock_basic.csv \
  --raw-csv share/scripts/testdata/generator_failure_fixture/bootstrap_cases/review_required/stock_daily_raw.csv \
  --feature-csv share/scripts/testdata/generator_failure_fixture/bootstrap_cases/review_required/stock_daily_feature.csv \
  --trade-date-from 2024-01-02 \
  --trade-date-to 2024-01-02 \
  --output-dir output/challenge_generator
```

预期：
- 仍生成 1 条 candidate
- `review_status = REVIEW_REQUIRED`
- `primary_tag = 放量突破 vs 假突破`

对于以下预期 `EMPTY` 的场景，推荐加上 `--allow-empty`，避免脚本以非 0 退出码结束：

```bash
python3 share/scripts/challenge_generator.py \
  --generation-batch-id fixture-generator-fail-no-candidate \
  --stock-basic-csv share/scripts/testdata/generator_failure_fixture/bootstrap_cases/no_candidate/stock_basic.csv \
  --raw-csv share/scripts/testdata/generator_failure_fixture/bootstrap_cases/no_candidate/stock_daily_raw.csv \
  --feature-csv share/scripts/testdata/generator_failure_fixture/bootstrap_cases/no_candidate/stock_daily_feature.csv \
  --trade-date-from 2024-01-02 \
  --trade-date-to 2024-01-02 \
  --allow-empty \
  --output-dir output/challenge_generator
```

说明：
- `--allow-empty` 只改变 CLI 退出体验
- `generator_run_log.status` 仍然会是 `EMPTY`
- `generator_debug` 和 `generator_run_log` 仍然照常输出

### 8.3 no candidate / 冲突拒绝场景怎么判断
- `no_candidate`
  - 预期 `generator_run_log.status = EMPTY`
  - `generator_debug` 中应出现 `tag_classify / no_tag_hit`
- `insufficient_trade_days`
  - `generator_debug` 中应出现 `window_build / insufficient_trade_days`
- `unresolvable_tag_conflict`
  - `generator_debug` 中应出现 `candidate_gate / unresolvable_tag_conflict`
  - 表示窗口命中了多标签，但被规则明确拒绝，不进入人工池

说明：
- 这套 failure fixtures 是 generator 的离线诊断样本
- 每个样本只承担一种主语义，不代表真实样本全集

---

## 8.4 generator 规则稳定性夹具（anti-drift）
当你要确认 generator 的核心标签/难度行为是否漂移时，可直接使用固定 stability fixtures。

### 8.4.1 夹具位置
- `share/scripts/testdata/generator_stability_fixture/manifest.json`
- `share/scripts/testdata/generator_stability_fixture/bootstrap_cases/`

当前第一轮覆盖：
- `easy_clear_signal`
- `secondary_tag_explanatory`
- `index_missing_but_candidate_survives`

### 8.4.2 单独复现某个 stability case
以 `easy_clear_signal` 为例：

```bash
python3 share/scripts/challenge_generator.py \
  --generation-batch-id fixture-generator-stability-easy \
  --stock-basic-csv share/scripts/testdata/generator_stability_fixture/bootstrap_cases/easy_clear_signal/stock_basic.csv \
  --raw-csv share/scripts/testdata/generator_stability_fixture/bootstrap_cases/easy_clear_signal/stock_daily_raw.csv \
  --feature-csv share/scripts/testdata/generator_stability_fixture/bootstrap_cases/easy_clear_signal/stock_daily_feature.csv \
  --trade-date-from 2024-01-02 \
  --trade-date-to 2024-01-02 \
  --output-dir output/challenge_generator
```

预期：
- 生成 1 条 candidate
- `primary_tag = 缩量回踩均线`
- `difficulty = easy`
- `review_status = PENDING`

### 8.4.3 怎么判断是规则漂移还是实现故障
- 若 `candidate.csv` 存在，但 `primary_tag / secondary_tag / difficulty / review_status` 与 manifest 不一致：
  - 更像规则实现或优先级发生漂移
- 若 `generator_debug` 中关键 `reason` 不再出现：
  - 优先检查标签命中条件或 debug 落盘逻辑
- 若 `index_missing_but_candidate_survives` 因缺指数整批失败：
  - 说明“指数缺失只停用第 5 类标签”的既有口径被破坏

说明：
- 这组样本是 generator 的 anti-drift regression set
- 用于锁核心业务行为，不是完整标签全集，也不是抓取替代物

---

## 9. 一键 fixture smoke
当你要一次性验证 repo 内所有固定夹具链路时，可直接运行一键 smoke 脚本。

### 9.1 标准命令
```bash
python3 share/scripts/fixture_smoke.py \
  --output-dir output/fixture_smoke
```

### 9.2 执行内容
脚本会按 manifest 串行执行：
1. fixed success
2. publish failure fixtures
3. generator failure fixtures
4. generator stability fixtures

其中 generator failure fixtures 会自动带上 `--allow-empty` 等价行为，因此像 `no_candidate` / `unresolvable_tag_conflict` 这类预期 `EMPTY` 的样本不会把整个 smoke 直接打断。

### 9.3 输出目录
默认输出到：

```text
output/fixture_smoke/<smoke_batch_id>/
```

目录内至少包含：
- `fixed_success/`
- `publish_fail_<case>/`
- `generator_fail_<case>/`
- `generator_stability_<case>/`
- `smoke_summary_<smoke_batch_id>.csv`
- `smoke_summary_<smoke_batch_id>.json`

### 9.4 summary 怎么看
summary 至少包含：
- `suite`
- `case_id`
- `expected_outcome`
- `actual_status`
- `pass`
- `key_output_path`
- `message`

判断口径：
- 所有 `pass=true`：本轮 fixture smoke 通过
- 任一 `pass=false`：优先打开该行的 `key_output_path`

---

## 10. 常见问题排查
### 10.1 缺少 pandas / akshare / sqlalchemy
现象：
- `ModuleNotFoundError`

处理：
```bash
python3 -m pip install pandas akshare sqlalchemy pymysql
```

### 10.2 RemoteDisconnected / Connection aborted
现象：
- `RemoteDisconnected('Remote end closed connection without response')`
- `Connection aborted`
- 同一批次多个 symbol 同时在抓取阶段失败

处理：
- 优先判断为上游连接中断、接口限流、网络波动，而不是本地依赖缺失
- 先按最小排查顺序执行：
  1. 单股
  2. 短日期
  3. 直接调用 AKShare 原始接口
- 如需把请求现场抓全，使用：

```bash
python3 share/scripts/akshare_bootstrap.py \
  --symbols 600519 \
  --start-date 2023-10-01 \
  --end-date 2024-03-31 \
  --output-dir output/akshare_bootstrap \
  --fetch-debug
```

- 若 `stock_zh_a_daily` 高频失败，但 `stock_zh_a_hist` 可用，允许按软失败降级继续生成 raw / feature
- 若首次失败、紧接着复跑成功，优先判断为上游瞬时抖动 / 限流，而不是本地依赖问题
- 优先查看 bootstrap 批次目录中的：
  - `fetch_attempt_log.csv`
  - `fetch_debug_log.jsonl`（若开启了 `--fetch-debug`）
  - `symbol_run_log.csv`
  以确认是 `REMOTE_DISCONNECTED`、`CONNECTION_ERROR` 还是其它标准化错误
- 当前主链路只使用 `stock_zh_a_hist` 拉个股日线；若你之前单独使用 AKShare 稳定，而脚本链路不稳定，应优先检查是否是批量调用节奏而不是接口本身
- 读日志口径：
- `response_missing=true`：连接在收到 HTTP 响应前就被对端关闭，这时通常**没有响应体可打印**
  - `response_missing=false` 且有 `response_status_code` / `response_body_preview`：说明已经拿到 HTTP 响应，可继续判断是否 403/429/HTML 异常页/验证码页

### 10.3 generator 无 candidate
现象：
- `GeneratorError: 本次未生成任何 candidate`
- 没法直接从终端判断是股票被过滤、窗口不足还是标签未命中

处理：
- 先看 `generator_run_log_<generation_batch_id>.csv` 的：
  - `candidate_count`
  - `top_reject_reasons_json`
  - `status_message`
- 再看 `generator_debug_<generation_batch_id>.csv`：
  - `stock_filter` 阶段是否只有 `missing_list_date` 警告而不是整股跳过
  - `window_build` 阶段是否大量出现 `insufficient_trade_days`
  - `tag_classify` 阶段是否大量出现 `no_tag_hit`
  - `tag_rule` 阶段里是否能看出每个标签具体是哪些条件没过
- 若样本只有单股、单月，优先扩大时间范围或增加股票数量后再判断规则是否异常

补充判断口径：
- 若 `tag_rule` 大量是 `tag_miss_大盘恐慌日该不该抄底` 且 `index_features_missing`：
  - 说明只是第 5 类标签被停用，不代表其余标签也失效
- 若窗口进入 `REVIEW_REQUIRED`：
  - 不代表规则失败，而是代表多标签强冲突，需要人工重点审核
- 若 `candidate_gate` 出现：
  - `recently_listed_window`
  - `unresolvable_tag_conflict`
  - `indicator_gap`
  说明该窗口被规则明确判为不适合进入人工池

### 10.4 publish 扫描历史输出时遇到空 challenge CSV
现象：
- 之前失败批次遗留了空的 `challenge_*.csv`
- 再次执行 publish 时抛 `pandas.errors.EmptyDataError`

处理：
- 当前脚本已对空文件和空白文件自动跳过
- 若仍需排查，优先清理 `output/review_publish/` 下异常的空文件
- 推荐保留 `publish_failed.csv` 和 `publish_run_log.csv`，删除无意义的空 `challenge_*.csv`

### 10.5 AKShare 返回字段变化
现象：
- 缺列
- 列名变化
- share 数据接口字段与脚本预期不一致

处理：
- 先把原始报错、返回字段截图或样例记录到调试记录
- 核查 `staging_raw.csv` 与脚本字段映射逻辑
- 不要直接改规则文档，优先修正脚本字段兼容层

### 10.6 最新批次目录识别错误
现象：
- generator / publish 读错批次
- 读到旧输出

处理：
- 当前 generator 已改为优先读取 `SUCCESS / PARTIAL_SUCCESS` 的最新 bootstrap 批次
- 若仍需强控输入，显式传入 `--stock-basic-csv` / `--raw-csv` / `--feature-csv` / `--reviewed-csv`
- 或先清理/归档历史调试输出，再重跑

### 10.7 reviewed CSV 缺列或格式错误
现象：
- publish 阶段直接失败
- `reviewed_at` 无法解析
- `reviewer` / `publish_flag` 缺失

处理：
- 先对照本文档最小字段补齐
- `reviewed_at` 建议统一写成 `YYYY-MM-DD HH:MM:SS`
- 第一轮先只批准少量样本，避免整批排查困难

### 10.8 双重人工调整被拒绝
现象：
- 同一行同时填了 `adjusted_primary_tag` 和 `adjusted_difficulty`

处理：
- 第一版规则不允许这样做
- 该行应改为 `REJECTED` 或仅保留一项调整

### 10.9 challenge_id 冲突
现象：
- `publish_failed.csv` 出现 `CHALLENGE_ID_CONFLICT`

处理：
- 检查同一 `code + start_date + primaryTag + version` 是否重复发布
- 第一版不覆盖旧题，应更换版本或更换候选样本

---

## 10. AKShare 鉴权与限流说明
### 10.1 当前结论
基于 AKShare 官方文档当前内容：
- `stock_zh_a_hist` 未看到必须登录、cookie 或 token 的要求
- `stock_zh_a_daily` 也未看到独立鉴权参数要求
- 当前更像是上游连接不稳定、远端断开或接口限流，而不是鉴权缺失

### 10.2 需要特别注意的点
- `stock_zh_a_daily` 官方文档明确提示：多次获取容易封禁 IP，并建议优先使用 `stock_zh_a_hist`
- `stock_zh_a_hist` 是当前 raw / qfq 主链路的优先接口
- `stock_zh_a_daily` 在当前实现中应视为增强数据源，失败时允许软降级

### 10.3 文档依据
- 官方文档：`https://akshare.akfamily.xyz/data/stock/stock.html`
- 这是基于官方文档的当前结论
- 不排除上游站点后续临时调整策略，因此实现上仍需依赖重试、退避、降级和失败落盘

---

## 11. 联调执行顺序
固定按以下顺序推进：
1. 只跑 help 与依赖检查
2. 跑 bootstrap（先 CSV，后 MySQL）
3. 跑 generator
4. 手工准备 reviewed CSV 最小样本
5. 跑 review_publish（先 CSV，后 MySQL）
6. 把真实问题回填到本文档与 `docs/stage-review.md`

---

## 12. 调试记录模板
每次联调后，建议追加一条记录：

```markdown
### 调试记录 - YYYY-MM-DD HH:MM
- 执行命令：
  - `...`
- 输入批次：
  - bootstrap: `...`
  - generator: `...`
- 输出批次：
  - bootstrap: `...`
  - generator: `...`
  - publish: `...`
- 结果摘要：
  - 成功 / 失败
  - 产出文件数量
  - 是否接入 MySQL
- 已知问题 / 临时绕过：
  - ...
- 后续待修复项：
  - ...
```

### 调试记录 - 2026-03-22 20:00
- 执行命令：
  - `python3 share/scripts/akshare_bootstrap.py --symbols 600519 300750 --start-date 2024-01-01 --end-date 2024-03-31 --output-dir output/akshare_bootstrap`
- 输入批次：
  - bootstrap: `无（首轮真实联调）`
  - generator: `无`
- 输出批次：
  - bootstrap: `未成功产出业务 CSV`
  - generator: `无`
  - publish: `无`
- 结果摘要：
  - 本地 `.venv` 依赖安装成功
  - bootstrap 首轮真实联调失败
  - 未进入 generator / publish 阶段
- 已知问题 / 临时绕过：
  - 错误：`RemoteDisconnected('Remote end closed connection without response')`
  - 当前更像上游连接中断、远端断开或限流，不像本地依赖缺失
- 后续待修复项：
  - 为 bootstrap 增加重试 / 退避 / 失败落盘
  - 把 `stock_zh_a_daily` 降级为可失败增强数据源
  - 先按单股、短日期做复测

### 调试记录 - 2026-03-22 18:00
- 执行命令：
  - `python3 share/scripts/akshare_bootstrap.py --symbols 600519 --start-date 2024-01-01 --end-date 2024-01-31 --output-dir output/akshare_bootstrap`
- 输入批次：
  - bootstrap: `无（单股短日期复测）`
  - generator: `无`
- 输出批次：
  - bootstrap: `bootstrap-c633e74c863b`（失败） / `bootstrap-e99b5fd82acf`（成功）
  - generator: `无`
  - publish: `无`
- 结果摘要：
  - 第一次复测经历 3 次重试后仍失败，并落出最小诊断产物
  - 第二次紧接着复跑成功，已生成 6 个 bootstrap CSV
  - 当前可判断主链路可跑通，但上游存在瞬时断连 / 限流抖动
- 已知问题 / 临时绕过：
  - `RemoteDisconnected('Remote end closed connection without response')` 仍会偶发出现
  - generator 联调阶段优先显式指定成功批次 CSV，避免误吃失败批次或历史输出
- 后续待修复项：
  - 消除 bootstrap 中 `datetime.utcnow()` 告警
  - 确保 generator 自动选择成功批次
  - 补准 `job_run_log.csv` 的重试次数与真实起止时间

### 调试记录 - 2026-03-22 21:00
- 执行命令：
  - `python3 share/scripts/akshare_bootstrap.py --symbols 600519 --start-date 2023-10-01 --end-date 2024-03-31 --output-dir output/akshare_bootstrap --fetch-debug`
- 输入批次：
  - bootstrap: `无（请求级诊断复测）`
  - generator: `无`
- 输出批次：
  - bootstrap: `bootstrap-cc3b0a0df6fe`
  - generator: `无`
  - publish: `无`
- 结果摘要：
  - 股票列表与交易日历接口可访问
  - Eastmoney `push2his` 个股/指数 K 线接口全部失败
  - `fetch_debug_log.jsonl` 显示全部 `response_missing=true`
- 已知问题 / 临时绕过：
  - 当前更像 Eastmoney K 线接口的连接级拒绝/风控，不是本机整体断网，也不是 symbol/date 参数问题
  - 先暂停 bootstrap 抓取线，转做 generator / publish / MySQL 准备项
- 后续待修复项：
  - 等封禁窗口过去后再做 bootstrap 单股短区间复测
  - 这段等待时间优先补 generator 输入校验、空样本诊断、publish 失败码与 run log

## 13. 当前阻塞台账
### 10.1 已完成
- bootstrap 已具备请求级诊断、失败落盘、symbol/index 级日志
- generator 已具备 candidate/debug/run log 最小输出
- publish 已具备 success/failed 清单与 challenge/challenge_day 最小发布链路

### 10.2 阻塞中
- Eastmoney `push2his` K 线接口连接级拒绝，短期内暂停继续抓取
- 因 bootstrap 无法拿到有效 raw/feature，真实新数据链路暂时卡住

### 10.3 当前可并行推进
- generator 输入校验与 `0 candidate` 诊断补强
- publish reviewed CSV 校验、失败码、run log 补强
- MySQL 字段映射与写入口径核对

### 10.4 等 bootstrap 解锁后再做
- 重新跑单股、短日期 bootstrap 复测
- 串 generator -> reviewed CSV -> publish 最小闭环

## 14. CSV 与 MySQL 映射速查
### 11.1 bootstrap
- `stock_basic.csv` -> `stock_basic`
- `stock_daily_raw.csv` -> `stock_daily_raw`
- `stock_daily_feature.csv` -> `stock_daily_feature`
- `staging_raw.csv` -> `staging_raw`
- `job_run_log.csv` -> `job_run_log`
- `data_quality_check.csv` -> `data_quality_check`

当前说明：
- bootstrap 的 CSV 字段比当前 MySQL 入库字段更全；现阶段以脚本 `persist()` 中实际写入列为准
- `index_daily_raw / index_daily_feature / trading_calendar` 目前已产 CSV，但还未进入 bootstrap 的 MySQL 主写入路径

### 11.2 generator
- `candidate_{generation_batch_id}.csv`：当前只作为审核输入，不直接写 MySQL
- `generator_debug_{generation_batch_id}.csv` / `generator_run_log_{generation_batch_id}.csv`：当前为离线诊断产物，不写 MySQL

### 11.3 review_publish
- `challenge_{publish_batch_id}.csv` -> `challenge`
- `challenge_day_{publish_batch_id}.csv` -> `challenge_day`
- `publish_success_{publish_batch_id}.csv` / `publish_failed_{publish_batch_id}.csv` / `publish_run_log_{publish_batch_id}.csv`：当前为离线审计产物，不写 MySQL

## 15. 当前联调结论更新方式
若联调中发现：
- 输入字段口径变化
- 命令执行路径容易误用
- 输出目录存在歧义
- reviewed CSV 模板需要补充
- MySQL 联调有固定坑点

应优先更新：
1. 本文档 `docs/script-runbook.md`
2. `docs/stage-review.md`
3. 必要时再更新 `README.md` 或 `AGENTS.md`
