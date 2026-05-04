# 🤖 Macro Quant Agent (基于大语言模型的宏观量化交易引擎)

> 🎓 **A Quantitative Trading Project by a CS Student**  
> 这是一个结合了**事件驱动架构**、**大语言模型 (LLM)**、**RAG 检索增强**和**向量化回测**的现代量化交易系统。旨在探索 AI 在资产配置和量化风控中的应用边界。

---

## 📖 项目简介 (Overview)

本项目从一个简单的 Python 均线策略骨架起步，逐步重构演进为一个**高度解耦、支持实盘仿真、具备严格风控**的 AI 驱动量化交易框架。系统不再依赖传统的硬编码规则，而是通过 RAG 机制将实时的新闻情绪、宏观经济指标、基本面数据注入到 LLM (如字节跳动 Doubao-pro) 中，让 AI 充当“基金经理”生成每日的目标仓位权重。

核心特性：
- **🧠 LLM 驱动决策**：模型根据 RAG 获取的多维度数据（宏观/微观/情绪/量价）动态生成投资组合权重。
- **🛡️ 硬核风控系统 (Risk Management)**：实现了资金安全垫 (Cash Buffer)、最大单日换手率限制 (Turnover Limit)、死区微调阈值 (Deadband) 等交易前拦截机制。
- **⚡ 向量化回测引擎 (Vectorized Backtesting)**：使用 Pandas / Numpy 构建的高性能独立回测模块，能够一键生成包含夏普比率、最大回撤、资金曲线的专业回测报告。
- **🔌 统一实盘券商接口 (Unified Broker API)**：通过一键修改配置，支持在本地回测环境 (MockBroker) 和盈透证券真实/仿真环境 (IBKRBroker) 之间无缝切换。

---

## 🏗️ 架构设计 (Architecture)

项目采用了标准的 MVC/微服务解耦架构，主要分为以下几个模块：

```text
isolation/
├── config.py                  # 全局配置中心 (风控参数、股票池、API Key)
├── .env                       # 本地环境变量 (机密数据，不提交至 Git)
├── core/
│   └── agent.py               # 🧠 核心大脑：MacroQuantAgent (协调数据、LLM 与交易执行)
├── data/
│   ├── retriever.py           # 📡 数据检索层：RAGRetriever (负责拉取新闻、宏观、行情并组装 Prompt)
│   ├── earnings_agent.py      # 🧾 财报研究代理：多步检索/总结 earnings & guidance（Agentic Search 风格）
│   └── cache.py               # 💾 持久化层：CacheDB (本地 JSON 账本，记录历史状态)
├── llm/
│   └── volcengine.py          # 🤖 模型层：封装火山引擎 API，处理 JSON Schema 强制校验
├── execution/
│   ├── portfolio.py           # 💼 资管中心：处理权重归一化、风控拦截、计算目标订单
│   └── broker.py              # 🏦 券商接口：包含 MockBroker 与 IBKRBroker (支持实盘/仿真)
├── backtest/
│   └── engine.py              # 📈 回测引擎：VectorizedBacktester (计算绩效指标与可视化)
├── legacy/
│   ├── main.py                # 🗃️ 早期教学/原型脚本（已归档，不属于主系统入口）
│   ├── ib_trade.py            # 🗃️ 早期事件驱动 IBKR 实验脚本
│   ├── ib_test.py             # 🗃️ 早期 IBKR 连通性测试脚本
│   └── refactor.py            # 🗃️ 历史辅助重构脚本
├── run_agent.py               # 🚀 入口：运行单日实盘/仿真交易循环
└── run_llm_backtest.py        # 🚀 入口：执行 LLM 历史区间量化回测
```

---

## 🛠️ 技术栈 (Tech Stack)

*   **核心语言**: Python 3.9+
*   **数据处理与回测**: `pandas`, `numpy`
*   **数据源 API**: `yfinance` (行情与基本面), `Alpha Vantage` (金融新闻)
*   **券商行情数据**: IBKR TWS/Gateway (支持延迟行情快照，作为 yfinance 的更稳定替代)
*   **宏观指标**: 优先使用 IBKR 延迟快照（VIX/TNX），失败时回退到中性假设或其他数据源
*   **大语言模型**: `openai` SDK (接入火山引擎 BytePlus)
*   **可视化**: `matplotlib`
*   **实盘接口**: `ib_insync` (Interactive Brokers TWS API)

---

## 🚀 快速开始 (Getting Started)

### 1. 环境安装
克隆项目后，安装必要的依赖：
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量
在项目根目录创建一个 `.env` 文件，并填入你的 API Keys：
```env
# Alpha Vantage (用于获取新闻)
ALPHA_VANTAGE_KEY=your_alpha_vantage_key_here

# 火山引擎 / BytePlus (用于调用大模型)
VOLCENGINE_API_KEY=your_volcengine_api_key_here
VOLCENGINE_MODEL_ENDPOINT=ep-xxxxxxxx-xxx # 你的模型推理接入点

# IBKR 行情/交易（模拟盘常用 7497）
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1
IBKR_DATA_CLIENT_ID=11

# 默认安全模式：先用 mock，本地确认无误后再显式开启真实提交
BROKER_TYPE=mock
ENABLE_LIVE_TRADING=false
```

### 3. 运行历史回测 (Backtest)
想看看 LLM 的策略在过去几天的表现？运行向量化回测引擎：
```bash
python3 run_llm_backtest.py
```
> 执行完毕后，根目录会生成一张 `llm_backtest_report.png`，展示累计收益、最大回撤等核心指标。

### 4. 运行单日仿真交易 (Daily Agent)
如果你想在每天收盘后运行一次 AI 决策，生成最新的持仓指令并持久化到本地：
```bash
python3 run_agent.py
```

### 正式入口
- 正式运行入口只保留两个：
  - `python3 run_agent.py`
  - `python3 run_llm_backtest.py`
- `legacy/` 目录中的脚本仅用于保留项目早期演进历史与实验样例，不属于当前主系统链路。

如需启用轻量无人值守调度器，可额外配置：

```env
AGENT_SCHEDULER_ENABLED=true
AGENT_SCHEDULE_TIME=16:10
AGENT_SCHEDULE_TIMEZONE=America/New_York
AGENT_SCHEDULE_POLL_SECONDS=30
```

然后运行：

```bash
python3 run_scheduler.py
```

运行心跳会写入 `runtime/heartbeat.json`，Dashboard 会展示最近一次运行状态、最近成功运行、调度器下一次触发时间，以及当前是否处于 kill switch 锁定状态。

当系统触发熔断时，还会额外写入 `runtime/kill_switch.json`，其中包含：
- 触发原因 `reason`
- 触发来源 `source`
- 触发时间 `triggered_at`
- 恢复提示 `recovery_hint`
- 最近触发/解除历史 `history`

Dashboard Runtime 面板会直接展示这些信息，便于你快速判断是 agent 异常、告警策略触发，还是遗留锁文件导致的阻塞。

如需连接 IBKR 做真实提交，除了设置 `BROKER_TYPE=ibkr` 外，还需要显式开启：

```env
ENABLE_LIVE_TRADING=true
```

如需给本地 Dashboard 加一个最小访问保护，可以再配置：

```env
DASHBOARD_TOKEN=replace-with-a-long-random-string
```

然后用带 token 的地址打开页面，例如：

```text
http://127.0.0.1:8010/?token=replace-with-a-long-random-string
```

---

## 🛡️ 风控规则说明 (Risk Control)

在 `config.py` 中，你可以自由调节以下风控参数：
- `MIN_CASH_RATIO = 0.05`：**现金缓冲**。系统会强制拦截 LLM 的满仓指令，永远保留至少 5% 的现金，防止由于滑点或价格波动导致账户透支。
- `MAX_DAILY_TURNOVER = 0.30`：**换手率限制**。防止 LLM 频繁“高买低卖”导致摩擦成本过高，单日最大允许调仓总资产的 30%。超出部分将被按比例等比缩小。
- `MAX_SINGLE_POSITION = 0.30`：**单票持仓上限**。防止 LLM 发生幻觉导致 100% 仓位梭哈单只股票，系统强制截断任何超过 30% 占比的指令。
- `DEADBAND_THRESHOLD = 0.05`：**死区过滤**。如果目标权重与当前权重的差异小于 5%，系统将忽略该指令，避免微小波动带来的无谓手续费损耗。
- **全局系统熔断 (Kill Switch)**：在 API 连续异常或执行出现致命错误时，自动生成 `kill_switch.lock` 文件锁死系统，要求人工介入排查。

---

## 🔌 实盘与仿真切换 (Broker Configuration)

系统通过 `BROKER_TYPE` 环境变量控制运行模式。修改 `.env` 或 `config.py` 即可无缝切换：

```env
# 可选值: 'mock' (本地回测) 或 'ibkr' (盈透实盘/仿真)
BROKER_TYPE=mock
ENABLE_LIVE_TRADING=false

# 如果选择 ibkr，需配置以下连接参数:
IBKR_HOST=127.0.0.1
# 7497 为 TWS 模拟盘，7496 为 TWS 实盘，4002 为 IB Gateway 模拟盘
IBKR_PORT=7497 
IBKR_CLIENT_ID=1
```

未开启 `ENABLE_LIVE_TRADING=true` 时，系统即使连接到 `IBKRBroker` 也只会生成计划并落盘为 `planning_only`，不会实际提交订单。

---

## 📅 未来路线图 (Roadmap)

本项目仍在持续迭代中。路线图以“里程碑”方式组织，便于读者理解系统会往哪个方向演进（详细任务拆分见 `TASKS.md`）。

### P0｜可信度与安全（优先级最高）

### P1｜稳定性与可观测性
- **远程访问与鉴权**：为 Dashboard 增加鉴权与安全访问策略（只读模式、访问控制、脱敏），支持部署到局域网/云端。
- **历史回放与运营视角 Dashboard**：支持按日期回看策略、持仓、执行和告警，增强问题定位与人工复盘效率。
- **无人值守运行能力增强**：当前已具备轻量定时调度、运行心跳、结构化熔断状态与 Dashboard Runtime 面板；下一步继续补每日摘要通知。
- **恢复流程与运维工具**：下一步可补充显式“恢复/解锁”脚本、恢复前检查清单，以及更细粒度的异常归因摘要。
- **执行质量监控**：补充佣金、滑点、取消率、未成交率等执行指标，帮助区分策略表现与执行摩擦。

### P2｜能力扩展
- **真实的 RAG 向量检索**：引入 `ChromaDB` 或 `FAISS`，支持研报/公告/财报长文本切片与语义检索，并在输出中引用可追溯的证据来源。
- **多策略协同决策**：从单一 LLM 计划演进到多个子策略协同，再由上层做投票或加权，减少单一 Prompt 的脆弱性。
- **测试体系与 CI**：补充 `pytest` 单元测试与集成测试，并接入 CI 以确保持续迭代不破坏核心风控与执行链路。

### 回测说明
- `run_llm_backtest.py` 目前定位为研究预览型回测工具，默认会输出一份图表报告和一份可信度摘要。
- 可通过环境变量控制样本窗口：
  - `BACKTEST_PRICE_PERIOD`
  - `BACKTEST_SAMPLE_DAYS`
  - `BACKTEST_ALLOW_SYNTHETIC_PRICES`
- 当历史行情退化为模拟价格、或历史 RAG 快照覆盖不足时，摘要会明确标记为较低可信度，避免将演示结果误解为生产级验证。

---

*Disclaimer: 本项目仅作学术研究与技术展示，LLM 生成的投资建议不构成任何真实的财务指导。量化有风险，投资需谨慎。*
