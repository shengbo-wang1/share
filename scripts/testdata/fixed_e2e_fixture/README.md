# fixed_e2e_fixture

这套夹具用于 **generator -> reviewed -> publish** 的最小正向闭环联调。

## 用途
- 当 bootstrap 因上游风控或接口抖动不可用时，继续验证后链路
- 提供 1 套稳定的 breakout 正例，不覆盖全部标签/失败场景

## 固定预期
- `generation_batch_id = fixture-e2e`
- `publish_batch_id = fixture-publish-e2e`
- generator 预期只产出 1 条 candidate：
  - `candidate_key = 600519.SH_2024-01-02`
  - `primary_tag = 放量突破 vs 假突破`
  - `difficulty = normal`
- publish 预期：
  - `challenge_id = 600519.SH_2024-01-02_breakout_v1`
  - `challenge_day` 恰好 20 行

## 文件定位
- `bootstrap_output/bootstrap-fixture-e2e/`：模拟 bootstrap 成功批次
- `reviewed_candidate_fixture-e2e.csv`：人工联调用的静态 reviewed 样本
- `manifest.json`：机器可读的锁定字段和预期结果

## 防漂移约定
- 静态 reviewed CSV 只保留最小合法 JSON，不再复制 generator 的完整 explain 输出
- 自动化测试中的 publish smoke 会先跑 generator，再从 candidate 派生 reviewed CSV
- 若 generator 规则变化：
  - 必须同步检查 `candidate_key / primary_tag / difficulty / challenge_id`
  - `score_explain_json / rule_flags_json` 的细节允许变化
