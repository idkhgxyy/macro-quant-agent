# Macro Quant Agent Code Wiki

## 1. 项目概览

### 1.1 项目定位

`Macro Quant Agent` 是一个以 Python 为核心的研究型量化资产配置系统，目标不是“让 LLM 输出一份 JSON”就结束，而是把以下能力串成完整闭环：

- 数据检索与上下文拼装
- LLM 组合规划
- 风控校验与清洗
- 调仓订单生成
- Mock / IBKR 券商执行
- 执行后对账与留痕
- 心跳、告警、熔断、Dashboard 可观测性
- 历史回测与研究报告

项目强调三个关键词：

- **安全默认值**：默认 `BROKER_TYPE=mock`，不开启 `ENABLE_LIVE_TRADING` 时不会向 IBKR 实盘提交订单
- **工程闭环**：从 RAG 到执行再到审计、复盘和运维可观测，全链路贯通
- **研究优先**：文件持久化、本地 Dashboard、向量化回测都更偏研究和演示，而非生产级交易基础设施

### 1.2 仓库核心能力

1. 根据宏观、基本面、新闻和市场数据，生成科技股股票池的目标权重。
2. 在执行前对 LLM 输出执行组合约束和风险规则清洗。
3. 根据当前资产与目标权重生成调仓订单。
4. 支持 `MockBroker` 本地仿真和 `IBKRBroker` 真/仿真接入。
5. 通过 `SnapshotDB`、`ExecutionLedger`、`MetricsDB`、`HeartbeatStore` 保留每日运行证据。
6. 通过 Dashboard、事件日志和告警策略提供运行时观测能力。
7. 通过 `run_llm_backtest.py` 对历史窗口做 LLM 回放与研究报告输出。

## 2. 顶层目录结构

```text
isolation/
├── backtest/                 # 回测引擎
├── core/                     # 核心编排器
├── dashboard/                # 本地 Dashboard API 与静态前端
├── data/                     # 数据源接入、缓存、快照
├── execution/                # 组合调仓、券商适配、账本、对账
├── legacy/                   # 历史实验代码，不在当前主链路
├── llm/                      # 模型调用、输出校验
├── reports/                  # 每日报告与图表生成
├── tests/                    # 回归测试
├── utils/                    # 运维与基础设施工具
├── config.py                 # 全局配置与风险参数
├── policy.py                 # LLM 投资政策与输出 Schema
├── run_agent.py              # 日常运行入口
├── run_llm_backtest.py       # LLM 回测入口
├── run_scheduler.py          # 轻量调度器入口
└── strategy_registry.py      # 策略目录与策略 ID 定义
```

### 2.1 当前主链路目录

- `core/`
- `data/`
- `llm/`
- `execution/`
- `utils/`
- `dashboard/`
- `backtest/`
- `reports/`
- `tests/`

### 2.2 非主链路目录

- `legacy/`：保留旧实验实现，不属于当前系统执行路径

## 3. 架构总览

### 3.1 分层视角

```text
配置层
  config.py / policy.py / strategy_registry.py
        |
        v
编排层
  core/agent.py (MacroQuantAgent)
        |
        +------------------+
        |                  |
        v                  v
数据检索层              LLM 层
data/retriever.py       llm/volcengine.py
data/cache.py           llm/validator.py
data/ibkr_data.py
data/earnings_agent.py
        |                  |
        +--------+---------+
                 v
执行层
execution/portfolio.py
execution/broker.py
execution/reconcile.py
execution/ledger.py
                 |
                 v
状态/审计/运维层
SnapshotDB / MetricsDB / HeartbeatStore / KillSwitchStore
events / alerts / reports / dashboard
```

### 3.2 主执行链路

```text
run_agent.py
  -> build_agent()
  -> MacroQuantAgent.run_daily_routine()
      -> 检查 kill switch
      -> 判断市场时段
      -> RAGRetriever 拉取四类上下文
      -> SnapshotDB 保存 rag 快照
      -> VolcengineLLMClient.generate_strategy()
      -> validator 清洗与校验
      -> PortfolioManager.rebalance()
      -> 运行时守卫判断是否 planning_only
      -> Broker.submit_orders()
      -> reconcile_execution()
      -> ExecutionLedger / SnapshotDB / PortfolioDB 写入
      -> HeartbeatStore / MetricsDB / Alerting 更新
      -> Dashboard 与报表层消费这些产物
```

## 4. 入口程序与运行模式

### 4.1 `run_agent.py`

主日常入口，负责装配系统：

- 创建 `RAGRetriever`
- 创建 `VolcengineLLMClient`
- 按 `BROKER_TYPE` 选择 `MockBroker` 或 `IBKRBroker`
- 最终构建 `MacroQuantAgent`
- 调用 `run_daily_routine()`

适用场景：

- 手动日常运行
- 调度器触发的被调用入口

### 4.2 `run_scheduler.py`

轻量级轮询调度器，按配置时间每天触发一次 agent：

- 使用 `AGENT_SCHEDULER_ENABLED` 控制是否启动
- 使用 `AGENT_SCHEDULE_TIME` 和 `AGENT_SCHEDULE_TIMEZONE` 控制触发时间
- 将调度状态写入 `HeartbeatStore.scheduler`
- 到点后调用 `run_agent.main(run_mode="scheduled")`

### 4.3 `run_llm_backtest.py`

回测入口，核心逻辑：

- 下载历史价格
- 读取历史 `rag_YYYY-MM-DD.json`
- 对每个历史交易日生成一份 LLM 权重
- 构造 `weights_df`
- 交给 `VectorizedBacktester`
- 输出 PNG 图表和 Markdown 可信度摘要

### 4.4 `dashboard/server.py`

本地运维查看入口，启动一个 `ThreadingHTTPServer`：

- 服务静态前端页面
- 暴露 `/api/*` 数据接口
- 支持 `DASHBOARD_TOKEN` 鉴权

## 5. 核心编排层

### 5.1 `core/agent.py`

该文件定义项目的核心类 `MacroQuantAgent`，它不是策略本身，而是“总调度器”。

#### 5.1.1 `MacroQuantAgent.__init__`

职责：

- 注入三大依赖：`llm_client`、`retriever`、`broker`
- 初始化 `KillSwitchStore`
- 启动时先从 broker 读取真实资金与持仓

含义：

- Agent 的“当前仓位”以 broker 为准，而不是本地文件为准
- 本地 `PortfolioDB` 只在 Mock 模式下起到状态恢复作用

#### 5.1.2 `check_kill_switch()`

职责：

- 检查全局熔断是否已触发
- 如果 `kill_switch.lock` 或结构化状态显示已锁定，则阻止后续运行

设计意义：

- 防止严重异常后调度器继续重复执行

#### 5.1.3 `trigger_kill_switch(reason, source, trigger_event)`

职责：

- 记录严重错误
- 发出 critical 事件
- 写入结构化 kill switch 状态和锁文件

触发场景：

- 主流程异常
- 告警策略达到阈值且允许自动熔断

#### 5.1.4 `run_daily_routine()`

这是全仓库最重要的函数，完整流程如下。

##### 阶段 0：运行初始化

- 生成交易日 `date_str`
- 启动 `HeartbeatStore.start_run()`
- 初始化 metrics 上下文

##### 阶段 1：熔断与市场时段检查

- 如果 kill switch 生效，立即退出
- 使用 `get_market_session()` 判断：
  - 是否交易日
  - 是否休市
  - 当前是否允许下单
  - 是否半日市

如果市场关闭：

- 直接写 `decision` 快照
- 状态记为 `market_closed`
- 不再进入检索与 LLM 环节

##### 阶段 2：RAG 检索

通过 `RAGRetriever` 拉取：

- 宏观数据 `fetch_macro_data()`
- 基本面数据 `fetch_fundamental_data()`
- 新闻数据 `fetch_news()`
- 市场数据 `fetch_market_data()`

随后：

- 汇总 provider 状态
- 保存 `rag` 快照
- 计算当前组合估值与持仓摘要

##### 阶段 3：LLM 规划

调用 `self.llm.generate_strategy(...)`，输入包括：

- 当前持仓摘要
- 宏观上下文
- 基本面上下文
- 新闻上下文
- 市场上下文

输出读取字段：

- `reasoning`
- `allocations`
- `selected_strategies`
- `_valid`
- `_errors`
- `_warnings`
- `_audit`

如果校验失败：

- 状态记为 `invalid`
- 仅保存快照
- 不生成订单

##### 阶段 4：调仓方案生成

调用 `PortfolioManager.rebalance(...)`：

- 现金 + 持仓 * 市价计算总资产
- 目标权重转订单列表
- 应用死区过滤与换手率限制

如果没有订单：

- 状态记为 `no_trade`
- 说明当前仓位已接近目标仓位

##### 阶段 5：执行守卫

在真正下单前还要经过两层守卫：

1. 交易时段守卫
   - 若开启 `ENFORCE_RTH` 且不允许盘前盘后，则不下单
2. Live Trading 守卫
   - `BROKER_TYPE=ibkr` 且 `ENABLE_LIVE_TRADING=false` 时，只允许生成计划

如果守卫拦截：

- 状态记为 `planning_only`
- 订单只进入快照，不提交到 broker

##### 阶段 6：订单执行与对账

调用 `broker.submit_orders(proposed_orders)` 后：

- 获取执行回报 `execution_report`
- 根据 `requested / filled / status` 计算执行摘要
- 再次从 broker 拉取真实账户快照
- 使用 `reconcile_execution()` 校验成交结果与账户变化是否一致
- 保存 `ExecutionLedger`
- 保存 `decision` 快照
- 更新本地 `PortfolioDB`

##### 阶段 7：收尾与告警

在 `finally` 中一定会执行：

- `HeartbeatStore.finish_run()`
- `MetricsDB.append()`
- `evaluate_and_notify()`

如果告警策略触发且开启自动熔断：

- 自动写入 kill switch

### 5.2 编排层的设计特点

- **强编排**：几乎所有业务路径都由 `MacroQuantAgent` 收口
- **状态可追溯**：RAG 快照、决策快照、执行账本、指标、事件相互关联
- **执行与规划分离**：即使不允许下单，也允许完整生成计划用于审计

## 6. 配置层

### 6.1 `config.py`

该文件集中维护系统运行参数。

#### 6.1.1 凭证与外部接入

- `ALPHA_VANTAGE_KEY`
- `VOLCENGINE_API_KEY`
- `VOLCENGINE_MODEL_ENDPOINT`
- `IBKR_HOST`
- `IBKR_PORT`
- `IBKR_CLIENT_ID`
- `IBKR_DATA_CLIENT_ID`

#### 6.1.2 投资池

`TECH_UNIVERSE` 固定为九只科技股：

- `AAPL`
- `MSFT`
- `NVDA`
- `GOOGL`
- `META`
- `AMZN`
- `TSLA`
- `PLTR`
- `MU`

这是系统所有组合建议、风险控制、执行对账和测试的共同基线。

#### 6.1.3 调度与市场时段

- `MARKET_TIMEZONE`
- `AGENT_SCHEDULER_ENABLED`
- `AGENT_SCHEDULE_TIME`
- `AGENT_SCHEDULE_TIMEZONE`
- `AGENT_SCHEDULE_POLL_SECONDS`
- `ENFORCE_RTH`
- `RTH_START`
- `RTH_END`
- `HALF_DAY_RTH_END`
- `ALLOW_OUTSIDE_RTH`

#### 6.1.4 告警与通知

- `ALERT_WEBHOOK_URL`
- `ALERT_COOLDOWN_SECONDS`
- `ALERT_DATA_FAILED_THRESHOLD`
- `ALERT_LLM_INVALID_THRESHOLD`
- `ALERT_ORDER_PROBLEM_THRESHOLD`
- `ALERT_EXCEPTION_THRESHOLD`
- `ALERT_AUTO_KILL_SWITCH`

#### 6.1.5 组合构建与风险控制

- `MAX_HOLDINGS`
- `MIN_POSITION_WEIGHT`
- `MAX_TOP3_SUM`
- `RISK_EXPOSURE_GROUP_CAPS`
- `MIN_CASH_RATIO`
- `MAX_DAILY_TURNOVER`
- `DEADBAND_THRESHOLD`
- `MAX_SINGLE_POSITION`
- `MAX_API_ERRORS`

#### 6.1.6 Broker 模式

- `BROKER_TYPE`
- `ENABLE_LIVE_TRADING`

设计重点：

- 实际下单行为由配置显式控制
- 风险参数与 LLM policy 共用同一组约束来源，保证“提示词规则”和“执行期规则”一致

### 6.2 `policy.py`

定义 LLM 交互中的“硬政策文本”。

核心函数：

- `get_prompt_version()`
- `get_system_prompt_text()`
- `get_investment_policy_text()`
- `get_output_schema_text()`

作用：

- 把风控约束转成提示词
- 强制 LLM 输出固定 JSON 结构
- 提供 prompt 版本号以便审计

### 6.3 `strategy_registry.py`

维护可选策略目录 `STRATEGY_CATALOG`，当前包含：

- `core_hold_momentum_tilt`
- `macro_risk_on_off`
- `quality_tilt`
- `vol_targeting`
- `news_overlay_sparse`

设计目的：

- 不让 LLM 在“策略框架”上无限发散
- 要求模型在有限策略集合里做组合决策
- 让 `selected_strategies` 字段可审计、可统计

## 7. 数据检索层

### 7.1 `data/retriever.py`

`RAGRetriever` 是整个数据层的核心对象，负责把多个数据源统一成 LLM 所需上下文。

#### 7.1.1 负责的四类数据

- 新闻 `news`
- 市场数据 `market`
- 宏观数据 `macro`
- 基本面数据 `fundamental`

#### 7.1.2 支持的数据源

- Alpha Vantage
- yfinance
- FRED
- IBKR
- 本地缓存
- 旧缓存兜底

#### 7.1.3 关键设计能力

1. **本地缓存**
   - 避免频繁请求外部 API
   - 通过 `CacheDB` 做 TTL 与 stale fallback

2. **Provider Budget**
   - 记录不同数据源每日预算
   - 在接近上限时优先复用旧快照

3. **Provider Cooldown**
   - 某 provider 失败后进入冷却期
   - 防止短时间重复打爆限流或认证错误

4. **Provider Trace**
   - 记录每类数据最终用的是哪个 provider
   - 记录尝试链路、失败原因和预算状态

5. **多级降级**
   - 先 fresh cache
   - 再 stale cache
   - 再次级 provider
   - 最后兜底占位文本或 dummy prices

#### 7.1.4 关键函数说明

##### `fetch_news()`

职责：

- 优先读缓存
- 再尝试 Alpha Vantage 新闻接口
- 失败后回退到 stale cache
- 最终无法获取时返回“新闻获取失败”占位文本

##### `fetch_market_data()`

职责：

- 在 `ibkr` 模式下优先用 `IBKRDataProvider`
- 否则优先 Alpha Vantage，再回退到 yfinance
- 输出结构统一为：

```python
{
  "context_string": "...",
  "prices": {"AAPL": 170.0, "...": ...},
  "source": "..."
}
```

##### `fetch_macro_data()`

职责：

- `ibkr` 模式下尝试 IBKR 宏观快照
- 非 `ibkr` 模式优先 FRED，再回退到 yfinance
- 输出给 LLM 的是纯文本宏观摘要

##### `fetch_fundamental_data()`

职责：

- 优先 Alpha Vantage 公司概览
- 再回退到 yfinance 的 `stock.info`
- 同时接入 `EarningsResearchAgent` 补充财报窗口信息

#### 7.1.5 `RAGRetriever` 的架构价值

- 屏蔽外部数据源差异
- 给 LLM 提供结构一致的上下文
- 为运行稳定性引入预算、冷却、缓存和降级体系

### 7.2 `data/cache.py`

包含两个本地状态类。

#### 7.2.1 `CacheDB`

职责：

- 保存带 TTL 的缓存
- 支持 `get_stale()` 读取过期但仍可兜底的数据
- 支持 provider 预算和冷却信息的存储

#### 7.2.2 `PortfolioDB`

职责：

- 本地保存 cash 和 positions
- 主要用于 Mock 模式下的“跨天状态恢复”

### 7.3 `data/snapshot_db.py`

`SnapshotDB` 用于保存两类点时快照：

- `rag_YYYY-MM-DD.json`
- `decision_YYYY-MM-DD.json`

用途：

- 运行审计
- Dashboard 展示
- 回测时按日期复用历史 RAG 快照

### 7.4 `data/ibkr_data.py`

`IBKRDataProvider` 提供与交易执行分开的数据通道：

- `fetch_market_snapshot()`：股票延迟行情与 1 个月涨跌幅
- `fetch_macro_snapshot()`：VIX 与 TNX 指标

设计意义：

- 检索层可以复用 IBKR 作为数据源
- 与执行层 `IBKRBroker` 解耦

### 7.5 `data/earnings_agent.py`

`EarningsResearchAgent` 不是独立 agent 框架，而是一个财报辅助摘要器。

职责：

- 识别最近财报日期
- 在财报窗口内补充营收、盈利、利润率、EPS 等摘要信息

## 8. LLM 层

### 8.1 `llm/volcengine.py`

`VolcengineLLMClient` 负责模型调用和审计留痕。

#### 8.1.1 输入拼装

生成 prompt 时会整合：

- `policy.py` 中的投资政策
- `strategy_registry.py` 中的策略目录
- 当前持仓摘要
- 宏观上下文
- 基本面上下文
- 新闻上下文
- 市场上下文
- 输出 JSON Schema

#### 8.1.2 审计字段

内部通过 `_make_audit_base()` 记录：

- prompt 版本
- model endpoint
- mode
- system prompt hash
- user prompt hash
- prompt 长度
- 尝试次数
- 原始模型输出
- validator 错误与警告
- repair 过程信息

这使得每一次 LLM 决策都可以被事后审计。

#### 8.1.3 `generate_strategy(...)`

逻辑分为三步：

1. 调用 LLM 获取初始结果
2. 解析 JSON，并调用 `validate_and_clean_strategy_plan()`
3. 若 live 模式下第一次未通过校验，发起一次 repair 重问

#### 8.1.4 失败时的降级策略

- `backtest` 模式：LLM 失败时退化为等权组合
- `live` 模式：LLM 失败时返回无效计划，阻止执行

设计意义：

- 回测强调可继续跑通
- 实盘强调宁可不交易也不误交易

### 8.2 `llm/validator.py`

`validate_and_clean_strategy_plan(plan)` 是模型输出进入执行层前的关键过滤器。

#### 8.2.1 处理内容

- 非数字权重清洗
- 负权重归零
- 超单票上限截断
- 小于最小持仓权重的仓位归零
- 超过 `MAX_HOLDINGS` 时仅保留最大仓位
- `TOP3` 集中度缩放
- 风险暴露分组缩放
- `selected_strategies` 合法性清洗
- `evidence` 格式清洗

#### 8.2.2 注意点

- 该函数会生成 `errors` 和 `warnings`
- 大部分组合约束以“清洗 + 警告”的方式处理，而不是直接异常
- `MIN_CASH_RATIO` 在这里更多是提示候选违规，真正执行期仍会再次处理

### 8.3 LLM 层的设计价值

- **双保险**：提示词约束 + 后处理校验
- **可审计**：记录模型原始输出和修复过程
- **可恢复**：live 失败即停止，backtest 失败则降级

## 9. 执行层

### 9.1 `execution/portfolio.py`

`PortfolioManager.rebalance(cash, positions, target_weights, current_prices)` 负责把“目标权重”变成“订单列表”。

#### 9.1.1 处理步骤

1. 计算当前总资产
2. 再次应用单票上限
3. 应用现金缓冲约束
4. 计算每只股票的目标金额与当前金额差异
5. 依据价格换算成整数股数
6. 应用 deadband 过滤微小调整
7. 估算换手率
8. 若超出 `MAX_DAILY_TURNOVER`，按比例缩小全部订单
9. 输出标准订单结构

#### 9.1.2 订单结构

```python
{
  "ticker": "AAPL",
  "action": "BUY" or "SELL",
  "shares": 10,
  "price": 170.0,
  "amount": 1700.0
}
```

#### 9.1.3 设计特点

- 偏“目标权重到订单”的轻量执行官
- 不处理复杂成交模拟
- 依赖 broker 层完成真实/模拟撮合

### 9.2 `execution/broker.py`

定义 broker 抽象与两种实现。

#### 9.2.1 `BaseBroker`

定义统一接口：

- `get_account_summary()`
- `submit_orders()`

这使 `MacroQuantAgent` 不需要关心底层是真实券商还是模拟券商。

#### 9.2.2 `IBKRBroker`

职责：

- 连接 `ib_insync`
- 拉取账户现金与持仓
- 提交市价单
- 等待成交状态进入终态
- 对超时未终结订单尝试取消
- 返回执行回报

关键特点：

- 自动处理连接与断开
- 使用 `outsideRth` 与 `ALLOW_OUTSIDE_RTH` 配合
- 执行结果保留 `requested / filled / avg_fill_price / status / order_id`

#### 9.2.3 `MockBroker`

职责：

- 在内存里维护虚拟现金与持仓
- 模拟成交
- 随机引入少量拒单概率

适合：

- 本地演示
- 回归测试
- 无 IBKR 环境下的研究运行

### 9.3 `execution/reconcile.py`

`reconcile_execution(...)` 用于执行后对账。

职责：

- 根据成交回报推导预期仓位变化
- 对比实际账户仓位变化
- 输出 `ok / mismatched / cash_delta`

价值：

- 即使 broker 返回成交，系统仍会再次验证账户状态变化是否匹配

### 9.4 `execution/ledger.py`

`ExecutionLedger` 将每日执行结果写到 `ledger/execution_YYYY-MM-DD.json`。

通常包含：

- 执行前现金与仓位
- 计划订单
- 执行回报
- 执行后现金与仓位
- 对账结果

## 10. 回测层

### 10.1 `backtest/engine.py`

`VectorizedBacktester` 是轻量向量化回测器。

#### 10.1.1 `run_backtest(historical_prices, daily_target_weights)`

核心逻辑：

- 对齐价格与权重时间轴
- 计算日收益率
- 用 `shift(1)` 避免前视偏差
- 依据权重变化估算手续费
- 计算策略净值与等权基准净值

#### 10.1.2 `generate_report(...)`

输出：

- 总收益
- 年化收益
- 最大回撤
- 夏普比率
- 资金曲线与回撤图

### 10.2 `run_llm_backtest.py` 的研究增强

相比普通回测脚本，它还补了两项研究能力：

1. **历史 RAG 快照回放**
   - 尽可能读取真实历史上下文
2. **可信度摘要**
   - 记录快照覆盖率
   - 标记是否使用 synthetic prices
   - 给出 `credibility` 标签

这让回测结果不是只有收益曲线，还包含证据质量提示。

## 11. 运维与可观测性层

### 11.1 `utils/heartbeat.py`

`HeartbeatStore` 用于记录运行状态。

文档结构大致包含：

- `current`
- `last_run`
- `last_success`
- `recent_runs`
- `scheduler`

关键函数：

- `start_run()`
- `finish_run()`
- `update_scheduler()`

用途：

- 让 Dashboard 和运维脚本知道系统最近是否运行成功

### 11.2 `utils/kill_switch.py`

`KillSwitchStore` 维护两套熔断状态：

- `kill_switch.lock` 兼容传统锁文件
- `runtime/kill_switch.json` 维护结构化状态和历史记录

关键函数：

- `load()`
- `trigger()`
- `clear()`
- `is_locked()`

### 11.3 `utils/events.py`

提供事件与异常分类基础设施。

#### 11.3.1 `classify_exception(e)`

将异常粗分类为：

- `rate_limit`
- `timeout`
- `auth`
- `quota`
- `connect_failed`
- `unknown`

#### 11.3.2 `emit_event(...)`

职责：

- 将事件写入 `events/events.jsonl`
- 对 `ERROR` / `CRITICAL` 级别同步写入 `alerts/alerts.jsonl`
- 输出到日志

### 11.4 `utils/alerting.py`

`evaluate_and_notify(...)` 基于本次运行窗口内产生的告警，更新累计计数并决定是否触发通知。

可累计的风险维度：

- `data_failed`
- `llm_invalid`
- `order_problem`
- `exception`

支持：

- 冷却窗口
- webhook 发送
- 自动建议/触发 kill switch

### 11.5 `utils/metrics.py`

`MetricsDB.append(record)` 负责把运行指标追加到 `metrics/metrics.jsonl`。

常见指标：

- `status`
- `rag_sec`
- `llm_sec`
- `rebalance_sec`
- `submit_sec`
- `reconcile_sec`
- `turnover`
- `order_count`
- `market_state`
- `prompt_version`

### 11.6 `utils/review.py`

`build_day_review(...)` 用于构建单日复盘摘要。

输出包括：

- 状态
- 策略 ID
- 目标组合 Top allocations
- 现金比例
- 仓位变化
- 订单摘要
- 执行质量
- 滑点估算
- 对账结果
- 亮点文本

该函数既被 Dashboard 使用，也被每日报告使用。

### 11.7 `utils/trading_hours.py`

负责美股交易时段判断。

能力包括：

- 计算美国市场假日
- 计算半日市
- 判断当前是 `open / planning_only / closed`
- 输出是否允许生成计划和是否允许下单

### 11.8 其他基础设施工具

- `utils/logger.py`
  - 配置控制台 + 文件日志
- `utils/structlog.py`
  - 追加结构化日志 `logs/structured.jsonl`
- `utils/retry.py`
  - 用 `tenacity` 包装重试
- `utils/file_rotate.py`
  - 文本文件轮转
- `utils/webhook.py`
  - 发送 JSON webhook

## 12. Dashboard 与报告层

### 12.1 `dashboard/server.py`

`DashboardHandler` 提供 API 和静态资源。

#### 12.1.1 鉴权

当设置 `DASHBOARD_TOKEN` 时，可以通过以下方式传 token：

- `Authorization: Bearer <token>`
- `X-Dashboard-Token: <token>`
- 查询参数 `?token=...`

#### 12.1.2 关键 API

- `/api/ping`
- `/api/dates`
- `/api/decision`
- `/api/rag`
- `/api/ledger`
- `/api/alerts`
- `/api/events`
- `/api/log`
- `/api/metrics`
- `/api/heartbeat`
- `/api/review`
- `/api/equity`

#### 12.1.3 数据来源

Dashboard 本身不参与交易决策，只读取本地产物：

- `snapshots/`
- `ledger/`
- `alerts/`
- `events/`
- `logs/`
- `metrics/`
- `runtime/`

### 12.2 `reports/generate_daily_report.py`

按指定日期汇总：

- 当日运行次数与状态
- LLM 有效率
- 换手率
- 运行时延
- 日复盘摘要
- 数据源成功率

输出到 `reports/daily_report_<date>.md`

### 12.3 `reports/generate_charts.py`

从 `metrics.jsonl` 中生成简单 HTML/SVG 图表，包括：

- 运行状态柱状图
- LLM 延迟折线图
- 总耗时折线图
- 换手率折线图

## 13. 持久化与运行产物

项目主要使用文件持久化，核心产物如下：

### 13.1 快照与账本

- `snapshots/rag_<date>.json`
- `snapshots/decision_<date>.json`
- `ledger/execution_<date>.json`
- `portfolio_state.json`
- `data_cache.json`

### 13.2 运行时状态

- `runtime/heartbeat.json`
- `runtime/kill_switch.json`
- `kill_switch.lock`

### 13.3 指标、事件与告警

- `metrics/metrics.jsonl`
- `events/events.jsonl`
- `alerts/alerts.jsonl`
- `alerts/policy_state.json`

### 13.4 日志与报告

- `logs/trading_system.log`
- `logs/structured.jsonl`
- `reports/daily_report_<date>.md`
- `reports/charts.html`
- `reports/llm_backtest_summary.md`
- `*.png` 回测图

## 14. 关键数据结构

### 14.1 LLM 输出计划

```json
{
  "reasoning": "分析逻辑",
  "selected_strategies": ["core_hold_momentum_tilt"],
  "allocations": {
    "AAPL": 0.2,
    "MSFT": 0.2,
    "NVDA": 0.1
  },
  "evidence": [
    {
      "source": "macro",
      "quote": "VIX 低于 20，市场风险偏好稳定",
      "ticker": null
    }
  ]
}
```

### 14.2 决策快照 `decision`

常见字段：

- `status`
- `reasoning`
- `plan`
- `llm_audit`
- `orders`
- `execution_report`
- `execution_summary`
- `reconciliation`
- `positions_after`
- `cash_after`
- `market_session`
- `run_start_ts`

### 14.3 指标记录 `metrics`

常见字段：

- `date`
- `broker`
- `run_mode`
- `status`
- `rag_sec`
- `llm_sec`
- `turnover`
- `order_count`
- `market_state`
- `prompt_version`

## 15. 模块依赖关系

### 15.1 关键依赖图

```text
config.py
  -> policy.py
  -> run_agent.py
  -> run_scheduler.py
  -> run_llm_backtest.py
  -> data/retriever.py
  -> execution/portfolio.py
  -> execution/broker.py

strategy_registry.py
  -> llm/volcengine.py
  -> llm/validator.py

data/retriever.py
  -> data/cache.py
  -> data/earnings_agent.py
  -> data/ibkr_data.py
  -> utils/retry.py
  -> utils/events.py
  -> utils/trading_hours.py

llm/volcengine.py
  -> policy.py
  -> strategy_registry.py
  -> llm/validator.py
  -> utils/events.py

core/agent.py
  -> data/retriever.py
  -> llm/volcengine.py
  -> execution/portfolio.py
  -> execution/broker.py
  -> execution/reconcile.py
  -> execution/ledger.py
  -> data/cache.py
  -> data/snapshot_db.py
  -> utils/heartbeat.py
  -> utils/kill_switch.py
  -> utils/events.py
  -> utils/structlog.py
  -> utils/metrics.py
  -> utils/alerting.py
  -> utils/trading_hours.py

dashboard/server.py
  -> utils/review.py
  -> utils/heartbeat.py
  -> utils/kill_switch.py
```

### 15.2 依赖设计结论

- `core/agent.py` 是耦合中心
- `config.py` 是横切基础模块
- Dashboard 与 reports 是消费侧，只读运行产物
- 执行层和检索层通过编排层隔离，没有直接强耦合

## 16. 运行方式

### 16.1 环境准备

```bash
pip install -r requirements.txt
```

### 16.2 最小 `.env` 示例

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

### 16.3 运行日常 Agent

```bash
python3 run_agent.py
```

### 16.4 运行回测

```bash
python3 run_llm_backtest.py
```

### 16.5 启动 Dashboard

```bash
python3 dashboard/server.py
```

默认地址：

```text
http://127.0.0.1:8010/
```

### 16.6 启动调度器

```env
AGENT_SCHEDULER_ENABLED=true
AGENT_SCHEDULE_TIME=16:10
AGENT_SCHEDULE_TIMEZONE=America/New_York
AGENT_SCHEDULE_POLL_SECONDS=30
```

```bash
python3 run_scheduler.py
```

### 16.7 运行测试

```bash
python3 -m pytest -q
```

## 17. 外部依赖与技术栈

### 17.1 Python 依赖

- `pandas`
- `numpy`
- `yfinance`
- `matplotlib`
- `openai`
- `ib_insync`
- `python-dotenv`
- `tenacity`

### 17.2 外部服务

- Volcengine / BytePlus 大模型接口
- Alpha Vantage
- FRED
- yfinance
- IBKR TWS / Gateway

### 17.3 CI

GitHub Actions 工作流会：

- 安装 Python 3.11
- 安装 `requirements.txt`
- 运行 `pytest -q`

## 18. 测试覆盖说明

当前测试重点覆盖以下风险区域：

- `test_portfolio_manager.py`
  - 调仓与风险规则
- `test_validator_risk_exposure.py`
  - LLM 输出清洗与暴露限制
- `test_reconcile_execution.py`
  - 执行对账逻辑
- `test_retriever_providers.py`
  - provider 选择、降级、缓存与预算行为
- `test_dashboard_auth.py`
  - Dashboard token 鉴权
- `test_heartbeat_scheduler.py`
  - 心跳与调度时间逻辑
- `test_runtime_guards.py`
  - planning-only / live trading / 守卫逻辑
- `test_llm_audit.py`
  - LLM 审计元数据
- `test_day_review.py`
  - 复盘摘要构造
- `test_backtest_summary.py`
  - 回测可信度摘要
- `test_trading_hours.py`
  - 交易时段判断
- `test_kill_switch_state.py`
  - 熔断状态持久化

结论：

- 测试不是围绕“收益效果”，而是围绕“工程可靠性”和“运行安全性”

## 19. 典型运行场景

### 19.1 本地安全演示

推荐配置：

- `BROKER_TYPE=mock`
- `ENABLE_LIVE_TRADING=false`

效果：

- 系统会完整执行检索、LLM、风控、调仓和记录
- 但只在 Mock 账本中模拟交易

### 19.2 IBKR 连接但只做计划

推荐配置：

- `BROKER_TYPE=ibkr`
- `ENABLE_LIVE_TRADING=false`

效果：

- 系统可读取真实账户和行情
- 生成计划和订单草案
- 不会真的提交订单

### 19.3 IBKR 可执行模式

需要配置：

- `BROKER_TYPE=ibkr`
- `ENABLE_LIVE_TRADING=true`
- TWS / Gateway 正常开启
- 交易时段允许下单

仍然会被以下条件阻断：

- 市场关闭
- 盘前盘后守卫
- kill switch 锁定
- LLM 输出无效

## 20. 设计优点与局限

### 20.1 优点

- 模块边界清晰，检索、LLM、执行、运维分层明确
- 安全默认值合理，实盘提交通道被显式开关保护
- 全链路留痕较完整，适合审计与复盘
- Dashboard、reports、metrics 让运行态透明度较高
- Retriever 的预算、冷却、缓存和降级设计较成熟

### 20.2 局限

- 文件持久化为主，不适合多实例部署
- `MacroQuantAgent` 作为主编排器承担职责较重
- 回测仍是研究型近似模拟，不是高保真成交仿真
- 数据源质量受免费接口额度和稳定性限制
- 当前系统更适合单机研究环境，而非生产级交易平台

## 21. 扩展建议

### 21.1 若要扩展策略能力

优先修改：

- `strategy_registry.py`
- `policy.py`
- `llm/validator.py`

### 21.2 若要接入新数据源

优先修改：

- `data/retriever.py`
- 必要时新增 provider adapter
- 补充 provider budget / cooldown / trace 逻辑

### 21.3 若要接入新 broker

实现一个继承 `BaseBroker` 的新类，并满足：

- `get_account_summary()`
- `submit_orders()`

然后在 `run_agent.py` 中加入装配逻辑。

### 21.4 若要提升生产可用性

建议方向：

- 将文件状态迁移到 SQLite / Postgres
- 把编排器拆分成更细的 service 层
- 增加类型检查和 lint
- 增强订单生命周期与执行质量分析
- 引入更正式的任务调度和监控体系

## 22. 一句话总结

这个仓库的本质不是“一个会选股的 LLM demo”，而是一个围绕 **LLM 组合规划** 构建的 **研究型量化执行闭环系统**：它把数据检索、策略生成、风控清洗、订单执行、对账留痕、运行告警和复盘展示连接在了一起。
