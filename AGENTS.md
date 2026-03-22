# AGENTS.md

## 项目概述
- 项目名称：历史 K 线交易训练小程序后端 MVP
- 一句话描述：A 股历史日 K 交易训练游戏后端与离线题库链路
- 当前阶段：脚本实现与工程落地阶段
- 当前主要任务：优先参考 `docs/stage-review.md` 与 `docs/roadmap.md`

## 关键文档
- `docs/stage-review.md` — 当前阶段回顾、当前不足与风险
- `docs/stage-retrospective.md` — 本阶段完整复盘、经验沉淀与后续接力重点
- `docs/roadmap.md` — 路线图、实施顺序与阶段验收
- `docs/script-runbook.md` — 三段脚本实跑、联调顺序与调试记录
- `docs/data-init-flow.md` — 数据初始化总流程
- `docs/er-diagram.md` — 数据模型与 ER 图
- `docs/mysql-schema.sql` — MySQL 草案
- `docs/challenge-generation-rules.md` — 标签/难度规则
- `docs/feature-formula-pseudocode.md` — 特征公式与伪代码
- `docs/challenge-generator-main-flow.md` — candidate 生成主流程
- `docs/review-and-publish-toolchain.md` — 审核与发布链路
- `docs/akshare-data-init.md` — AKShare 初始化说明
- `README.md` — 项目入口与运行说明

## 技术栈
- Java 8
- Spring Boot 2.7.x
- Maven
- 当前仓储层：内存实现
- 目标部署环境：MySQL + Nginx + 腾讯云

## 任务开始前必读
1. 先读 `share/AGENTS.md`
2. 再读 `docs/stage-review.md`（看当前现状）
3. 再读 `docs/roadmap.md`（看接下来做什么）
4. 若任务是脚本联调/调试，再读 `docs/script-runbook.md`
5. 按任务类型补读专题文档：
   - 数据初始化：`docs/data-init-flow.md` / `docs/akshare-data-init.md`
   - 题库规则：`docs/challenge-generation-rules.md` / `docs/feature-formula-pseudocode.md`
   - candidate 生成：`docs/challenge-generator-main-flow.md`
   - 发布链路：`docs/review-and-publish-toolchain.md`
6. 若任务涉及改规则，先确认是否与“已知决策”冲突
7. 若任务只是实现脚本，默认不重新发明规则

## 当前主要实现优先级
1. 补强 `scripts/akshare_bootstrap.py`
2. 补强 `scripts/challenge_generator.py`
3. 补强 `scripts/review_publish.py`
4. MySQL 持久化

## 完成标准
### 文档任务
- [ ] 相关索引已同步
- [ ] 与既有文档口径一致
- [ ] 没有引入新的未声明决策

### 代码 / 脚本任务
- [ ] 有最小测试或最小校验方式
- [ ] 相关文档已同步
- [ ] 不绕过 `freeze` / `reviewed CSV` / `challenge_id` 规则
- [ ] 如涉及 Java 代码，优先使用 `mvn -s .mvn-settings.xml test`

## 已知决策
- 历史训练，不是荐股
- 一局固定 20 个交易日
- 仓位固定为 `0 / 50 / 100`
- 次日开盘成交
- 前复权展示、原始价结算
- `challenge / challenge_day` 发布后冻结
- 题库链路为：`candidate -> reviewed CSV -> 发布脚本 -> challenge/challenge_day`
- 第 5 类标签依赖沪深核心 3 指数，缺失即停用
- `challenge_id` 采用可读命名规则
- 排行榜默认按 `challenge_id` 隔离
- 第一版审核与发布承载方式为：离线 CSV + 离线脚本

## 禁止事项
- 不要绕过人工审核直接发布 challenge
- 不要覆盖已发布 `challenge / challenge_day`
- 不要把 `float_mv_est` 当成精确历史流通市值
- 不要让前端依赖未来数据或标签验证特征
- 不要在未同步文档前改规则口径
- 不要未经确认修改公共 API 签名
- 不要在代码中写死 MySQL IP，统一使用 env / profile / 参数注入

## AGENTS 使用工作流
### 新任务进入时
1. 先读仓库根 `AGENTS.md`
2. 再读 `share/AGENTS.md`
3. 看 `docs/stage-review.md` 了解当前局势
4. 看 `docs/roadmap.md` 了解下一步实施顺序
5. 若任务是脚本联调/调试，补读 `docs/script-runbook.md`
6. 根据任务类型读取相关专题文档
7. 再开始写计划、文档、代码或脚本

### AGENTS 的职责
- AGENTS 是导航页
- docs 是事实页
- `docs/stage-review.md` 是当前局势页
- `docs/stage-retrospective.md` 是阶段复盘与经验沉淀页
- `docs/roadmap.md` 是实施路线页
- `docs/script-runbook.md` 是脚本实跑与联调页

### 什么时候更新 AGENTS
仅在以下情况更新：
- 当前阶段变化
- 关键文档新增或重命名
- 已知决策新增
- 禁止事项新增
- 工作流入口改变

普通细节规则变化，优先更新专题文档，不要把 AGENTS 写得过重。

## 新工作窗口切换规则
### 当前不建议立刻切新窗口
原因：
- 规则文档已较完整
- 但工程入口仍缺关键脚本实现
- 现在切新窗口，仍可能需要重新解释下一步先落哪个脚本

### 可以打开新的工作窗口的触发条件
满足以下条件后，再切新窗口：
1. 根 `AGENTS.md` 已写好
2. `share/AGENTS.md` 已写好
3. 至少落完一个脚本骨架入口：
   - 推荐优先：`scripts/challenge_generator.py`
   - 或：`scripts/review_publish.py`
4. `docs/stage-review.md` 已明确进入“脚本实现与工程落地阶段”
5. `docs/roadmap.md` 已明确实施优先级与阶段目标

### 为什么要等脚本骨架
- 看 AGENTS 能知道项目背景
- 看 docs 能知道规则
- 看路线图能知道实施顺序
- 看脚本骨架能知道下一步从哪开始实现

只有到这一步，新的工作窗口才真正容易低成本恢复上下文。
