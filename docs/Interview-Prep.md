# Macro Quant Agent — 面试准备手册

## 一句话定调

> 一个 LLM 驱动的量化资产配置 Agent，核心不是让 LLM 生成交易信号就结束，而是构建了一套从数据检索 → 策略生成 → 硬约束校验 → 多 Broker 执行 → 对账审计的完整工程管线。

---

## 项目能干什么

| 能力 | 说明 |
|------|------|
| **日频策略生成** | 每天自动收集宏观/基本面/新闻/行情/SEC EDGAR 公告，喂给 LLM 生成持仓配比 |
| **7 层硬约束风控** | 单标上限、现金底线、死区过滤、集中度限制、主题暴露限制、换手率封顶等 |
| **双 Broker 模式** | Mock 模拟（本地回测）和 IBKR 实盘（TWS 仿真/真实交易） |
| **planning_only 预览** | 不下单的 dry-run 模式，生成"如果下单了会怎样"的完整预览 |
| **回测系统** | 向量化回测 + 可信度评估 |
| **Dashboard** | 双语本地 Web 仪表板，支持多日对比、决策回放、LLM 复盘 |
| **运行时监控** | 心跳检测、熔断开关、告警通知（Webhook）、运行锁防重复启动 |
| **全审计追踪** | 每个决策有快照、每笔执行有账本、每次运行有指标 |

---

## 项目当前状态

- ❌ 非生产量化交易软件
- ✅ Safe by default: `BROKER_TYPE=mock`，实盘需显式开启
- ✅ 所有代码经过 171+ 测试用例验证
- ✅ P0（4 项代码质量改进）+ P1（3 项工程化改进）全部完成

---

## 架构图

```
┌──────────────────────────────────────────────────────────┐
│                      run_agent.py                         │
│    validate_config() → build_agent() → main()            │
├──────────────────────────────────────────────────────────┤
│                MacroQuantAgent.run_daily_routine()         │
├──────────┬───────────┬───────────┬───────────┬───────────┤
│Planning  │Execution  │Persist-   │ Ops       │ Dashboard │
│Service   │Service    │enceSvc    │ Service   │ (FastAPI) │
├──────────┴───────────┴───────────┴───────────┴───────────┤
│  LLM Client   │  RAGRetriever   │  MockBroker / IBKR    │
│  Volcengine   │  αV/yf/SEC/DDG  │  PortfolioManager      │
└───────────────┴────────────────┴───────────────────────┘
```

---

## 技术栈

| 层次 | 技术 |
|------|------|
| **语言** | Python 3.9 |
| **LLM** | DeepSeek / Volcengine（统一 Client 封装），含结构化输出校验器 |
| **数据源** | Alpha Vantage（行情/宏观）、yfinance（备选行情）、SEC EDGAR（公告爬取）、DuckDuckGo（新闻搜索） |
| **Broker** | MockBroker（模拟）、IBKR（`ib_insync` 库连接 TWS/Gateway） |
| **架构** | 依赖注入的 4 层 Service 架构（Planning / Execution / Persistence / Ops） |
| **Web** | FastAPI + Jinja2 + Tailwind CSS + Playwright E2E 测试 |
| **持久化** | JSON/JSONL 快照 + SQLite |
| **测试** | pytest + unittest.mock，171+ 通过，IBKR Broker 覆盖 28 个用例 |
| **质量工具** | mypy + ruff |
| **其他** | tenacity（重试）、structlog（结构化日志）、zoneinfo（时区处理） |

---

## 核心文件路径速查

| 文件 | 作用 |
|------|------|
| `core/agent.py` | 主编排器，`run_daily_routine()` 协调 4 个 Service |
| `core/planning.py` | RAG 检索 + LLM 策略生成 |
| `core/execution.py` | 风控校验 + 调仓执行 + 对账 |
| `core/persistence.py` | 决策快照 / 执行账本 / 指标持久化 |
| `core/ops.py` | 心跳、熔断、告警评估 |
| `execution/broker.py` | BaseBroker + MockBroker + IBKRBroker |
| `execution/portfolio.py` | PortfolioManager（7 层风控逻辑所在） |
| `llm/volcengine.py` | VolcengineLLMClient |
| `llm/validator.py` | LLM 结构化输出校验 |
| `data/retriever.py` | RAGRetriever（多数据源检索引擎） |
| `config/secrets.py` | API Key / Model 配置 |
| `config/risk.py` | 风控参数 / 市场时段 / 告警配置 |
| `config/broker.py` | Broker 类型 / IBKR 连接参数 |
| `dashboard/server.py` | FastAPI Dashboard |
| `run_agent.py` | 日频运行入口 |
| `run_scheduler.py` | 定时调度器 |
| `run_llm_backtest.py` | 回测入口 |

---

## 面试话术

### Q: "介绍一下这个项目"（1 分钟版）

> "我做的是一个 LLM 驱动的量化资产配置 Agent，核心不是让 LLM 生成交易信号，而是构建了一套从数据检索 → 策略生成 → 硬约束校验 → 执行 → 对账审计的完整管线。"
>
> "系统拆了 4 个 Service——Planning、Execution、Persistence、Ops——通过依赖注入组合。默认是 mock 交易模式，开启 ENABLE_LIVE_TRADING=true 才能连 IBKR 实盘，而且还有 planning_only preview 和熔断开关做双重保护。"
>
> "所有决策都有快照、所有执行都有账本、所有运行时事件都有记录，可以在 Dashboard 上回放。"

### Q: "你怎么保证 LLM 不乱下单？"（高频问题）

> "两个层面。第一层是 **校验层**：LLM 输出的 JSON 要过 Validator，检查字段完整性、数值合理性。无效输出直接丢弃并记录错误。"
>
> "第二层是 **风控层**：即使 LLM 输出通过了校验，还要过 PortfolioManager 的 7 条硬约束——"
> 
> 1. 单标上限（≤30%）
> 2. 现金底线（≥20%）
> 3. 死区过滤（调仓 <5% 时跳过）
> 4. 最大持仓数
> 5. 前 3 大集中度限制
> 6. 主题暴露限制
> 7. 日换手率封顶
>
> "LLM 输出必须通过这全部 7 道关卡才能进入执行阶段。"

### Q: "IBKR 那部分你怎么保证不出问题？"

> "IBKRBroker 是我最小心的一块。之前零测试覆盖，我补了 28 个单元测试，覆盖了所有状态推导——Filled、Cancelled、Inactive、timeout_cancelled、partial_then_cancelled 等 8 种场景。"
>
> "超时机制也很明确：下单后最多等 10 秒，没完成的订单自动取消并标记。所有异常都触发熔断开关，不会让系统处于未知状态。"

### Q: "为什么选择依赖注入架构？"

> "我把系统拆成 4 个 Service，通过构造函数注入。好处有三个："
>
> 1. **可独立测试**：测试时可以 mock 掉 PlanningService，只测 Execution 的逻辑
> 2. **可替换**：MockBroker 和 IBKRBroker 实现同一个 BaseBroker 接口，切换 broker 只需改一个环境变量
> 3. **职责清晰**：每个 Service 文件不超过 200 行，新人看一眼就能找到代码位置

### Q: "你碰到过什么棘手的 bug？"

> "熔断和 alert 的联动问题。有段时间发现熔断触发器会在异常分支中重复触发 kill_switch。原因是 except 块和 finally 块里的 evaluate_and_notify 各自都能触发熔断。最后重构时我把熔断触发统一放到 except 里、告警放到 finally 里，职责分清楚才解决。"
>
> "这也说明了一个问题：运行时安全代码反而是最容易出 bug 的地方，因为它涉及的状态路径最多。"

### Q: "这个项目跟市面上那些 GPT+交易有什么区别？"

> "最大的区别是工程深度。大多数 demo 就是一条 prompt 下去、拿 JSON 做交易。这个项目思考的是更实际的问题："
>
> - LLM 输出不可靠怎么办 → 7 层硬约束
> - 实盘出错怎么兜底 → 熔断 + 超时自动取消 + 对账差异告警
> - 出了问题怎么查 → 决策快照、执行账本、Dashboard 回放
> - 怎么分工协作 → 拆 4 个 Service，各司其职
>
> "说到底，这是一个系统工程问题，不是 prompt 工程问题。"

### Q: "你怎么验证这个策略是赚钱的？"

> "第一，有向量化回测系统（`run_llm_backtest.py`），可以快速回测历史表现。"
> "第二，`planning_only` 模式提供了一种安全的 dry-run 方式：系统生成完整的交易计划但不实际下单，运行一段时间后可以回顾'如果当时执行了这个计划，效果会怎样'。"
> "第三，所有日终指标（持仓、现金、换手率）都有结构化日志，可以导出做进一步分析。"

### Q: "技术选型为什么选这些？"

> "LLM 选了 Volcengine/DeepSeek 而不是 OpenAI，因为："
> - 国内 API 延迟更低
> - 支持更长上下文（适合塞入完整的 RAG 上下文）
>
> "数据源多路冗余：Alpha Vantage 为主、yfinance 为备选、IBKR 为实时。任何一个挂了系统不会崩，会自动 fallback。"
>
> "Dashboard 用 FastAPI + Jinja2 而不是前后端分离，因为这是个单人工具，不需要 SSR/CSR 分离带来的复杂度。"

---

## 面试官可能追问的深度问题

| 问题 | 回答方向 |
|------|---------|
| "MockBroker 和 IBKRBroker 怎么切换？" | `BROKER_TYPE` 环境变量（mock/ibkr），依赖注入到 ExecutionService |
| "你的回测跟实盘怎么保证一致性？" | 回测用同一个 PortfolioManager 风控逻辑，但走独立数据路径 |
| "告警阈值怎么定的？" | 可配置环境变量，默认 3 次数据失败 / 2 次 LLM 无效触发告警，超过预期值就 Webhook 通知 |
| "熔断怎么恢复？" | 手动清除 `runtime/kill_switch.json`，或通过 Dashboard 恢复 |
| "为什么用 JSON 而不是数据库？" | 调试友好、Dashboard 可直接读、方便 git diff 对比两天决策。SQLite 做辅助存储 |
| "run_daily_routine 的 6 个退出路径？" | kill_switch_locked → market_closed → abort_no_prices → invalid → no_trade → planning_only → filled |
| "你做了哪些重构？" | 274 行的 `run_daily_routine()` 拆成 12 个私有方法 + 4 层 Service 注入；1300 行 retriever 引入通用引擎；重复代码消除 |

---

## 简历写法推荐

### 项目标题

> **Macro Quant Agent — LLM 驱动的量化资产配置系统**

### 2-3 行简介

> 基于 Python 的日频量化决策管线，通过 RAG 检索宏观/公告数据，结合 LLM 生成持仓策略，经 7 层硬约束校验后执行调仓。支持 Mock 本地模拟和 IBKR 实盘交易，含完整的对账、审计追踪和双语 Dashboard。

### 要点列表（选 3-4 个）

```
• 设计并实现 4 层依赖注入架构（Planning / Execution / Persistence / Ops），
  使各模块可独立测试和替换
• 构建 7 层风控约束管线（单标上限/集中度/换手率封顶/死区过滤等），
  杜绝 LLM 非法输出进入执行阶段
• 封装 IBKR TWS 实盘适配器，覆盖 28 个单元测试，
  含连接超时、部分成交、券商拒单等边缘场景
• 开发双语 Web Dashboard（FastAPI + Tailwind），
  支持多日对比、决策回放、LLM 复盘和自动简报
```

---

## 推荐的话术结构（层层递进）

```
[一句话定调] → [工程架构] → [安全设计] → [具体例子] → [收尾]
```

1. **一句话定调**（10 秒）："我做的是一个 LLM 驱动的量化资产配置 Agent……"
2. **讲工程架构**（20 秒）："系统拆了 4 个 Service、依赖注入、每层可独立测试……"
3. **讲安全设计**（20 秒）："7 层硬约束 + 熔断 + planning_only + 市场时段检查……"
4. **讲具体例子**（20 秒）："比如死区过滤：如果 LLM 建议的调仓幅度 < 5%，我就跳过这次交易……"
5. **收尾**（10 秒）："这个项目让我理解了 Agent 工程化不只是写 prompt，而是怎么让 LLM 操作真实系统时安全、可审计。"
