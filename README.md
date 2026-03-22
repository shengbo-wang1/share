# share

历史 K 线交易训练小程序后端 MVP。

## 当前阶段
- 当前已进入：**脚本实现与工程落地阶段**
- 当前现状回顾：见 `docs/stage-review.md`
- 当前实施路线：见 `docs/roadmap.md`
- 脚本实跑与联调手册：见 `docs/script-runbook.md`

## 已实现
- `POST /api/session/start`：发一局 20 日 challenge
- `POST /api/session/submit`：提交 0/50/100 仓位轨迹并由服务端结算
- `GET /api/session/result/{sessionId}`：查看结算结果和海报文案
- `GET /api/leaderboard/daily`：查看日榜
- 内置样例 challenge 数据，便于前后端联调

## 规则摘要
- 用户看到的是前复权 K 线与指标；服务端用原始价格按**次日开盘价成交**结算。
- 支持仓位 `0 / 50 / 100`。
- 每次仓位调整按成交金额收取固定成本，默认 `0.15%`。
- 主分数 = 最终收益率；同分时最大回撤更低者优先。
- 每局显示 20 个交易日，其中前 19 天可发出指令，第 20 天用于最终估值。

## 脚本实跑与联调
- 所有脚本命令默认从**仓库根目录**执行：`/Users/wangshengbo/Desktop/java-share-app`
- 三段脚本联调顺序、输出目录和调试记录统一见 `docs/script-runbook.md`
- 若 bootstrap 遇到远端断连 / AKShare 限流，先看 `docs/script-runbook.md` 的 AKShare 排查节

## 启动
```bash
mvn spring-boot:run
```

默认端口：`8080`

## 示例请求
### 1. 开局
```bash
curl -X POST http://localhost:8080/api/session/start \
  -H 'Content-Type: application/json' \
  -d '{"userId":"demo-user"}'
```

### 2. 提交
将第一步返回的 `sessionId`、`signature`、前两天 `tradeDate` 带入：
```bash
curl -X POST http://localhost:8080/api/session/submit \
  -H 'Content-Type: application/json' \
  -d '{
    "sessionId":"<sessionId>",
    "userId":"demo-user",
    "signature":"<signature>",
    "actions":[
      {"tradeDate":"2018-06-01","targetPosition":50},
      {"tradeDate":"2018-06-02","targetPosition":100}
    ]
  }'
```

## 数据初始化与落库
- MySQL 表设计：见 `docs/mysql-schema.sql`
- 数据库 ER 图：见 `docs/er-diagram.md`
- AKShare 初始化脚本（最小可运行版，支持 CSV / 可选 MySQL）：见 `scripts/akshare_bootstrap.py`
- 初始化说明：见 `docs/akshare-data-init.md`
- 数据初始化流程图与评审：见 `docs/data-init-flow.md`
- Challenge 生成规则：见 `docs/challenge-generation-rules.md`
- 特征公式与伪代码：见 `docs/feature-formula-pseudocode.md`
- Challenge generator 主流程：见 `docs/challenge-generator-main-flow.md`
- Challenge generator 脚本（最小可运行版，输出 candidate.csv）：见 `scripts/challenge_generator.py`
- 审核与发布工具链：见 `docs/review-and-publish-toolchain.md`
- 审核与发布脚本（最小可运行版，输出 challenge / challenge_day / publish result CSV）：见 `scripts/review_publish.py`
- 脚本实跑与联调手册：见 `docs/script-runbook.md`
- 阶段性回顾（当前状态页）：见 `docs/stage-review.md`
- 项目路线图（实施顺序版）：见 `docs/roadmap.md`
- 当前初始化链路已补充到文档层：`staging_raw / job_run_log / data_quality_check`
- 题库生成规则采用：`阈值规则 + 人工微调` 的 v1 策略
- 题库发布流程采用：`自动候选 + 人工精选 + 冻结发布`
- 第 5 类标签采用：`沪深核心 3 指数 + 固定阈值 + 缺失即停用`

## 环境与部署说明
- 当前开发阶段 MySQL 可按公网访问：`43.143.210.196`
- 后续云上部署后切私网：`10.2.0.14`
- 数据库地址不要写死在代码中，统一通过 env / profile / 启动参数注入

## 当前限制
- 目前为了快速联调，仓储层为内存实现；已经把领域对象与表结构拆开，后续可切到 MySQL/JPA。
- 内置 challenge 是合成样例数据，不是线上真实行情。
- 未接微信登录，当前以 `userId` 字符串代表用户身份。
