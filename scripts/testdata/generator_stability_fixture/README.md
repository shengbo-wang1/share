# generator_stability_fixture

这套夹具用于 **challenge_generator.py** 的规则稳定性 anti-drift 回归。

## 第一轮覆盖
- `easy_clear_signal`：单标签、低冲突、稳定产出 `easy`
- `secondary_tag_explanatory`：主标签明确且带解释型 secondary，稳定产出 `normal`
- `index_missing_but_candidate_survives`：无指数特征时第 5 类标签停用，但其他标签仍可出题

## 目录说明
- `bootstrap_cases/`：每个场景一套最小 `stock_basic/raw/feature` 输入
- `manifest.json`：机器可读的场景清单、预期状态、核心 candidate 字段、关键 debug reason

## 说明
- 这组样本用于锁核心规则行为，不追求覆盖全部标签全集
- 默认只锁高信号字段和关键 debug reason，不锁完整 explain JSON
