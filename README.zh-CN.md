# Macro Quant Agent

[English](./README.md) | [简体中文](./README.zh-CN.md)

一个基于 Python 构建的 LLM 驱动宏观/科技股资产配置研究系统，包含检索增强上下文、组合风控、回测、调度与心跳监控，以及用于审计和复盘的本地 Dashboard。

## 项目状态

- 当前定位为研究预览版，不是生产级交易系统
- 默认安全模式运行：`BROKER_TYPE=mock`
- 真实下单需要显式开启 `ENABLE_LIVE_TRADING=true`
- 重点放在工程可靠性、风控、审计可追踪与运行可观测性

## 这个项目在解决什么问题

很多 “LLM + 交易” Demo 只停留在“让模型输出一份 JSON 持仓权重”。这个项目更关注后面的工程问题：

- LLM 生成的计划，在执行前应该如何校验？
- 一个交易研究系统如何做到可审计、可复盘？
- 即使只是研究型系统，也应该具备哪些风控？
- 如何把策略、执行、调度、运行状态解耦开来？

围绕这些问题，这个仓库实现了：

- 基于 LLM 的日度组合规划
- 从新闻、宏观、基本面、行情组装 RAG 风格上下文
- 执行前的硬性风控与组合约束
- Mock / IBKR 双券商适配
- 向量化回测与可信度摘要
- 心跳、熔断、告警、Dashboard 等运维视角能力

## 主要能力

### 1. 日度 LLM 组合规划

系统会拉取宏观、新闻、基本面、市场数据，然后让 LLM 在固定科技股股票池上生成目标权重。

### 2. 执行前风控

LLM 输出不会直接变成订单，而是先经过校验与清洗，包括：

- 单票持仓上限
- 最低现金缓冲
- 死区过滤
- 最大持仓数
- Top3 集中度上限
- 主题/风险分组暴露上限
- 最大单日换手率缩放

### 3. 安全执行模式

- `MockBroker` 用于本地仿真和状态持久化
- `IBKRBroker` 用于连接 TWS / Gateway
- 未显式开启实盘时，系统只会生成 `planning_only` 结果，不会真实下单

### 4. 回测与研究报告

回测模块支持在历史窗口上回放 LLM 计划，并输出：

- 净值 / 基准对比图
- 夏普率、最大回撤等指标
- 关于快照覆盖率与 synthetic prices 的可信度摘要

### 5. 运行态可观测性

仓库自带一个轻量级本地运维台：

- Dashboard 展示策略、执行、告警、日志和资金曲线
- 心跳文件记录最近运行状态
- 调度器状态
- 结构化 kill switch 状态
- 事件与告警日志，便于排障

## 架构

```text
isolation/
├── config.py
├── core/
│   └── agent.py               # 检索、LLM、风控、执行的总调度
├── data/
│   ├── retriever.py           # 新闻 / 宏观 / 行情 / 基本面检索
│   ├── earnings_agent.py      # 财报与指引摘要辅助模块
│   ├── snapshot_db.py         # 点时快照持久化
│   └── cache.py               # 本地缓存与状态
├── llm/
│   ├── volcengine.py          # 模型调用、审计留痕、修复重问
│   └── validator.py           # 输出校验与组合约束清洗
├── execution/
│   ├── portfolio.py           # 目标权重 -> 订单，附带风控
│   ├── broker.py              # MockBroker / IBKRBroker
│   ├── ledger.py              # 执行账本
│   └── reconcile.py           # 成交与账户对账
├── backtest/
│   └── engine.py              # 向量化回测引擎
├── dashboard/
│   ├── server.py              # 本地 HTTP API
│   └── static/                # Dashboard 前端
├── utils/
│   ├── heartbeat.py
│   ├── kill_switch.py
│   ├── alerting.py
│   ├── metrics.py
│   └── review.py
├── run_agent.py               # 日常运行入口
├── run_llm_backtest.py        # 回测入口
└── run_scheduler.py           # 轻量调度入口
```

## 技术栈

- Python 3.9+
- `pandas`, `numpy`, `matplotlib`
- 通过 `openai` SDK 接入 BytePlus / Volcengine 模型
- `yfinance`, `Alpha Vantage`
- `ib_insync` 用于 IBKR 集成
- 使用本地 JSON / JSONL 保存快照、指标、事件、告警和运行状态

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 创建 `.env`

```env
ALPHA_VANTAGE_KEY=your_alpha_vantage_key_here

VOLCENGINE_API_KEY=your_volcengine_api_key_here
VOLCENGINE_MODEL_ENDPOINT=ep-xxxxxxxx-xxx

IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1
IBKR_DATA_CLIENT_ID=11

BROKER_TYPE=mock
ENABLE_LIVE_TRADING=false
```

### 3. 运行测试

```bash
python3 -m pytest -q
```

### 4. 运行 daily agent

```bash
python3 run_agent.py
```

### 5. 运行回测

```bash
python3 run_llm_backtest.py
```

### 6. 启动 Dashboard

```bash
python3 dashboard/server.py
```

默认地址：

```text
http://127.0.0.1:8010/
```

### 7. 启动调度器

```env
AGENT_SCHEDULER_ENABLED=true
AGENT_SCHEDULE_TIME=16:10
AGENT_SCHEDULE_TIMEZONE=America/New_York
AGENT_SCHEDULE_POLL_SECONDS=30
```

```bash
python3 run_scheduler.py
```

## 安全模型

这个仓库有意采用保守策略：

- 默认 broker 模式是 `mock`
- 真实 IBKR 提交需要显式开启 `ENABLE_LIVE_TRADING=true`
- LLM 输出在执行前会先被校验和清洗
- 输出非法时优先降级 / 跳过交易，而不是盲目提交
- 严重异常时 kill switch 可以锁住系统
- 即使不允许执行，系统也可以继续生成计划用于审计与复盘

## 当前局限

这个项目已经不只是一个玩具，但它也还不是生产级交易平台。

- 某些数据源容易受限流影响，尤其是 `yfinance`
- 回测可信度依赖点时快照覆盖率
- synthetic prices 适合演示，不适合作为策略有效性的强证据
- 当前持久化主要是文件，而不是数据库
- Dashboard 偏本地排查和展示，不适合多用户部署

## 仓库亮点

- 检索、LLM 规划、执行、对账、运行态运维职责清晰分层
- 对 prompt 版本、原始模型输出、校验警告、修复重问做显式审计留痕
- 具备心跳、熔断状态、运行事件等可观测性能力
- Dashboard 支持 token 保护
- 回归测试覆盖组合规则、Dashboard 鉴权、运行守卫、复盘逻辑、调度逻辑与审计元数据

## 主要入口

- `python3 run_agent.py`
- `python3 run_llm_backtest.py`
- `python3 run_scheduler.py`
- `python3 dashboard/server.py`

`legacy/` 目录仅保留早期实验，不属于当前主链路。

## 路线图

目前最值得继续改造的方向：

- 提升数据源稳定性与降级策略
- 加强回测可信度与成本模型
- 增加 CI、lint 和 type-check
- 从文件状态迁移到 SQLite / Postgres
- 引入真正的向量库 RAG
- 增加多日 Dashboard 回放与执行质量分析

更细的任务拆分见 `TASKS.md`。

## 免责声明

本项目仅用于工程探索、研究和技术展示，不构成任何金融建议。任何由 LLM 生成的组合配置都应视为实验输出，而不是投资建议。

## License

MIT。详见 `LICENSE`。
