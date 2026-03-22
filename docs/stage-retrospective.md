# 阶段复盘（脚本实现与工程落地阶段）

这份文档用于把本阶段已经完成的工作、踩过的坑、形成的经验、当前不足与下一步重点系统沉淀下来，方便后续任何接力者快速回答：

- 这一阶段我们到底做了什么
- 这些东西具体是什么、解决了什么问题
- 哪些地方做得好、哪些地方踩了坑
- 当前还缺什么、下一阶段最应该先做什么

它是**阶段复盘与经验沉淀页**；当前状态判断仍以 `docs/stage-review.md` 为准，实施顺序仍以 `docs/roadmap.md` 为准。

## 1. 阶段目标与范围
这一阶段的核心目标，不是继续发散规则，而是把“已有规则文档”真正落到可以联调、可以诊断、可以重复回归的工程链路上。

重点范围包括：
- 后端 MVP 主链路保持可运行
- `akshare_bootstrap.py` 具备最小真实抓取与故障诊断能力
- `challenge_generator.py` 具备最小 candidate 生成与可解释调试能力
- `review_publish.py` 具备 reviewed CSV -> challenge/challenge_day 的最小发布链路
- 在实时抓取受阻时，仍能通过固定 fixture 跑通 generator / publish 与回归验证

## 2. 本阶段完成了什么
### 2.1 后端与规则基础没有丢
这一阶段并不是从零开始。进入脚本实现阶段前，项目已经有：
- 一个可运行的 Spring Boot 后端 MVP
- 20 日玩法主链路与结算规则
- 一套较完整的数据初始化、特征、题库、审核发布、MySQL 草案文档

这意味着后续脚本实现不是“边写边猜业务规则”，而是在既有规则框架下做工程落地。

### 2.2 bootstrap 从“能跑”推进到“出错时能看明白”
`share/scripts/akshare_bootstrap.py` 本阶段最重要的提升，不只是“去抓数据”，而是把抓取过程做成了**可诊断的链路**。

已经落地的能力包括：
- 统一的请求级诊断包装
- 失败重试与 attempt 日志
- `fetch_attempt_log.csv`
- `fetch_debug_log.jsonl`
- `symbol_run_log.csv`
- `index_fetch_log.csv`
- 对 `RemoteDisconnected` 的单独提示口径

这些能力具体解决的问题是：
- 不再只能看到一句 `RemoteDisconnected` 然后猜原因
- 可以区分：
  - 是否拿到了 HTTP response
  - 是否属于响应前断连
  - 是否是返回了异常页 / HTML / 验证码页
- 可以判断问题更像：
  - 参数错误
  - 临时网络问题
  - 上游连接级拒绝 / 风控

本阶段的关键结论也由此明确：
- 股票列表与交易日历接口可访问
- Eastmoney `push2his` 个股/指数 K 线接口在响应前断连
- 当前阻塞更像**连接级风控**，而不是 symbol/date 参数问题

### 2.3 generator 从“最小可跑版”推进到“有解释、有夹具、有回归”
`share/scripts/challenge_generator.py` 本阶段做的不是简单“能出 candidate”，而是把 generator 从黑盒推进到可解释、可回归的状态。

已经形成的能力包括：
- `candidate.csv` / `generator_debug.csv` / `generator_run_log.csv` 三类输出稳定落盘
- `tag_rule` 级别诊断：
  - `tag_hit_<标签>`
  - `tag_miss_<标签>`
  - `matched_conditions / missed_conditions / exclusion_reasons`
- `0 candidate` 时不再只剩一个抽象报错，而是能从 debug 看清卡在哪个标签、哪个条件
- 新增 `--allow-empty`
  - 默认行为保持不变，真实批处理时 `EMPTY` 仍算失败
  - fixture / 调试场景下显式传参时，`EMPTY` 不再把整条命令打断

这些能力具体解决的问题是：
- `0 candidate` 不再看起来像“脚本坏了”
- 可以把“规则未命中”“样本不足”“冲突被 gate 拒绝”分开看
- 可以稳定构建失败/半失败场景，而不依赖实时抓取结果

### 2.4 publish 从“最小发布”推进到“失败可落盘、重复跑不易崩”
`share/scripts/review_publish.py` 本阶段补强的重点在于：**发布失败不是崩掉，而是能被识别、落盘、复现**。

已经落地的能力包括：
- reviewed CSV -> `challenge/challenge_day` 最小发布链路
- `publish_success.csv`
- `publish_failed.csv`
- `publish_run_log.csv`
- 常见失败语义的固定失败码
- `challenge_id` 冲突检测
- 历史输出目录扫描时对空 `challenge_*.csv` 的容错

这些能力具体解决的问题是：
- 发布失败不再只剩 traceback
- 可以稳定区分：
  - 输入缺列
  - 双重人工调整不允许
  - `challenge_id` 冲突
  - 构建失败
- 连续运行正向 / 失败样本时，不会再因为空历史 CSV 直接崩掉

### 2.5 形成了固定 fixture + smoke 回归体系
这一阶段最有价值的工程成果之一，是把“联调依赖实时抓取成功”转换成了“有固定样本就能重复跑通后链路”。

当前仓库内已经形成 4 组固定夹具：

#### 1) `fixed_e2e_fixture`
这是一套**最小正向闭环样本**。

它提供：
- 一组 bootstrap-like 的固定输入 CSV
- 一份静态 reviewed CSV
- 一个可稳定生成 1 条 candidate、再发布 1 条 challenge 的样本

它解决的问题是：
- 即使 bootstrap 被封控，也能先把 generator / publish 主链路打通

#### 2) `publish_failure_fixture`
这是一组 `review_publish.py` 的**离线失败诊断样本**。

它覆盖了：
- `REVIEWED_CSV_MISSING_COLUMNS`
- `DUAL_ADJUSTMENT_NOT_ALLOWED`
- `CHALLENGE_ID_CONFLICT`
- `PUBLISH_BUILD_FAILED`

它解决的问题是：
- publish 失败场景可以稳定复现，不必手工拼随机 reviewed CSV

#### 3) `generator_failure_fixture`
这是一组 `challenge_generator.py` 的**失败/半失败样本**。

它覆盖了：
- `review_required`
- `no_candidate`
- `insufficient_trade_days`
- `unresolvable_tag_conflict`

它解决的问题是：
- generator 关键失败口径有了离线复现基础

#### 4) `generator_stability_fixture`
这是一组 generator 的**规则稳定性 anti-drift 样本**。

它覆盖了：
- `easy_clear_signal`
- `secondary_tag_explanatory`
- `index_missing_but_candidate_survives`

它解决的问题是：
- 后续改规则时，不会无感把关键标签/难度/review_status 行为改坏

#### 5) `fixture_smoke.py`
这是基于 manifest 的**一键离线回归入口**。

它会串行跑：
- fixed success
- publish failure fixtures
- generator failure fixtures
- generator stability fixtures

它解决的问题是：
- 不需要手工一条条敲命令验证所有固定样本
- 预期失败样本不会被误当成“整体 smoke 失败”

截至本次复盘，最近一次本地离线回归结果为：
- Python 单测：`18` 项通过
- `fixture_smoke.py`：`pass=12 fail=0`

这说明当前离线回归基线已经可用。

## 3. 这一阶段哪些地方做得好
### 3.1 从黑盒报错推进到了请求级 / 阶段级可诊断
这是这一阶段最明显的提升。

之前很多问题的表现是：
- “报错了”
- “断连了”
- “0 candidate 了”
- “publish 崩了”

现在至少可以做到：
- bootstrap 看请求级现场
- generator 看标签级命中/未命中
- publish 看失败码与失败清单

这使得问题从“猜”变成“定位”。

### 3.2 从依赖实时抓取推进到了固定 fixture 可重复回归
这一步非常关键。

如果没有固定夹具，bootstrap 一被风控，后面的 generator / publish 基本就跟着停摆。

这一阶段通过 fixed fixture、failure fixture、stability fixture，把后链路的推进从“等上游恢复”切换成了“先把自己能控的部分做扎实”。

### 3.3 从单点脚本测试推进到了 manifest + smoke 的离线闭环
以前更多是“我单独跑某个脚本看一下”。

现在已经形成：
- 夹具目录
- manifest
- 单元测试
- 一键 smoke

这代表脚本联调已经开始具备工程化回归能力，而不只是临时调试。

### 3.4 对“默认语义”和“调试语义”的边界处理比较克制
例如 generator 的 `--allow-empty` 做得比较稳：
- 默认行为不变
- 不伪装 `EMPTY` 为 `SUCCESS`
- 只是改善调试/fixture 场景下的使用体验

这类处理避免了为了调试方便而污染真实批处理语义。

## 4. 这一阶段踩了哪些坑
### 4.1 Eastmoney `RemoteDisconnected` / 响应前断连
这是本阶段最核心的外部阻塞。

踩坑点在于：
- 一开始只能看到 `RemoteDisconnected('Remote end closed connection without response')`
- 很容易误判成本地网络问题、参数问题或 akshare 黑盒问题

后来的经验是：
- 要同时记录“有无 response”与“请求侧上下文”
- 当股票/指数都在 100~200ms 内同类失败时，更像连接级拒绝/风控
- 这种问题不一定能拿到 response body，因此必须接受“无 body 可打印”的现实

### 4.2 generator 的 `0 candidate` 原先使用体验差
之前 `0 candidate` 直接抛异常，对调试阶段很不友好。

踩坑点在于：
- 预期无 candidate 的 fixture 场景也会表现得像“脚本坏了”
- 手工批量复现失败样本时会频繁被中断

这推动了：
- `--allow-empty`
- 更明确的 run log / debug 输出

### 4.3 publish 扫描历史输出目录时会被空 CSV 打断
之前 `review_publish.py` 扫描 `challenge_*.csv` 时，如果遇到空文件，会抛 `EmptyDataError`。

踩坑点在于：
- 这不是业务失败，而是读取侧容错不足
- 会把本来应该进入 `publish_failed.csv` 的失败样本，提前打断成 traceback

后续修复方向是正确的：
- 读取侧跳过空文件
- 不要求先手工清理历史目录才能继续调试

### 4.4 smoke 重跑时历史输出污染会导致误报冲突
一键 smoke 早期有一个很典型的问题：
- 同一个 `smoke_batch_id` 重跑时，会复用旧输出目录
- fixed success 里的 publish 会误判成 `CHALLENGE_ID_CONFLICT`

这个坑的本质是：
- 不是业务逻辑坏了
- 而是回归环境隔离不够

这也说明，做 smoke 时“重复运行可复现”本身就是一个需要单独验证的工程要求。

## 5. 当前不足、未完成项与风险
### 5.1 bootstrap 主链路仍受上游风控阻塞
这是当前最大的现实阻塞。

虽然 bootstrap 已经具备诊断能力，但“能诊断”不等于“已经恢复可用”。
当前仍未完成的关键点是：
- 真实抓取主链路的稳定恢复
- 新鲜 raw/feature 数据的持续产出

### 5.2 MySQL 仍未形成真实闭环
当前脚本层虽然已有可选 MySQL 参数与表结构文档，但整体还没有形成：
- CSV -> MySQL 的稳定联调
- 后端 repository -> MySQL 的稳定切换

所以当前 MySQL 仍处于“准备阶段”，不是“可作为主路径依赖”的状态。

### 5.3 真实数据回归仍不足，当前验证仍以 fixture 为主
固定夹具非常有价值，但它们主要解决的是：
- 离线可重复回归
- 稳定复现已知语义

它们不能完全替代：
- 真正来自 bootstrap 的多股票、多时段样本
- 对真实数据分布的规则鲁棒性验证

### 5.4 generator 规则仍不是最终版
当前 generator 的规则实现已经从“可跑通版”进步了很多，但仍不应当被视为最终稳定版。

仍需持续推进的包括：
- 更多边界样本
- 更多 anti-drift fixture
- 更真实样本下的规则校验

## 6. 目前哪些地方还可以优化
### 6.1 bootstrap 侧
- 继续补强退避、节流、恢复口径
- 把“连接级拒绝”的批次级提示做得更统一
- 抓取恢复后补一轮真实样本回归记录

### 6.2 generator 侧
- 继续补输入异常类 fixture
- 扩充 anti-drift 样本覆盖更多标签与难度边界
- 进一步压缩 `0 candidate` 时的排查路径

### 6.3 publish 侧
- 扩更多 reviewed CSV 失败样本
- 让失败码聚合与 run log 摘要更利于人工排查
- 为后续 MySQL 发布前校验预留更清晰的检查入口

### 6.4 smoke / 工具链侧
- 可以继续补 `suite/case filter`
- 可以补更安静的 summary-only 输出
- 可以补更适合人工阅读的终端汇总

### 6.5 文档侧
- runbook 中的调试记录可以继续规范化，避免时间线散乱
- 未来若阶段切换，需及时把本页与 `stage-review.md` 同步更新，避免“状态页”和“复盘页”脱节

## 7. 下一阶段重点与推进顺序
当前最建议的接力顺序如下：

### 7.1 等抓取窗口恢复后，回到 bootstrap 做单股短区间复测
这是第一优先级。

因为只有抓取恢复，才能重新验证：
- 真实 raw/feature 产出
- generator 在真实 batch 上的表现
- publish 对真实 candidate 的最小闭环

### 7.2 继续补 generator / publish 离线边界样本
在等待抓取恢复或真实回归期间，这仍然是最有性价比的工作。

优先方向：
- generator 输入异常样本
- publish 更多失败码样本
- 更强的 anti-drift 回归集

### 7.3 做 CSV -> MySQL 字段映射与联调准备
即使暂时不做大规模真实写入，也应先把下面这些事情准备好：
- 脚本输出字段与 schema 的映射
- 发布前/写入前预检
- 参数与运行口径固定

这样一旦抓取恢复，就能更快接回 MySQL 联调。

### 7.4 再推进后端 MySQL 化
等脚本侧数据与发布链路相对稳定后，再把 MySQL 接到后端主链路上，整体风险更低。

### 7.5 外围能力最后推进
登录、审核后台、部署运维这些工作很重要，但不应抢在数据链路和发布链路稳定之前展开。

## 8. 当前阶段的总判断
这一阶段最重要的价值，不是“所有问题都解决了”，而是：

- 把项目从“文档比较全、实现还很弱”推进到了“离线脚本链路基本成形”
- 把很多原本的黑盒问题推进成了可诊断、可落盘、可复现的问题
- 在 bootstrap 被上游风控阻塞时，没有让整体推进停住，而是转向补齐 generator / publish / fixture / smoke 的可控部分

换句话说，这一阶段已经把**后续真正进入稳定联调与 MySQL 落地前的工程地基**打了出来。

接下来最关键的不是重新发明规则，而是：
- 等抓取恢复后补真数据回归
- 继续扩大离线边界覆盖
- 把 CSV 与 MySQL 之间的工程链路接上

做到这一步，项目才算真正从“有规则、有脚本”进入“有可持续迭代能力”的状态。
