# AKShare 数据初始化说明

## 目标
离线生成：
- 原始日线：结算用
- 前复权日线：展示与指标用
- MA / KDJ / MACD
- `outstanding_share` 与 `float_mv_est`
- `cap_bucket`
- challenge 种子数据

## 推荐流程
1. 用交易所股票列表接口生成 `stock_basic`：
   - `stock_info_sh_name_code(symbol="主板A股")`
   - `stock_info_sz_name_code(symbol="A股列表")`
   - `stock_info_bj_name_code()`
   - 若交易所列表接口失败，可回退到 `stock_zh_a_spot_em()` 作为股票池 / 名称补充源
2. 用 `tool_trade_date_hist_sina()` 生成 `trading_calendar`。
3. 用 `stock_zh_a_hist(symbol, period="daily", adjust="")` 拉原始日线。
4. 用 `stock_zh_a_hist(symbol, period="daily", adjust="qfq")` 拉前复权日线。
5. 用 `stock_zh_index_daily_em` 拉沪深核心 3 指数。
6. 按交易日对齐，生成 `stock_daily_raw`、`stock_daily_feature`、`index_daily_raw` 与 `index_daily_feature`。
7. 计算：
   - MA5 / 10 / 20
   - KDJ(9,3,3)
   - MACD(12,26,9)
8. 用 `stock_zh_a_hist` 自带的 `换手率` 反推 `outstanding_share_est`，再用 `raw_close * outstanding_share_est` 近似出 `float_mv_est`。
9. 每个交易日按全市场分位打 `small / mid / large`。
10. 过滤停牌过长、指标窗口不足、上市时间过短的样本，生成 `challenge`。

## 当前主链路原则
- 主行情唯一使用 `stock_zh_a_hist`
- `stock_zh_a_daily` 不再作为 bootstrap 主链路依赖
- `float_mv_est` 继续是估算值，不是精确历史流通市值
- `stock_zh_a_spot_em()` 只作为股票池候选源 / fallback，不作为正式静态主数据唯一来源

## 为什么展示与结算分离
- 展示：前复权 K 线连续，更适合训练和观察图形。
- 结算：原始价格更适合按真实交易价格回放。

## 第一版建议
- 先跑沪深主板 + 创业板核心股票池。
- challenge 先做 100~300 道，便于人工质检。
- 题目标签可先人工 + 简单规则混合生成。
