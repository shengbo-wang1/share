# 特征口径伪代码（v1 公式收敛版）

本文把 challenge 规则中已经出现的核心特征，收敛成**可直接编码的公式与伪代码规范**。目标不是重新定义题库标签，而是让实现者对“每个特征到底怎么算”不再做二次判断。

## 1. 总口径与设计原则

### 1.1 核心原则
- 默认价格基准使用 **QFQ**：`qfq_open / qfq_high / qfq_low / qfq_close`。
- 原始价只继续用于：
  - 服务端结算
  - `float_mv_est = raw_close * outstanding_share`
  - 与真实成交执行直接相关的回测口径
- 所有**基础特征**默认按 `trade_date = t` 的 as-of 口径计算，只能使用 `t` 及以前数据，严禁前视。
- 停牌、缺失、窗口不足时不做插值、不做补值，直接返回 `null`，由 candidate 过滤层决定是否剔除。
- 分母可能为 0 时统一使用 `eps = 1e-8` 做防护，并记为 `data_quality_check` 的关注项。

### 1.2 两类特征
第一版把特征分成两类，避免口径冲突：

#### A. 基础特征
- 用于趋势、形态、量能、指标判断
- 必须严格遵守 as-of `t` 口径
- 适合直接落入 `stock_daily_feature` 或在 generator 中按窗口即时计算

#### B. 标签验证特征
- 只用于**离线 challenge 生成时的标签语义确认**
- 不进入前端展示接口
- 第一版仅保留少量，例如：
  - `repair_signal_next_day`
- 这类特征可以使用 `t+1` 做离线语义验证，但不能反向污染用户在 `t` 日可见的信息口径

### 1.3 单特征文档模板
每个特征统一写成以下结构：
- `FeatureName`
- 用途
- 输入
- 公式
- 伪代码
- 最小样本要求
- 边界/异常
- 被哪些标签使用

---

## 2. 核心基础特征公式

以下特征为第一版必须统一的核心特征。

### 2.1 价格/形态类

#### FeatureName: `pct_change_n`
- **用途**：表达近 `n` 日累计涨跌幅。
- **输入**：`qfq_close[t]`, `qfq_close[t-n]`
- **公式**：
  - `pct_change_n = (qfq_close[t] / qfq_close[t-n]) - 1`
- **伪代码**：
```python
def pct_change_n(qfq_close, t, n):
    if t - n < 0:
        return null
    base = qfq_close[t - n]
    if base is null or abs(base) < eps:
        return null
    return qfq_close[t] / base - 1
```
- **最小样本要求**：`n + 1` 个有效收盘价。
- **边界/异常**：基准价缺失或为 0 时返回 `null`。
- **被哪些标签使用**：下跌中继、高位放量阴线、连续上涨后止盈。

#### FeatureName: `body_ratio`
- **用途**：衡量实体强弱。
- **输入**：`qfq_open[t]`, `qfq_close[t]`, `qfq_high[t]`, `qfq_low[t]`
- **公式**：
  - `body_ratio = abs(qfq_close[t] - qfq_open[t]) / max(qfq_high[t] - qfq_low[t], eps)`
- **伪代码**：
```python
def body_ratio(qfq_open, qfq_high, qfq_low, qfq_close, t):
    total_range = qfq_high[t] - qfq_low[t]
    return abs(qfq_close[t] - qfq_open[t]) / max(total_range, eps)
```
- **最小样本要求**：当日 OHLC 完整。
- **边界/异常**：若 `high < low`，返回 `null` 并记脏数据。
- **被哪些标签使用**：高位放量阴线。

#### FeatureName: `upper_shadow_ratio`
- **用途**：衡量上影占比。
- **输入**：`qfq_open[t]`, `qfq_close[t]`, `qfq_high[t]`, `qfq_low[t]`
- **公式**：
  - `upper_shadow_ratio = (qfq_high[t] - max(qfq_open[t], qfq_close[t])) / max(qfq_high[t] - qfq_low[t], eps)`
- **伪代码**：
```python
def upper_shadow_ratio(qfq_open, qfq_high, qfq_low, qfq_close, t):
    total_range = qfq_high[t] - qfq_low[t]
    upper = qfq_high[t] - max(qfq_open[t], qfq_close[t])
    return upper / max(total_range, eps)
```
- **最小样本要求**：当日 OHLC 完整。
- **边界/异常**：若影线值为负，说明 OHLC 非法，返回 `null`。
- **被哪些标签使用**：高位放量阴线。

#### FeatureName: `lower_shadow_ratio`
- **用途**：衡量下影占比。
- **输入**：`qfq_open[t]`, `qfq_close[t]`, `qfq_high[t]`, `qfq_low[t]`
- **公式**：
  - `lower_shadow_ratio = (min(qfq_open[t], qfq_close[t]) - qfq_low[t]) / max(qfq_high[t] - qfq_low[t], eps)`
- **伪代码**：
```python
def lower_shadow_ratio(qfq_open, qfq_high, qfq_low, qfq_close, t):
    total_range = qfq_high[t] - qfq_low[t]
    lower = min(qfq_open[t], qfq_close[t]) - qfq_low[t]
    return lower / max(total_range, eps)
```
- **最小样本要求**：当日 OHLC 完整。
- **边界/异常**：若影线值为负，说明 OHLC 非法，返回 `null`。
- **被哪些标签使用**：大盘恐慌日抄底、修复语义辅助。

#### FeatureName: `distance_to_ma20`
- **用途**：衡量当前价与 MA20 的乖离。
- **输入**：`qfq_close[t]`, `ma20[t]`
- **公式**：
  - `distance_to_ma20 = (qfq_close[t] / ma20[t]) - 1`
- **伪代码**：
```python
def distance_to_ma20(qfq_close, ma20, t):
    if ma20[t] is null or abs(ma20[t]) < eps:
        return null
    return qfq_close[t] / ma20[t] - 1
```
- **最小样本要求**：MA20 已可计算。
- **边界/异常**：MA20 不存在则返回 `null`。
- **被哪些标签使用**：下跌中继、高位放量阴线、缩量回踩均线、连续上涨后止盈。

#### FeatureName: `above_ma5 / above_ma10 / above_ma20`
- **用途**：表达是否站上关键均线。
- **输入**：`qfq_close[t]`, `ma5[t]`, `ma10[t]`, `ma20[t]`
- **公式**：
  - `above_maX = qfq_close[t] >= maX[t]`
- **伪代码**：
```python
def above_ma(qfq_close, ma, t):
    if ma[t] is null:
        return null
    return qfq_close[t] >= ma[t]
```
- **最小样本要求**：对应均线可计算。
- **边界/异常**：均线为空返回 `null`。
- **被哪些标签使用**：放量突破、下跌中继、缩量回踩均线。

### 2.2 量能类

#### FeatureName: `vol_ratio_1d_5d`
- **用途**：衡量当日量能相对前 5 日均量的放大倍数。
- **输入**：`volume[t]`, `volume[t-5:t-1]`
- **公式**：
  - `vol_ratio_1d_5d = volume[t] / mean(volume[t-5:t-1])`
- **伪代码**：
```python
def vol_ratio_1d_5d(volume, t):
    if t - 5 < 0:
        return null
    base = mean(volume[t-5:t])
    if base is null or abs(base) < eps:
        return null
    return volume[t] / base
```
- **最小样本要求**：前 5 个有效成交量。
- **边界/异常**：均量为 0 返回 `null`。
- **被哪些标签使用**：下跌中继、放量突破、高位放量阴线。

#### FeatureName: `vol_ratio_1d_10d`
- **用途**：衡量当日量能相对前 10 日均量的放大倍数。
- **输入**：`volume[t]`, `volume[t-10:t-1]`
- **公式**：
  - `vol_ratio_1d_10d = volume[t] / mean(volume[t-10:t-1])`
- **伪代码**：
```python
def vol_ratio_1d_10d(volume, t):
    if t - 10 < 0:
        return null
    base = mean(volume[t-10:t])
    if base is null or abs(base) < eps:
        return null
    return volume[t] / base
```
- **最小样本要求**：前 10 个有效成交量。
- **边界/异常**：均量为 0 返回 `null`。
- **被哪些标签使用**：放量突破。

#### FeatureName: `vol_shrink_ratio`
- **用途**：衡量回踩阶段是否缩量。
- **输入**：
  - `pullback_range`
  - `rise_range`
  - 两阶段 `volume`
- **公式**：
  - `vol_shrink_ratio = mean(volume[pullback_range]) / mean(volume[rise_range])`
- **伪代码**：
```python
def vol_shrink_ratio(volume, pullback_range, rise_range):
    if not pullback_range or not rise_range:
        return null
    pullback_mean = mean(volume[i] for i in pullback_range)
    rise_mean = mean(volume[i] for i in rise_range)
    if rise_mean is null or abs(rise_mean) < eps:
        return null
    return pullback_mean / rise_mean
```
- **最小样本要求**：上涨阶段、回踩阶段都至少 2 个交易日。
- **边界/异常**：阶段切分失败时返回 `null`。
- **被哪些标签使用**：缩量回踩均线。

### 2.3 趋势类

#### FeatureName: `ma_bull_alignment`
- **用途**：判断均线是否多头排列。
- **输入**：`ma5[t]`, `ma10[t]`, `ma20[t]`
- **公式**：
  - `ma_bull_alignment = ma5[t] > ma10[t] > ma20[t]`
- **伪代码**：
```python
def ma_bull_alignment(ma5, ma10, ma20, t):
    if ma5[t] is null or ma10[t] is null or ma20[t] is null:
        return null
    return ma5[t] > ma10[t] and ma10[t] > ma20[t]
```
- **最小样本要求**：MA20 已可计算。
- **边界/异常**：任一均线为空返回 `null`。
- **被哪些标签使用**：缩量回踩均线。

#### FeatureName: `ma_bear_alignment`
- **用途**：判断均线是否空头排列。
- **输入**：`ma5[t]`, `ma10[t]`, `ma20[t]`
- **公式**：
  - `ma_bear_alignment = ma5[t] < ma10[t] < ma20[t]`
- **伪代码**：
```python
def ma_bear_alignment(ma5, ma10, ma20, t):
    if ma5[t] is null or ma10[t] is null or ma20[t] is null:
        return null
    return ma5[t] < ma10[t] and ma10[t] < ma20[t]
```
- **最小样本要求**：MA20 已可计算。
- **边界/异常**：任一均线为空返回 `null`。
- **被哪些标签使用**：下跌中继辅助判断。

#### FeatureName: `below_ma20_days`
- **用途**：统计近窗口中位于 MA20 下方的天数。
- **输入**：近 `n` 日 `qfq_close`, `ma20`
- **公式**：
  - `below_ma20_days = count(qfq_close[i] < ma20[i])`
- **伪代码**：
```python
def below_ma20_days(qfq_close, ma20, start, end):
    if any(ma20[i] is null for i in range(start, end + 1)):
        return null
    cnt = 0
    for i in range(start, end + 1):
        if qfq_close[i] < ma20[i]:
            cnt += 1
    return cnt
```
- **最小样本要求**：窗口内 MA20 全部可用。
- **边界/异常**：窗口内任一均线缺失返回 `null`。
- **被哪些标签使用**：下跌中继。

#### FeatureName: `trend_up_days`
- **用途**：表达近 `n` 日上行趋势的持续性。
- **输入**：`qfq_close`, `qfq_high`
- **公式**：
  - 默认按 `close[i] > close[i-1]` 的累计天数
  - 若 `close[t]` 同时创近 `n` 日新高，则增强趋势确认
- **伪代码**：
```python
def trend_up_days(qfq_close, qfq_high, t, n):
    if t - n + 1 < 1:
        return null
    cnt = 0
    for i in range(t - n + 1, t + 1):
        if qfq_close[i] > qfq_close[i - 1]:
            cnt += 1
    new_high = qfq_close[t] >= max(qfq_high[t - n + 1:t + 1])
    return {"up_days": cnt, "new_high_confirm": new_high}
```
- **最小样本要求**：至少 `n` 日有效价格。
- **边界/异常**：第一天不足对比样本时返回 `null`。
- **被哪些标签使用**：连续上涨后止盈。

#### FeatureName: `trend_down_days`
- **用途**：表达近 `n` 日下行趋势的持续性。
- **输入**：`qfq_close`, `qfq_low`
- **公式**：
  - 默认按 `close[i] < close[i-1]` 的累计天数
  - 若 `close[t]` 同时创近 `n` 日新低，则增强趋势确认
- **伪代码**：
```python
def trend_down_days(qfq_close, qfq_low, t, n):
    if t - n + 1 < 1:
        return null
    cnt = 0
    for i in range(t - n + 1, t + 1):
        if qfq_close[i] < qfq_close[i - 1]:
            cnt += 1
    new_low = qfq_close[t] <= min(qfq_low[t - n + 1:t + 1])
    return {"down_days": cnt, "new_low_confirm": new_low}
```
- **最小样本要求**：至少 `n` 日有效价格。
- **边界/异常**：第一天不足对比样本时返回 `null`。
- **被哪些标签使用**：下跌中继。

### 2.4 波动/结构类

#### FeatureName: `amplitude_n`
- **用途**：衡量近 `n` 日价格区间振幅。
- **输入**：近 `n` 日 `qfq_high`, `qfq_low`
- **公式**：
  - `amplitude_n = (max(qfq_high[t-n+1:t]) / min(qfq_low[t-n+1:t])) - 1`
- **伪代码**：
```python
def amplitude_n(qfq_high, qfq_low, t, n):
    if t - n + 1 < 0:
        return null
    window_high = max(qfq_high[t-n+1:t+1])
    window_low = min(qfq_low[t-n+1:t+1])
    if window_low is null or abs(window_low) < eps:
        return null
    return window_high / window_low - 1
```
- **最小样本要求**：`n` 日高低价完整。
- **边界/异常**：最低价为 0 返回 `null`。
- **被哪些标签使用**：平台宽度、难度辅助。

#### FeatureName: `volatility_n`
- **用途**：衡量近 `n` 日日收益波动率。
- **输入**：近 `n` 日日收益率
- **公式**：
  - `volatility_n = std(daily_return[t-n+1:t])`
- **伪代码**：
```python
def volatility_n(qfq_close, t, n):
    if t - n < 0:
        return null
    returns = []
    for i in range(t - n + 1, t + 1):
        if abs(qfq_close[i - 1]) < eps:
            return null
        returns.append(qfq_close[i] / qfq_close[i - 1] - 1)
    return std(returns)
```
- **最小样本要求**：`n + 1` 个收盘价。
- **边界/异常**：收益序列不完整返回 `null`。
- **被哪些标签使用**：难度判断。

#### FeatureName: `platform_width`
- **用途**：判断突破前平台是否足够窄。
- **输入**：突破日前 10 日 `qfq_high`, `qfq_low`
- **公式**：
  - `platform_width = (max(qfq_high[t-10:t-1]) / min(qfq_low[t-10:t-1])) - 1`
- **伪代码**：
```python
def platform_width(qfq_high, qfq_low, t, lookback=10):
    start = t - lookback
    end = t - 1
    if start < 0:
        return null
    high_ = max(qfq_high[start:end+1])
    low_ = min(qfq_low[start:end+1])
    if low_ is null or abs(low_) < eps:
        return null
    return high_ / low_ - 1
```
- **最小样本要求**：突破日前完整 10 日窗口。
- **边界/异常**：用于“突破日”判断时，`t` 必须是候选突破日。
- **被哪些标签使用**：放量突破 vs 假突破。

#### FeatureName: `false_break_retrace`
- **用途**：度量突破后 1~3 日是否快速回落。
- **输入**：
  - `breakout_day = t`
  - `qfq_open[t]`, `qfq_close[t]`
  - `qfq_low[t+1:t+3]`
- **公式**：
  - `breakout_body = max(abs(qfq_close[t] - qfq_open[t]), eps)`
  - `false_break_retrace = (qfq_close[t] - min_low_after_breakout) / breakout_body`
- **伪代码**：
```python
def false_break_retrace(qfq_open, qfq_close, qfq_low, t):
    if t + 3 >= len(qfq_low):
        return null
    breakout_body = max(abs(qfq_close[t] - qfq_open[t]), eps)
    min_low = min(qfq_low[t+1:t+4])
    return (qfq_close[t] - min_low) / breakout_body
```
- **最小样本要求**：突破日后至少 3 个交易日。
- **边界/异常**：
  - 这是**离线标签评估特征**，只用于出题，不可作为用户当日可见信息。
  - 若后续 3 日不足，则当前窗口不能参与该标签自动判定。
- **被哪些标签使用**：放量突破 vs 假突破。

### 2.5 指标类

#### FeatureName: `kdj_golden_cross / kdj_dead_cross`
- **用途**：识别 K 线上穿 / 下穿 D。
- **输入**：`k_value[t-1:t]`, `d_value[t-1:t]`
- **公式**：
  - `golden = k[t-1] <= d[t-1] and k[t] > d[t]`
  - `dead = k[t-1] >= d[t-1] and k[t] < d[t]`
- **伪代码**：
```python
def kdj_cross(k_value, d_value, t):
    if t - 1 < 0:
        return {"golden": null, "dead": null}
    golden = k_value[t-1] <= d_value[t-1] and k_value[t] > d_value[t]
    dead = k_value[t-1] >= d_value[t-1] and k_value[t] < d_value[t]
    return {"golden": golden, "dead": dead}
```
- **最小样本要求**：至少 2 个交易日 KDJ。
- **边界/异常**：任一 K/D 为空返回 `null`。
- **被哪些标签使用**：下跌中继、缩量回踩均线、连续上涨后止盈。

#### FeatureName: `macd_golden_cross / macd_dead_cross`
- **用途**：识别 DIF 上穿 / 下穿 DEA。
- **输入**：`dif[t-1:t]`, `dea[t-1:t]`
- **公式**：
  - `golden = dif[t-1] <= dea[t-1] and dif[t] > dea[t]`
  - `dead = dif[t-1] >= dea[t-1] and dif[t] < dea[t]`
- **伪代码**：
```python
def macd_cross(dif, dea, t):
    if t - 1 < 0:
        return {"golden": null, "dead": null}
    golden = dif[t-1] <= dea[t-1] and dif[t] > dea[t]
    dead = dif[t-1] >= dea[t-1] and dif[t] < dea[t]
    return {"golden": golden, "dead": dead}
```
- **最小样本要求**：至少 2 个交易日 MACD。
- **边界/异常**：任一 DIF/DEA 为空返回 `null`。
- **被哪些标签使用**：下跌中继、连续上涨后止盈。

#### FeatureName: `macd_hist_shrinking`
- **用途**：识别 MACD 柱体动能衰减。
- **输入**：`macd[t-1]`, `macd[t]`
- **公式**：
  - `macd_hist_shrinking = abs(macd[t]) < abs(macd[t-1])`
- **伪代码**：
```python
def macd_hist_shrinking(macd, t):
    if t - 1 < 0 or macd[t] is null or macd[t-1] is null:
        return null
    return abs(macd[t]) < abs(macd[t-1])
```
- **最小样本要求**：至少 2 个交易日 MACD 柱值。
- **边界/异常**：空值返回 `null`。
- **被哪些标签使用**：连续上涨后止盈。

#### FeatureName: `j_extreme_high / j_extreme_low`
- **用途**：识别 J 值极端超买 / 超卖。
- **输入**：`j_value[t]`
- **公式**：
  - `j_extreme_high = j_value[t] >= 90`
  - `j_extreme_low = j_value[t] <= 10`
- **伪代码**：
```python
def j_extreme(j_value, t):
    if j_value[t] is null:
        return {"high": null, "low": null}
    return {
        "high": j_value[t] >= 90,
        "low": j_value[t] <= 10,
    }
```
- **最小样本要求**：当日 J 值完整。
- **边界/异常**：空值返回 `null`。
- **被哪些标签使用**：连续上涨后止盈、下跌中继辅助。

### 2.6 指数协同类

#### FeatureName: `relative_strength_vs_index`
- **用途**：判断恐慌日个股是否相对指数抗跌。
- **输入**：
  - `stock_pct_change_1d`
  - `index_drop_1d`
- **公式**：
  - `relative_strength_vs_index = stock_pct_change_1d - index_drop_1d`
- **伪代码**：
```python
def relative_strength_vs_index(stock_pct_change_1d, index_drop_1d):
    if stock_pct_change_1d is null or index_drop_1d is null:
        return null
    return stock_pct_change_1d - index_drop_1d
```
- **最小样本要求**：股价与指数当日跌幅都可得。
- **边界/异常**：指数缺失直接返回 `null`。
- **被哪些标签使用**：大盘恐慌日抄底。

#### FeatureName: `long_lower_shadow_signal`
- **用途**：识别恐慌日中的长下影修复信号。
- **输入**：`lower_shadow_ratio[t]`, `body_ratio[t]`
- **公式**：
  - 默认信号：`lower_shadow_ratio >= 0.35 and lower_shadow_ratio > body_ratio`
- **伪代码**：
```python
def long_lower_shadow_signal(lower_shadow_ratio, body_ratio):
    if lower_shadow_ratio is null or body_ratio is null:
        return null
    return lower_shadow_ratio >= 0.35 and lower_shadow_ratio > body_ratio
```
- **最小样本要求**：当日形态特征完整。
- **边界/异常**：形态特征为空返回 `null`。
- **被哪些标签使用**：大盘恐慌日抄底。

#### FeatureName: `repair_signal_next_day`
- **用途**：用次日修复迹象确认恐慌日抄底语义是否成立。
- **输入**：
  - `qfq_close[t]`
  - `qfq_open[t+1]`, `qfq_close[t+1]`, `volume[t+1]`
- **公式**：
  - 默认满足以下任一项：
    - `qfq_close[t+1] > qfq_close[t]`
    - `qfq_close[t+1] > qfq_open[t+1]`
    - `vol_ratio_1d_5d[t+1] >= 1.1 and qfq_close[t+1] >= qfq_close[t]`
- **伪代码**：
```python
def repair_signal_next_day(qfq_open, qfq_close, vol_ratio_1d_5d, t):
    if t + 1 >= len(qfq_close):
        return null
    cond1 = qfq_close[t+1] > qfq_close[t]
    cond2 = qfq_close[t+1] > qfq_open[t+1]
    cond3 = (
        vol_ratio_1d_5d[t+1] is not null
        and vol_ratio_1d_5d[t+1] >= 1.1
        and qfq_close[t+1] >= qfq_close[t]
    )
    return cond1 or cond2 or cond3
```
- **最小样本要求**：`t+1` 必须存在。
- **边界/异常**：
  - 这是**标签验证特征**，不是前端可见特征。
  - 若 `t+1` 不存在，则第 5 类标签不自动命中。
- **被哪些标签使用**：大盘恐慌日抄底。

---

## 3. 默认边界规则与统一约定

### 3.1 缺失与空值
- 窗口不足：返回 `null`
- 停牌/缺失：返回 `null`
- 不插值、不补值、不前向填充

### 3.2 分母与数值稳定性
- 所有分母统一使用 `max(value, eps)` 防止除零
- 若业务上分母本不应为 0，但实际为 0：
  - 特征结果返回 `null` 或保底值
  - 同时记录到 `data_quality_check`

### 3.3 前视边界
- 基础特征禁止使用未来数据
- 只有文档明确标注为“标签验证特征”的指标，允许在 challenge 离线生成阶段使用 `t+1 ~ t+3`
- 这类特征不能进入前端展示口径，也不能反向解释为用户在 `t` 日当下可见

### 3.4 均线与指标口径
- MA、KDJ、MACD 默认都基于 **QFQ** 数据
- 若后续实现要把它们落入 `stock_daily_feature`，必须与本文件公式一致

---

## 4. 与 challenge 规则的映射示例

本节只说明“特征如何被 generator 调用”，不重写整套 generator 流程。

### 4.1 `下跌中继 vs 真见底`
**输入窗口**
- `t-20 ~ t`

**先算特征**
- `pct_change_10`
- `below_ma20_days`
- `distance_to_ma20`
- `vol_ratio_1d_5d`
- `kdj_golden_cross`
- `macd_golden_cross`

**再做判断**
```python
if pct_change_10 <= -0.12 \
   and below_ma20_days >= 7 \
   and distance_to_ma20 < 0.02 \
   and vol_ratio_1d_5d < 1.2:
    hit_tag = "下跌中继 vs 真见底"
```

**直接剔除**
- `pct_change_10` 不可算
- MA20 不完整
- KDJ / MACD 不完整

### 4.2 `放量突破 vs 假突破`
**输入窗口**
- 平台观察区：`t-10 ~ t-1`
- 突破验证区：`t ~ t+3`

**先算特征**
- `platform_width`
- `pct_change_3`
- `vol_ratio_1d_5d`
- `vol_ratio_1d_10d`
- `false_break_retrace`
- `above_ma20`

**再做判断**
```python
if platform_width <= 0.12 \
   and pct_change_1d(t) >= 0.04 \
   and vol_ratio_1d_5d >= 1.8 \
   and vol_ratio_1d_10d >= 1.5:
    hit_primary = "放量突破 vs 假突破"

if false_break_retrace is not null and false_break_retrace >= 0.5:
    semantic = "假突破增强"
```

**直接剔除**
- 平台窗口不足
- 突破后 3 日不足且又必须判假突破
- 一字板或异常跳空

### 4.3 `缩量回踩均线`
**输入窗口**
- 上涨阶段 + 回踩阶段，均位于候选 20 日窗口内

**先算特征**
- `ma_bull_alignment`
- `vol_shrink_ratio`
- `distance_to_ma20`
- `pct_change_n`
- `kdj_golden_cross`

**再做判断**
```python
if ma_bull_alignment is true \
   and 0.03 <= pullback_pct <= 0.08 \
   and vol_shrink_ratio <= 0.75 \
   and distance_to_ma20 > -0.02:
    hit_tag = "缩量回踩均线"
```

**直接剔除**
- 无法切出上涨阶段 / 回踩阶段
- 回踩阶段明显放量下跌

### 4.4 `大盘恐慌日该不该抄底`
**输入窗口**
- 个股恐慌日：`t`
- 指数窗口：`t-5 ~ t`
- 修复验证：必要时使用 `t+1`

**先算特征**
- `index_drop_1d`
- `index_drawdown_5d`
- `index_panic_flag`
- `relative_strength_vs_index`
- `long_lower_shadow_signal`
- `repair_signal_next_day`

**再做判断**
```python
panic_candidate = (
    index_drop_1d <= -0.03
    or index_drawdown_5d <= -0.08
)

panic_confirm = (
    index_vol_spike is true
    or index_panic_flag is true
)

stock_repair = (
    long_lower_shadow_signal is true
    or relative_strength_vs_index >= 0.02
    or repair_signal_next_day is true
)

if panic_candidate and panic_confirm and stock_repair:
    hit_tag = "大盘恐慌日该不该抄底"
```

**直接剔除**
- 指数数据缺失
- `index_daily_feature` 质检未通过
- 恐慌日个股属于独立利空崩跌

---

## 5. 统一术语表

### 平台
- 工程定义：突破日前连续 10 个交易日内，`platform_width <= 0.12` 的整理区间。

### 突破日
- 工程定义：当日涨幅明显、成交量显著放大，并且收盘价有效站上平台区间上沿的交易日。

### 回踩阶段
- 工程定义：近端上涨后，价格向 MA5 / MA10 / MA20 回落的连续 2~5 个交易日区间。

### 上涨阶段
- 工程定义：回踩前最近一段连续推升区间，通常对应回踩前 3~8 个交易日。

### 修复信号
- 工程定义：长下影、相对指数抗跌、次日修复迹象三者中的至少一个成立。

### 相对指数抗跌
- 工程定义：`relative_strength_vs_index >= 0.02`，即个股当日跌幅至少比参考指数少 2 个百分点。

### 次日修复迹象
- 工程定义：`repair_signal_next_day = true`。

### 高位
- 工程定义：近 15 日累计涨幅 `>= 0.20`，且 `distance_to_ma20 >= 0.08`。

### 健康回踩
- 工程定义：均线仍保持多头结构、回踩幅度处于 `0.03 ~ 0.08`、且 `vol_shrink_ratio <= 0.75`。

---

## 6. 最终约定
- `docs/challenge-generation-rules.md` 负责定义标签与阈值。
- 本文负责定义**特征公式与伪代码**。
- 若两份文档冲突：
  - 特征计算口径以本文为准
  - 标签业务阈值与优先级以 `docs/challenge-generation-rules.md` 为准
