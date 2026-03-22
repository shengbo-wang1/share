# publish_failure_fixture

这套夹具用于 **review_publish.py** 的离线失败复现与回归测试。

## 设计原则
- 每个样本只对应一种失败语义
- 共享行情输入直接复用 `fixed_e2e_fixture`
- 重点验证 `publish_failed.csv`、`publish_run_log.csv` 和 fail reason 口径

## 第一轮覆盖
- `REVIEWED_CSV_MISSING_COLUMNS`
- `DUAL_ADJUSTMENT_NOT_ALLOWED`
- `CHALLENGE_ID_CONFLICT`
- `PUBLISH_BUILD_FAILED`

## 目录说明
- `reviewed_cases/`：每个失败场景一份 reviewed CSV
- `manifest.json`：机器可读的样本清单、输入来源、预期失败码

## 使用说明
- 大部分样本都直接复用：
  - `share/scripts/testdata/fixed_e2e_fixture/bootstrap_output/bootstrap-fixture-e2e/stock_daily_raw.csv`
  - `share/scripts/testdata/fixed_e2e_fixture/bootstrap_output/bootstrap-fixture-e2e/stock_daily_feature.csv`
- `challenge_id_conflict` 场景需要在输出目录预先放一个同 `challenge_id` 的 `challenge_*.csv`

## 预期
- 失败样本优先追求**稳定可复现**
- 不追求完全拟真，也不覆盖真实审核流中的全部错误组合
