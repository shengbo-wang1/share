# 项目路线图（实施顺序版）

这份文档用于说明：**接下来要做什么、按什么顺序做、每个阶段交付什么、如何判断阶段完成**。

它是项目的**实施路线图**，不替代专题规则文档；规则、公式、ER 与发布约束仍以各专题文档为准。

## 1. 路线图目标
当前项目主线已经从“规则补充阶段”进入到“脚本实现与工程落地阶段”。

接下来要完成的不是继续扩规则，而是把以下链路真正跑通：
- 历史数据初始化
- candidate 自动生成
- reviewed CSV 审核与发布
- 后端 MySQL 持久化
- 后续登录、后台、部署能力

## 2. 当前状态摘要
### 已有
- Spring Boot 后端 MVP 已可运行
- 已有接口：
  - `POST /api/session/start`
  - `POST /api/session/submit`
  - `GET /api/session/result/{sessionId}`
  - `GET /api/leaderboard/daily`
- 已实现 20 日玩法主链路与结算规则
- 已有样例 challenge 数据与基础测试
- 已有数据初始化、特征公式、challenge generator、review/publish、MySQL 草案等专题文档
- 已有 `scripts/akshare_bootstrap.py` 最小可运行版（支持 CSV / 可选 MySQL）

### 仍缺
- 稳定批量运行的历史数据初始化脚本
- 稳定批量运行的 `scripts/challenge_generator.py`
- 稳定批量运行的 `scripts/review_publish.py`
- MySQL 持久化实现
- 正式用户体系、审核后台、部署运维链路

### 当前完成度评估（粗估）
为避免“文档和脚本已经做了很多”但对整体进度判断过高，当前统一补一版**基于路线图阶段目标的粗估完成度**。

#### 整体项目完成度
- **全项目总体进度：约 `35% ~ 45%`**

这个口径是按整个路线图计算的，因此会显著受以下未完成项拖累：
- bootstrap 真实抓取主链路尚未稳定恢复
- MySQL 仍未接成主路径
- 外围能力（登录、审核后台、部署）尚未进入实施

#### 当前脚本主线完成度
- **脚本主线（Phase 1 ~ 3）进度：约 `60% ~ 70%`**

这个口径更能反映当前阶段的真实产出，因为最近一轮工作已经把：
- bootstrap 请求级诊断
- generator 调试日志 / `--allow-empty`
- publish 失败码 / 空 CSV 容错
- fixed fixture / failure fixture / stability fixture
- `fixture_smoke.py` 一键离线回归

这些工程化基础打出来了。

#### 分阶段粗估
- **Phase 1：离线数据初始化**：约 `45% ~ 55%`
  - 已有最小可运行版、批次日志、质检、请求级诊断
  - 但真实抓取主链路仍受 Eastmoney 连接级风控阻塞，不能按“已打通”计算
- **Phase 2：题库候选生成**：约 `70% ~ 80%`
  - 已有 candidate/debug/run log、tag_rule 级诊断、failure fixtures、stability fixtures、smoke 回归
  - 但真实 batch 回归和更广的边界样本仍不足
- **Phase 3：审核与发布**：约 `65% ~ 75%`
  - 已有 reviewed CSV -> challenge/challenge_day 的最小闭环、失败码、失败样本、空 CSV 容错
  - 但 MySQL 真闭环与更完整的发布前校验仍未完成
- **Phase 4：后端 MySQL 化**：约 `5% ~ 15%`
  - 目前主要还是 schema / 文档准备，后端主链路尚未切换到 MySQL
- **Phase 5：外围能力**：约 `0% ~ 5%`
  - 目前仍未进入真正实施阶段

#### 当前判断
如果只看“最近做了很多脚本和夹具”，很容易把整体进度高估到 `60%+`。  
但按路线图的阶段目标衡量，当前更准确的说法是：
- **全项目约 40% 左右**
- **脚本主线约 65% 左右**

也就是说，当前最大的未完成项并不是 generator / publish 的离线能力，而是：
1. bootstrap 真实抓取恢复
2. MySQL 主链路落地
3. 真数据回归补齐

## 3. 实施优先级
统一按以下顺序推进，不交叉发散：
1. 数据初始化
2. challenge generator
3. review / publish
4. 后端 MySQL 化
5. 外围能力

---

## Phase 1：离线数据初始化
### 当前状态
- **进行中（被上游连接级风控阻塞）**

### 目标
在现有最小可运行版基础上，继续补强为稳定批处理脚本，能够生成后续 challenge 链路所需的基础数据。

### 输入
- 股票池
- 起止日期
- AKShare 原始行情 / 前复权行情 / 股本相关数据
- MySQL 连接参数或 CSV 输出参数

### 输出
- `stock_daily_raw`
- `stock_daily_feature`
- `staging_raw`
- `job_run_log`
- `data_quality_check`
- 最小可验证的落库或导出结果

### 交付物
- 补强 `scripts/akshare_bootstrap.py`
- 至少支持单只股票、单时间区间跑通
- 支持写 MySQL 或导出 CSV 的最小路径
- 有最小校验方式（如行数、字段完整性、日期对齐）

### 验收标准
- 能对单个 symbol 成功执行完整流程
- 能产出 `raw` 与 `feature` 两类结果
- 能记录最小批次日志与质检结果
- 不把 `float_mv_est` 当精确历史流通市值使用

### 依赖关系
- 依赖现有文档：`docs/akshare-data-init.md`、`docs/data-init-flow.md`、`docs/feature-formula-pseudocode.md`
- 是 Phase 2 与 Phase 3 的前置条件
- 当前实跑步骤与调试记录统一见 `docs/script-runbook.md`

---

## Phase 2：题库候选生成
### 当前状态
- **进行中（离线链路已较稳定，仍缺真实 batch 回归）**

### 目标
在现有最小可运行版基础上，继续补强离线 generator，稳定输出待审核 candidate 集合。

### 输入
- `stock_daily_raw` / `stock_daily_feature`
- 股票池与交易日窗口
- 标签与难度规则

### 输出
- `candidate.csv`
- 过程产物（如过滤结果、失败清单、批次标识）

### 交付物
- 补强 `scripts/challenge_generator.py`
- 生成符合文档字段要求的 `candidate.csv`
- 至少支持单批次本地运行

### 验收标准
- 输出字段与 `docs/challenge-generator-main-flow.md` 一致
- 候选题遵守固定 20 日窗口、标签与难度默认规则
- 不绕过人工审核，不直接写 `challenge / challenge_day`

### 依赖关系
- 依赖 Phase 1 数据输出
- 依赖文档：`docs/challenge-generation-rules.md`、`docs/feature-formula-pseudocode.md`、`docs/challenge-generator-main-flow.md`
- 当前实跑步骤与调试记录统一见 `docs/script-runbook.md`

---

## Phase 3：审核与发布
### 当前状态
- **进行中（最小闭环已可跑，仍缺 MySQL 真闭环与更多发布校验）**

### 目标
在现有最小可运行版基础上，继续补强 reviewed CSV 发布脚本，稳定完成 `candidate -> reviewed CSV -> challenge/challenge_day` 闭环。

### 输入
- reviewed CSV
- candidate 输出文件
- challenge_id/version 命名规则
- 发布前校验规则

### 输出
- 入库后的 `challenge`
- 入库后的 `challenge_day`
- 发布成功清单 / 失败清单

### 交付物
- 补强 `scripts/review_publish.py`
- 支持读取 reviewed CSV 并逐条发布
- 支持发布失败按记录落失败清单

### 验收标准
- 只允许已审核通过记录进入发布
- 发布后 `challenge / challenge_day` 冻结，不覆盖旧题
- 排行榜继续按 `challenge_id` 隔离
- challenge_id 可读、可追溯

### 依赖关系
- 依赖 Phase 2 的 candidate 输出
- 依赖文档：`docs/review-and-publish-toolchain.md`、`docs/challenge-generator-main-flow.md`
- 当前实跑步骤与调试记录统一见 `docs/script-runbook.md`

---

## Phase 4：后端 MySQL 化
### 当前状态
- **未开始（目前仍以 schema / 文档准备为主）**

### 目标
把当前内存仓储逐步替换为 MySQL 持久化实现，同时保持现有玩法 API 不变。

### 输入
- `docs/mysql-schema.sql`
- `docs/er-diagram.md`
- 已落库的 challenge 与 session 相关表结构

### 输出
- MySQL 驱动的 repository / persistence 层
- 与现有 API 兼容的后端实现

### 交付物
- 引入 MySQL/JPA 或等价持久化方案
- 优先接入：
  - `challenge`
  - `challenge_day`
  - `user_session`
  - `user_action`
  - `user_result`
- 保持现有控制器接口签名不变

### 验收标准
- 现有 4 个 API 仍可工作
- `mvn -s .mvn-settings.xml test` 继续通过
- 不再依赖内存样例仓储作为主实现

### 依赖关系
- 依赖 `docs/mysql-schema.sql` 与 `docs/er-diagram.md`
- 与 Phase 3 可局部交错，但默认在 Phase 3 之后推进

---

## Phase 5：外围能力
### 当前状态
- **未开始**

### 目标
补齐从 MVP 到可部署版本的外围系统能力。

### 范围
- 微信登录 / 用户体系
- 审核后台
- 首页投放与运营工具
- 云部署、Nginx、配置管理、运维化

### 交付物
- 登录接入方案
- 审核后台或替代管理界面
- 部署脚本 / 配置模板 / 环境说明

### 验收标准
- 运行环境区分本地 / 测试 / 云上部署
- 审核与发布不再完全依赖手工搬运
- 不破坏前面阶段的冻结与可追溯原则

### 依赖关系
- 默认在前四阶段稳定后推进

---

## 4. 阶段实施注意事项
### 固定实现原则
- 不继续发散规则，优先实现既有文档
- 不绕过 `reviewed CSV`
- 不覆盖已发布 `challenge / challenge_day`
- 不让前端依赖未来数据
- 不把 `float_mv_est` 当精确历史市值
- 不未经确认修改公共 API 签名

### 推荐执行方式
- 先做“最小可运行版本”，再补强批量化与稳定性
- 每个阶段都要求有最小校验方式
- 每完成一阶段，同步更新 `docs/stage-review.md`

## 5. 环境与部署约束
### MySQL 网络信息
- 当前开发阶段公网 IP：`43.143.210.196`
- 后续云上私网 IP：`10.2.0.14`

### 固定约束
- 当前开发可先按公网访问
- 云上部署后默认切到私网访问
- 连接地址不得写死在代码中
- 统一通过 env / profile / 启动参数注入数据库地址
- 账号、密码、库名等敏感信息不写入公开文档

## 6. 与其他文档的关系
- 看**当前现状与卡点**：`docs/stage-review.md`
- 看**总体规则与设计原则**：各专题文档
- 看**接下来按什么顺序实施**：本文档

如果当前状态发生明显变化，应先更新：
1. `docs/stage-review.md`
2. `docs/roadmap.md`
3. 必要时更新 `share/AGENTS.md`
