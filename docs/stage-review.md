# 阶段性回顾（当前状态页）

这份文档用于回答三件事：
- 当前我们在做什么
- 已经完成了什么
- 现在还缺什么、为什么下一步要做那些事

它是**当前局势页**，不替代专题规则文档；完整实施顺序见 `docs/roadmap.md`。

## 1. 当前阶段结论
当前项目已经从“规则补充阶段”进入到**脚本实现与工程落地阶段**。

当前主线不是继续扩规则，而是把以下链路真正做出来：
- 离线数据初始化
- candidate 自动生成
- reviewed CSV 审核与发布
- 后端 MySQL 持久化

### 1.1 最近阶段回顾摘要
最近这一阶段，项目的重心已经从“继续补规则文档”切到“把离线脚本链路做实、做稳、做得可诊断”。

本阶段最重要的推进有三类：
- **bootstrap 诊断补强**：把抓取失败从黑盒报错推进到请求级诊断，能够区分“响应前断连”与“返回异常页”
- **generator / publish 离线稳态补强**：补足输入校验、失败码、空结果体验、调试日志与空文件容错
- **固定 fixture + smoke 回归体系**：把后链路从“依赖实时抓取联调”推进到“本地固定 CSV 可重复回归”

当前最可靠的成果不是“实时抓取已经恢复”，而是：
- `challenge_generator.py`、`review_publish.py` 的离线调试与回归路径已经明显稳定
- 仓库内已经具备 fixed success / publish failure / generator failure / generator stability 四组固定夹具
- 本地可通过 `fixture_smoke.py` 一键跑完整离线回归

当前最主要阻塞仍然是：
- Eastmoney `push2his` 个股/指数 K 线接口仍存在**响应前断连**，bootstrap 真实抓取短期内仍受连接级风控影响

因此当前工作重心从“继续消耗时间在实时抓取上”转到“先把离线链路、失败诊断、固定回归和 MySQL 准备项补齐”。

如需看这一阶段更完整的复盘、踩坑、经验和后续接力重点，统一见：
- `docs/stage-retrospective.md`

## 2. 当前已完成工作
### 2.1 后端 MVP 已完成项
当前仓库已经有一套可运行的后端 MVP，核心能力包括：
- Spring Boot 项目骨架
- 接口：
  - `POST /api/session/start`
  - `POST /api/session/submit`
  - `GET /api/session/result/{sessionId}`
  - `GET /api/leaderboard/daily`
- 20 日一局的对局流程
- 0 / 50 / 100 仓位切换
- 次日开盘成交
- 固定交易成本（0.15%）
- 最终收益优先、最大回撤辅助
- 样例 challenge 数据与基础测试

### 2.2 数据与题库专题文档已完成项
当前已经落地的专题文档包括：
- `docs/akshare-data-init.md`
- `docs/er-diagram.md`
- `docs/mysql-schema.sql`
- `docs/data-init-flow.md`
- `docs/challenge-generation-rules.md`
- `docs/feature-formula-pseudocode.md`
- `docs/challenge-generator-main-flow.md`
- `docs/review-and-publish-toolchain.md`

这些文档已经覆盖：
- 数据初始化总体流程
- 数据库 ER 图与表结构草案
- staging / job log / quality check 闭环设计
- challenge 生成流程
- challenge generator 主流程
- challenge 标签 / 难度 / 人工筛题规则

### 2.3 当前已经具备的能力边界
当前项目已经具备：
- 一个能跑通玩法主链路的后端样例系统
- 一套可复用的数据初始化与题库设计框架
- 一套可执行的 v1 题库规则说明

当前项目还不具备：
- MySQL 持久化实现
- 稳定批量运行的 AKShare 初始化任务
- 稳定批量运行的 challenge 自动生成器实现
- 稳定批量运行的审核与发布脚本实现
- 微信登录 / 正式用户体系
- 审核后台与部署工具链

## 3. 当前已确认且应继续坚持的设计
以下设计已经较稳定，后续实现默认沿用：
- 产品定位：历史 K 线训练，不是荐股
- 一局固定 20 个交易日
- 仓位固定为 `0 / 50 / 100`
- 次日开盘成交
- 前复权展示、原始价结算
- 后端统一结算
- `challenge + challenge_day` 分离并在发布后冻结
- 数据初始化分层：抓取 / 标准化 / 特征 / 题库 / 质检
- `staging_raw / job_run_log / data_quality_check` 保留
- 自动候选 + 人工精选
- 固定标签规则、三档难度、人工最多微调一项
- generator 为离线批处理，不做在线发题
- reviewed CSV + 离线发布脚本作为第一版审核发布载体
- 排行榜默认按 `challenge_id` 隔离
- 第 5 类标签依赖沪深核心 3 指数，缺失即停用

## 4. 当前主要不足与风险
### 4.1 实现层仍明显落后于规则层
当前规则文档已经较完整，但脚本和工程实现还没有真正跟上。

直接表现为：
- `scripts/akshare_bootstrap.py` 已有最小可运行版，但仍需补强批量化、稳定性与 MySQL 全链路细节
- `scripts/challenge_generator.py` 已有最小可运行版，但仍需补强规则覆盖、批量化与质检产物
- `scripts/review_publish.py` 已有最小可运行版，但仍需补强审核模板流转、批量化与 MySQL 发布校验
- MySQL 仍未接入后端主链路

### 4.2 AKShare 仍是单点风险
当前仍默认以 AKShare 为主要数据入口，存在：
- 上游字段变化风险
- 网络波动导致批次半成功风险
- 数据口径稳定性不足风险

结论：
- 第一版可继续使用
- 但实现上必须保留批次日志、质检与失败恢复能力

### 4.3 `float_mv_est` 只是估算值
当前设计里使用 `raw_close * outstanding_share` 近似历史流通市值。

结论：
- 可以用于第一版标签与筛题辅助
- 不能在产品和分析里被当作精确历史市值解释

### 4.4 job / batch 关系仍是概念模型
当前文档里的 batch 关系适合作为实现指导，但不应在真正落 MySQL 或调度系统时机械照搬为僵硬外键结构。

### 4.5 审核后台仍未落地
当前第一版已经明确采用 CSV + 离线脚本承接审核与发布，因此短期问题不在规则，而在工具链实现。

## 5. 联调状态
### 5.1 当前联调结论
- `scripts/akshare_bootstrap.py`、`scripts/challenge_generator.py`、`scripts/review_publish.py` 已具备最小可运行版
- 当前已经进入真实数据联调阶段
- bootstrap 首轮真实联调已开始，但被 AKShare 远端断连阻塞
- 联调执行口径统一为：从仓库根目录执行，输出统一落到根目录 `output/`
- 三段脚本的实跑顺序、输出目录约定、reviewed CSV 最小调试方法、常见问题排查统一见 `docs/script-runbook.md`

### 5.2 当前联调关注点
- 先按 CSV 路径联调，再测可选 MySQL 写入
- 重点关注 AKShare 字段兼容、最新批次目录识别、reviewed CSV 模板完整性、challenge_id 冲突
- bootstrap 当前已切到 `stock_zh_a_hist` 主链路，`stock_zh_a_daily` 不再作为必需依赖
- `python-share-env` 中可复用的 `stock_zh_a_spot_em()` 已作为股票池 / 名称 fallback 引入 bootstrap
- AKShare `RemoteDisconnected` 仍是当前 bootstrap 真实联调的主要阻塞点，但 bootstrap 已补到请求级诊断能力，可结合 `fetch_attempt_log.csv` / `fetch_debug_log.jsonl` / `symbol_run_log.csv` 区分“响应前断连”与“已返回异常页”
- bootstrap 现已补充请求级 method / URL / timeout / response status / body preview 诊断日志，不再只依赖终端输出猜原因
- 最新调试结果表明：股票列表与交易日历接口可访问，但 Eastmoney `push2his` 个股/指数 K 线接口在响应前断连，短期内应视为连接级风控阻塞
- 在抓取恢复前，当前工作重点应临时切换到 generator / publish 的离线稳定性补强，以及 MySQL 字段映射准备
- generator 必须输出逐阶段诊断日志，避免 `0 candidate` 时只能看到黑盒报错
- generator 现已补充 `tag_rule` 级别诊断，可按标签查看 matched / missed / exclusion reason，而不再只有 `no_tag_hit`
- generator 现已支持 `--allow-empty`，可把预期 `EMPTY` 场景从“脚本坏了”区分为“可接受的调试结果”
- 单股、单月样本不足以验证 generator 规则正确性；当可用交易日少于 `20 + 3` 时，无 candidate 属于预期结果
- publish 已补空 `challenge_*.csv` 容错，连续跑正向 / 失败样本时不会再因空历史文件崩溃
- 当前已形成基于 manifest 的固定夹具体系：
  - `fixed_e2e_fixture`
  - `publish_failure_fixture`
  - `generator_failure_fixture`
  - `generator_stability_fixture`
- 当前已形成 `fixture_smoke.py` 一键回归入口，可串行验证 fixed success / publish failure / generator failure / generator stability
- 最近一次本地离线回归结果：
  - Python 单测：`18` 项通过
  - fixture smoke：`pass=12 fail=0`
- 最新调试结论与临时绕过方式，统一记录到 `docs/script-runbook.md`

## 6. 当前最需要推进的内容
下一步更适合进入工具脚本与工程实现，而不是继续补原则文档。

当前推荐优先顺序：
1. 等抓取窗口恢复后，回到 bootstrap 做单股短区间复测，确认 Eastmoney K 线链路是否解锁
2. 继续补 generator / publish 的离线边界样本与 anti-drift 回归
3. 做 CSV -> MySQL 字段映射与联调准备，减少抓取恢复后的切换成本
4. 再推进后端 MySQL 化
5. 最后再进入登录、后台、部署等外围能力

## 7. 环境补充说明
### MySQL 网络信息
- 当前开发阶段公网 IP：`43.143.210.196`
- 后续云上私网 IP：`10.2.0.14`

### 使用原则
- 当前可先按公网访问
- 云上部署后默认切私网
- 数据库地址不得写死在代码中
- 统一通过 env / profile / 启动参数注入
- 敏感信息不写入公开文档

## 8. 当前建议结论
当前项目结构已经比较清晰：
- 后端 MVP 用来验证玩法主链路
- 专题文档用来固定数据与题库规则
- 这一阶段已经把脚本联调、离线诊断、固定夹具和 smoke 回归基础打出来
- 接下来应在抓取恢复后尽快回到 bootstrap 真数据复测，并把 MySQL 工程链路补齐

**详细实施路线、阶段拆分、交付物与验收标准，统一见 `docs/roadmap.md`。**

**三段脚本的真实联调步骤、输出目录约定与调试记录，统一见 `docs/script-runbook.md`。**

**本阶段更完整的回顾、经验、踩坑与后续接力重点，统一见 `docs/stage-retrospective.md`。**
