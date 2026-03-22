# generator_failure_fixture

这套夹具用于 **challenge_generator.py** 的离线失败/半失败复现与回归测试。

## 第一轮覆盖
- `review_required`：两标签强冲突，但仍进入人工池
- `no_candidate`：输入完整，但所有标签都不命中
- `insufficient_trade_days`：交易日不足 `20 + 3`
- `unresolvable_tag_conflict`：三标签强冲突，被 candidate gate 拒绝

## 目录说明
- `bootstrap_cases/`：每个场景一套最小 `stock_basic/raw/feature` 输入
- `manifest.json`：机器可读的场景清单、预期状态、关键 debug reason

## 说明
- 每个样本只承担一种主语义
- 失败样本优先追求稳定可复现，不追求完全拟真
