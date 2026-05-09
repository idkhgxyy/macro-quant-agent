# TASKS

本文件用于跟踪项目的内部开发进度（对外 Roadmap 请看 README）。

## P0｜可信度与安全

- [x] 默认安全模式：`BROKER_TYPE` 默认 `mock`，实盘提交需显式开启 `ENABLE_LIVE_TRADING`，未开启时仅生成计划不下单
- [x] LLM 输出强校验器（字段/类型/范围/权重和/单票上限/缺失补 0）
- [x] LLM 输出异常时的纠错闭环（自动重问一次）与降级策略（更高现金/不交易/沿用上一次有效权重）
- [x] 组合构建约束：最大持仓数、最小建仓阈值、Top3 集中度上限（自动清洗 LLM 输出）
- [x] Point-in-Time 数据快照：新闻/宏观/基本面/行情按日期落盘（含时间戳与来源）
- [x] 回测按日期回放 RAG 快照（移除“复用今天新闻/基本面”的未来函数）
- [x] 决策审计记录：保存检索证据与决策结果落盘（下一步可补 prompt 版本与 LLM 原始输出）
- [x] IBKR 订单状态机：submitted/partial/filled/rejected/cancelled
- [x] 交易对账：成交回写本地成交簿/订单簿，更新账本并验证与 IBKR 账户一致
- [x] 执行状态细分：将 traded 拆分为 filled/partial/cancelled/rejected/unfilled 等可复盘状态
- [x] 碎仓清理开关：可选自动卖出低权重历史遗留仓位（避免长期留存碎仓污染组合）
- [x] 交易时段控制：默认仅 RTH 下单（盘前盘后仅生成计划），可通过开关允许 outsideRth
- [x] 告警自动熔断：阈值触发后可选写入 kill_switch.lock 并落盘原因，防止系统在异常状态下继续运行
- [x] Prompt/模型版本留痕增强：在 decision/snapshot 中保存 prompt_version、model_endpoint、raw_response、validator_warnings，补齐完整审计链路
- [x] 市场日历与节假日感知：识别美股休市、半日市、夏令时切换，避免把 closed day 误记为 rth_blocked 或执行异常
- [x] 风险暴露约束：增加行业/主题/高相关性上限，避免股票池扩容后仍然集中在同一类科技风险上
- [x] Dashboard 基础鉴权：为 `/api/*` 增加最小 token 鉴权与只读保护，避免后续远程访问时裸露审计/日志/账本
- [x] 回测可信度升级：扩展回测窗口、明确状态演化与成本口径，减少“展示型回测”与真实运行之间的落差

## P1｜稳定性与可观测性

- [x] 网络层统一超时与重试（tenacity 或等价方案）
- [x] 外部数据源失败的负缓存（短 TTL）避免反复触发限流
- [x] 错误分级与告警（事件落盘到 events/ 与 alerts/）
- [x] 日志分级与结构化（关键字段：date, broker, source, strategy_ids, turnover, cash_ratio）
- [x] 日志滚动与归档（按天/按大小），避免单文件无限增长
- [x] 关键指标统计：LLM 调用次数、失败率、平均耗时；数据源成功率；当日换手率分布
- [x] 简单可视化图表：从 metrics 生成 HTML/SVG 折线图与柱状图（llm_sec/total_sec/turnover/status）
- [x] 本地 Dashboard：Python API + 前端页面展示资金曲线、持仓、策略、执行回报、对账、告警与日志
- [x] 告警渠道与阈值策略：连续失败计数 + 冷却时间，触发时写 alerts 并可选 webhook 通知
- [x] Webhook 告警增强：推送 payload 附带近期 alerts 摘要，便于手机端快速定位问题
- [ ] Dashboard 日期回放与多日对比：支持按日期查看历史 decision/rag/ledger，并对比持仓变化、策略变化与资金曲线
- [x] 无人值守调度与心跳：定时运行 daily agent、补充运行心跳与每日摘要通知，降低人工盯盘成本
- [x] Kill switch 状态中心：用结构化 state 文件记录触发原因/时间/恢复条件，并在 Dashboard 顶部明确展示当前熔断状态
- [x] 交易成本观测：统计佣金、滑点、取消率与未成交率，帮助区分“策略问题”和“执行问题”
- [ ] 数据源健康面板：展示 provider budget/cooldown/last_success/last_error/实际命中链路，缩短外部数据故障排障时间
- [ ] 执行生命周期分析：细化 `submitted_no_report`、`partial`、超时撤单、拒单原因和成交时延，形成更完整的执行质量画像
- [x] 调度与运行锁增强：增加单实例运行锁、重复触发保护、失败重入策略与健康检查，降低无人值守运行风险
- [x] 核心回归测试补齐：覆盖 PortfolioManager、reconcile_execution、Dashboard token 鉴权等关键路径，降低后续迭代回归风险
- [x] 仓库入口收敛：将教学/旧原型脚本迁移到 `examples/` 或 `legacy/`，主入口聚焦 `run_agent.py` / `run_llm_backtest.py`

## P2｜能力扩展

- [ ] 向量库 RAG：文档切片 + embedding + 相似度检索（ChromaDB/FAISS）
- [ ] 证据溯源：evidence 增加 chunk_id/url/timestamp，并在 README 展示审计示例
- [ ] 更多数据源：公告/财报电话会摘要/宏观日历（保持分层与优先级）
- [ ] 测试体系：pytest（优先覆盖 PortfolioManager 风控规则与 LLM 校验器）
- [ ] 集成测试：从“检索→LLM→风控→下单（Mock）→对账”全链路
- [ ] CI：lint + type-check + pytest
- [ ] 编排器分层重构：将 `MacroQuantAgent` 按 planning / execution / persistence / ops 拆成更清晰的 service，降低主编排器复杂度
- [ ] 状态存储抽象与数据库迁移：先为 `snapshots` / `ledger` / `metrics` / `runtime` 建立统一 store 接口，再评估 SQLite / Postgres 落地
- [ ] 调度与监控体系升级：在现有轻量 scheduler 之外，引入更正式的任务调度、失败恢复与外部监控接入能力
- [x] 收益归因与复盘：拆分收益来源（仓位变化、计划现金占比、执行质量、估算滑点、现金拖累），用于评估 LLM 决策质量
- [ ] 多策略集成：让系统同时产出趋势/事件/防守等子策略，再由上层做加权或投票，减少单一 Prompt 风险

## 下一阶段建议（基于 Code-Wiki）

1. 先完成 `P1` 中最贴近现有闭环的缺口：`Dashboard 日期回放与多日对比`、`交易成本观测`、`执行生命周期分析`。这三项能直接提升复盘与排障效率，也是当前 Dashboard / ledger / metrics 产物最值得继续挖深的方向。
2. 紧接着补 `集成测试` 与 `CI`。当前单元测试基础已经不错，但主链路仍缺少“检索 -> LLM -> 风控 -> Mock 执行 -> 对账”的自动化回归，以及 lint / type-check 的质量闸门。
3. 然后做 `数据源健康面板` 与 `调度与运行锁增强`。`Code-Wiki` 明确指出外部数据源稳定性和单机无人值守运行仍是薄弱点，这两项能优先降低真实运行中的运维成本。
4. 中期进入架构治理：推进 `编排器分层重构`，把 `MacroQuantAgent` 的职责拆薄；同时做 `状态存储抽象与数据库迁移`，先解耦接口，再考虑 SQLite / Postgres，而不是直接替换文件产物。
5. 最后再扩能力边界：`向量库 RAG`、`更多数据源`、`多策略集成`。这些能增强策略表达力，但优先级应低于稳定性、审计和执行质量建设。

## 完成记录

- 2026-04-28：新增 [validator.py](file:///Users/gxyy/Documents/isolation/llm/validator.py)，对 LLM 输出的 allocations/策略 id/evidence 做硬校验与清洗；实盘校验失败自动暂停调仓，回测模式失败降级等权。
- 2026-04-28：在 [config.py](file:///Users/gxyy/Documents/isolation/config.py) 增加 MAX_HOLDINGS / MIN_POSITION_WEIGHT / MAX_TOP3_SUM，并在 [validator.py](file:///Users/gxyy/Documents/isolation/llm/validator.py) 自动应用组合构建约束：过滤碎仓、保留 TopN、限制 Top3 集中度。
- 2026-04-28：新增 [snapshot_db.py](file:///Users/gxyy/Documents/isolation/data/snapshot_db.py)，将每日 RAG 输入与决策结果落盘到 `snapshots/`（带 created_at 时间戳）。
- 2026-04-28：新增碎仓清理配置 `AUTO_LIQUIDATE_DUST` / `DUST_MAX_WEIGHT`（[config.py](file:///Users/gxyy/Documents/isolation/config.py)），并在 [portfolio.py](file:///Users/gxyy/Documents/isolation/execution/portfolio.py) 在死区规则下对低权重且目标为 0 的持仓可选触发强制卖出。
- 2026-04-28：在 [agent.py](file:///Users/gxyy/Documents/isolation/core/agent.py) 中落盘 `rag_YYYY-MM-DD.json` 与 `decision_YYYY-MM-DD.json`，用于复盘与审计。
- 2026-04-28：在 [run_llm_backtest.py](file:///Users/gxyy/Documents/isolation/run_llm_backtest.py) 中按日期加载 RAG 快照，缺失时使用中性占位文本，避免回测复用“今天的数据”导致未来函数。
- 2026-04-28：增强 [broker.py](file:///Users/gxyy/Documents/isolation/execution/broker.py) 的 IBKR 下单流程：跟踪订单状态、识别部分成交/取消/拒单；超时未完成订单自动尝试取消；返回结构化订单执行结果。
- 2026-04-28：新增 [ledger.py](file:///Users/gxyy/Documents/isolation/execution/ledger.py) 与 [reconcile.py](file:///Users/gxyy/Documents/isolation/execution/reconcile.py)，将订单、成交回报、账户前后快照与对账结果落盘到 `ledger/execution_YYYY-MM-DD.json`；并在 [agent.py](file:///Users/gxyy/Documents/isolation/core/agent.py) 中根据成交回报与券商账户快照进行对账校验。
- 2026-04-28：在 [volcengine.py](file:///Users/gxyy/Documents/isolation/llm/volcengine.py) 增加“校验失败自动重问一次”的纠错闭环；若二次仍不合规则在实盘模式下返回 invalid 并由系统暂停调仓（保守策略）。
- 2026-04-28：增强 [cache.py](file:///Users/gxyy/Documents/isolation/data/cache.py) 支持 TTL 缓存，并在 [retriever.py](file:///Users/gxyy/Documents/isolation/data/retriever.py) 对新闻/宏观/市场/基本面添加失败负缓存（短 TTL），避免频繁重试触发限流。
- 2026-04-28：新增 [retry.py](file:///Users/gxyy/Documents/isolation/utils/retry.py) 并引入 `tenacity`；为外部请求统一加超时与指数退避重试（Alpha Vantage 请求、yfinance 下载与 info 拉取），降低偶发网络抖动导致的失败。
- 2026-04-28：新增 [events.py](file:///Users/gxyy/Documents/isolation/utils/events.py)，对数据源/LLM/券商/Agent 的关键异常进行分类并落盘到 `events/events.jsonl`；严重级别同时写入 `alerts/alerts.jsonl`，用于后续接入通知渠道。
- 2026-04-28：新增 [structlog.py](file:///Users/gxyy/Documents/isolation/utils/structlog.py) 输出结构化 JSONL 日志到 `logs/structured.jsonl`；在 [agent.py](file:///Users/gxyy/Documents/isolation/core/agent.py) 写入关键字段（date/broker/cash_ratio/strategy_ids/turnover/reconciliation）。
- 2026-04-28：新增 [file_rotate.py](file:///Users/gxyy/Documents/isolation/utils/file_rotate.py)，并将 [logger.py](file:///Users/gxyy/Documents/isolation/utils/logger.py)、[structlog.py](file:///Users/gxyy/Documents/isolation/utils/structlog.py)、[events.py](file:///Users/gxyy/Documents/isolation/utils/events.py) 改为按大小滚动（RotatingFileHandler + JSONL 文件轮转）。可通过环境变量 `LOG_MAX_BYTES` 与 `LOG_BACKUP_COUNT` 控制阈值与保留份数。
- 2026-04-28：新增 [metrics.py](file:///Users/gxyy/Documents/isolation/utils/metrics.py) 将每次运行的关键指标写入 `metrics/metrics.jsonl`；新增 [generate_daily_report.py](file:///Users/gxyy/Documents/isolation/reports/generate_daily_report.py) 统计 LLM 成功率/耗时、换手率、运行耗时与数据源成功率并生成 `reports/daily_report_YYYY-MM-DD.md`。
- 2026-04-28：新增 [generate_charts.py](file:///Users/gxyy/Documents/isolation/reports/generate_charts.py)，从 `metrics/metrics.jsonl*` 生成 `reports/charts.html`（纯 HTML + SVG，无第三方绘图库）。
- 2026-04-28：新增 [dashboard server](file:///Users/gxyy/Documents/isolation/dashboard/server.py) 与前端静态页（[index.html](file:///Users/gxyy/Documents/isolation/dashboard/static/index.html)），提供 `/api/*` 读取本地 `snapshots/ledger/events/alerts/metrics/logs` 并渲染资金曲线、持仓、策略与执行详情。
- 2026-04-28：增强 [agent.py](file:///Users/gxyy/Documents/isolation/core/agent.py) 的决策落盘：根据成交回报统计 execution_summary，并将 `decision.status` 从 traded 改为 filled/partial/cancelled/rejected/unfilled；前端状态颜色同步适配。
- 2026-04-30：增强 [trading_hours.py](file:///Users/gxyy/Documents/isolation/utils/trading_hours.py) 为美股市场日历感知：识别周末、Good Friday、Juneteenth、感恩节等休市日，以及 Thanksgiving 后一天 / Christmas Eve / Independence Day Eve 等常见半日市；同步在 [agent.py](file:///Users/gxyy/Documents/isolation/core/agent.py) 区分 `market_closed` 与 `planning_only`，避免将休市误判为执行异常，并把市场状态写入 decision/metrics。
- 2026-04-30：增强 [volcengine.py](file:///Users/gxyy/Documents/isolation/llm/volcengine.py) 输出统一 `llm_audit` 审计信息，记录 prompt_version、model_endpoint、raw_response、修正尝试与 validator errors/warnings；并在 [agent.py](file:///Users/gxyy/Documents/isolation/core/agent.py) 落盘到 decision、在 Dashboard 前端展示，便于复盘具体是哪版 Prompt 和哪次原始输出来了当前策略。
- 2026-05-04：收紧默认运行模式，在 [config.py](file:///Users/gxyy/Documents/isolation/config.py) 将 `BROKER_TYPE` 默认值改为 `mock`，新增 `ENABLE_LIVE_TRADING` 显式开关；在 [agent.py](file:///Users/gxyy/Documents/isolation/core/agent.py) 增加提交守卫，未开启实盘时即使连接 `IBKRBroker` 也只落盘 `planning_only` 而不会提交订单，并补充 [test_runtime_guards.py](file:///Users/gxyy/Documents/isolation/tests/test_runtime_guards.py) 固化该安全约束。
- 2026-05-04：增强 [dashboard server](file:///Users/gxyy/Documents/isolation/dashboard/server.py) 支持 `DASHBOARD_TOKEN` 最小鉴权；当配置 token 时，`/api/*` 需通过 `Authorization: Bearer`、`X-Dashboard-Token` 或 `?token=` 访问。前端 [app.js](file:///Users/gxyy/Documents/isolation/dashboard/static/app.js) 同步支持从页面 URL 读取 token 并自动附带到 API 请求，便于本机访问同时为后续远程访问预留安全边界。
- 2026-05-04：补充第一批高价值回归测试：新增 [test_portfolio_manager.py](file:///Users/gxyy/Documents/isolation/tests/test_portfolio_manager.py) 覆盖单票上限、现金缓冲、死区过滤、碎仓清理与换手缩放；新增 [test_reconcile_execution.py](file:///Users/gxyy/Documents/isolation/tests/test_reconcile_execution.py) 覆盖执行对账一致/不一致/脏数据忽略；配合 [test_dashboard_auth.py](file:///Users/gxyy/Documents/isolation/tests/test_dashboard_auth.py) 与 [test_runtime_guards.py](file:///Users/gxyy/Documents/isolation/tests/test_runtime_guards.py) 形成第一批核心安全回归网。
- 2026-05-04：增强 [config.py](file:///Users/gxyy/Documents/isolation/config.py) 增加 `RISK_EXPOSURE_GROUP_CAPS`，并在 [validator.py](file:///Users/gxyy/Documents/isolation/llm/validator.py) 对平台股、AI 算力链和高波动成长组三类暴露做自动缩放；[policy.py](file:///Users/gxyy/Documents/isolation/policy.py) 同步把分组约束写入 Prompt，新增 [test_validator_risk_exposure.py](file:///Users/gxyy/Documents/isolation/tests/test_validator_risk_exposure.py) 固化该行为。
- 2026-05-04：增强 [run_llm_backtest.py](file:///Users/gxyy/Documents/isolation/run_llm_backtest.py) 支持 `BACKTEST_PRICE_PERIOD`、`BACKTEST_SAMPLE_DAYS`、`BACKTEST_ALLOW_SYNTHETIC_PRICES` 等配置，并新增回测可信度摘要输出到 `reports/llm_backtest_summary.md`，明确标记真实价格/模拟价格、快照覆盖率、缺失日期与可信度等级；新增 [test_backtest_summary.py](file:///Users/gxyy/Documents/isolation/tests/test_backtest_summary.py) 固化摘要判定逻辑。
- 2026-05-04：收敛仓库主入口，将根目录中的早期脚本 [main.py](file:///Users/gxyy/Documents/isolation/legacy/main.py)、[ib_trade.py](file:///Users/gxyy/Documents/isolation/legacy/ib_trade.py)、[ib_test.py](file:///Users/gxyy/Documents/isolation/legacy/ib_test.py)、[refactor.py](file:///Users/gxyy/Documents/isolation/legacy/refactor.py) 迁移到 `legacy/` 目录；[README.md](file:///Users/gxyy/Documents/isolation/README.md) 同步明确当前正式入口仅为 [run_agent.py](file:///Users/gxyy/Documents/isolation/run_agent.py) 与 [run_llm_backtest.py](file:///Users/gxyy/Documents/isolation/run_llm_backtest.py)。
- 2026-05-04：新增 [review.py](file:///Users/gxyy/Documents/isolation/utils/review.py) 统一生成轻量复盘与收益归因摘要，拆分目标现金占比、仓位变化、计划现金流、成交率、估算滑点和对账结果；[generate_daily_report.py](file:///Users/gxyy/Documents/isolation/reports/generate_daily_report.py) 将其写入日报，[dashboard/server.py](file:///Users/gxyy/Documents/isolation/dashboard/server.py) 新增 `/api/review`，前端 [index.html](file:///Users/gxyy/Documents/isolation/dashboard/static/index.html) / [app.js](file:///Users/gxyy/Documents/isolation/dashboard/static/app.js) 增加 Review 面板；新增 [test_day_review.py](file:///Users/gxyy/Documents/isolation/tests/test_day_review.py) 固化核心口径。
- 2026-05-04：新增 [heartbeat.py](file:///Users/gxyy/Documents/isolation/utils/heartbeat.py) 写入统一 `runtime/heartbeat.json` 运行状态文件，记录 `current` / `last_run` / `last_success` / `recent_runs` / `scheduler`；[agent.py](file:///Users/gxyy/Documents/isolation/core/agent.py) 在每次 daily run 前后自动更新心跳；新增 [run_scheduler.py](file:///Users/gxyy/Documents/isolation/run_scheduler.py) 作为轻量定时入口，支持按配置时间每日触发；[dashboard/server.py](file:///Users/gxyy/Documents/isolation/dashboard/server.py) 增加 `/api/heartbeat`，前端 [index.html](file:///Users/gxyy/Documents/isolation/dashboard/static/index.html) / [app.js](file:///Users/gxyy/Documents/isolation/dashboard/static/app.js) 增加 Runtime 面板；新增 [test_heartbeat_scheduler.py](file:///Users/gxyy/Documents/isolation/tests/test_heartbeat_scheduler.py) 固化心跳与调度时间逻辑。
- 2026-05-04：新增 [kill_switch.py](file:///Users/gxyy/Documents/isolation/utils/kill_switch.py) 作为结构化熔断状态中心，将锁状态写入 `runtime/kill_switch.json`，统一记录 `reason` / `source` / `triggered_at` / `recovery_hint` / `history`；[agent.py](file:///Users/gxyy/Documents/isolation/core/agent.py) 的检查与触发逻辑改为通过该状态中心驱动，同时保留 `kill_switch.lock` 兼容层；[dashboard/server.py](file:///Users/gxyy/Documents/isolation/dashboard/server.py) 在 `/api/heartbeat` 返回完整 kill switch 详情，前端 [app.js](file:///Users/gxyy/Documents/isolation/dashboard/static/app.js) 在 Runtime 面板展示触发原因、来源、时间与恢复提示；新增 [test_kill_switch_state.py](file:///Users/gxyy/Documents/isolation/tests/test_kill_switch_state.py) 固化状态读写与兼容逻辑。
- 2026-05-09：新增 [run_lock.py](file:///Users/gxyy/Documents/isolation/utils/run_lock.py) 作为 daily agent 的单实例运行锁，默认写入 `runtime/agent_run.lock`；[run_agent.py](file:///Users/gxyy/Documents/isolation/run_agent.py) 在启动前统一获取运行锁，遇到并发启动时返回 `already_running`，遇到陈旧锁时自动恢复；[heartbeat.py](file:///Users/gxyy/Documents/isolation/utils/heartbeat.py) 新增 `recover_stale_current()` 用于清理异常残留的 `current=running`；[run_scheduler.py](file:///Users/gxyy/Documents/isolation/run_scheduler.py) 在调度触发时识别并记录“已有实例运行中”的阻塞状态，避免重复拉起；新增 [test_run_lock.py](file:///Users/gxyy/Documents/isolation/tests/test_run_lock.py) 覆盖并发拦截和陈旧锁恢复。
- 2026-05-09：继续收敛 [run_scheduler.py](file:///Users/gxyy/Documents/isolation/run_scheduler.py) 的失败重入语义：新增 `is_already_running_result()` 与 `resolve_last_run_date()`，把“锁冲突跳过”视作当天已触发、把“真实异常失败”保留为当天可重试；补充 [test_heartbeat_scheduler.py](file:///Users/gxyy/Documents/isolation/tests/test_heartbeat_scheduler.py) 固化这两个边界条件。
- 2026-05-09：继续修复运行守卫边界：增强 [run_scheduler.py](file:///Users/gxyy/Documents/isolation/run_scheduler.py) 对残留 `heartbeat.current=running` 的陈旧检测，发现死进程或超时陈旧状态时自动调用 [heartbeat.py](file:///Users/gxyy/Documents/isolation/utils/heartbeat.py) 的恢复逻辑，避免 scheduler 被永久阻塞；同时修正 [run_lock.py](file:///Users/gxyy/Documents/isolation/utils/run_lock.py) 的 TTL 语义，同机且 PID 仍存活时不再因锁年龄过大误判为陈旧锁；补充 [test_heartbeat_scheduler.py](file:///Users/gxyy/Documents/isolation/tests/test_heartbeat_scheduler.py) 与 [test_run_lock.py](file:///Users/gxyy/Documents/isolation/tests/test_run_lock.py) 覆盖这两个边界。
- 2026-05-09：增强 [broker.py](file:///Users/gxyy/Documents/isolation/execution/broker.py) 在执行回报中统一附带 `commission` 字段，`IBKRBroker` 聚合成交佣金、`MockBroker` 明确返回 `0.0`；增强 [review.py](file:///Users/gxyy/Documents/isolation/utils/review.py) 输出 `requested_notional`、`filled_notional`、`fill_notional_ratio`、`estimated_slippage_bps`、`reported_commission_total`、`reported_commission_bps` 与 `missed_notional`；前端 [app.js](file:///Users/gxyy/Documents/isolation/dashboard/static/app.js) 的 `Execution Quality` 卡片同步展示这些指标；日报 [generate_daily_report.py](file:///Users/gxyy/Documents/isolation/reports/generate_daily_report.py) 追加成本口径；补充 [test_day_review.py](file:///Users/gxyy/Documents/isolation/tests/test_day_review.py) 固化佣金与名义成交额相关统计。
- 2026-05-09：增强 [broker.py](file:///Users/gxyy/Documents/isolation/execution/broker.py) 为执行回报补充 `submitted_at`、`completed_at`、`elapsed_sec`、`timeout_cancel_requested`、`status_detail` 与 `status_history`，并在超时撤单场景保留生命周期信号；增强 [review.py](file:///Users/gxyy/Documents/isolation/utils/review.py) 输出 `timeout_cancel_requested_count`、`partial_terminal_count`、`avg_elapsed_sec`、`max_elapsed_sec` 与 `status_detail_breakdown`；前端 [app.js](file:///Users/gxyy/Documents/isolation/dashboard/static/app.js) 的 `Lifecycle Summary` 卡片同步展示超时撤单率、时延与细分状态；日报 [generate_daily_report.py](file:///Users/gxyy/Documents/isolation/reports/generate_daily_report.py) 追加生命周期摘要；补充 [test_day_review.py](file:///Users/gxyy/Documents/isolation/tests/test_day_review.py) 固化时延与超时撤单口径。
