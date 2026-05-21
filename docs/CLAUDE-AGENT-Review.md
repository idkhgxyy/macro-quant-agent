# CLAUDE.md 与 AGENT.md 评价报告

## 整体印象

这两个文件的质量非常高，是目前见过写得最好的 AI Agent 操作指南之一。它们采用了**分层设计**——`AGENT.md` 作为通用仓库指南，`CLAUDE.md` 作为 Claude 特定的操作层——这种架构非常合理，职责清晰。

---

## 一、CLAUDE.md 评价

### 优点

1. **"Think in Layers" 设计精妙**
   - 要求 Claude 在接任务时先分类到具体层面（planning / retrieval / execution / runtime guards / dashboard），然后只操作最小相关层。这是一种非常有效的**上下文窗口节省策略**。

2. **Good/Bad Changes 对比**
   - 用具体正反例子说明什么叫好的变更、什么叫坏的变更，比如"混在一起改 planning + execution + dashboard"是坏例子。这种方式比抽象的说教有效得多。

3. **安全硬规则（Hard Safety Rules）**
   - 6 条不可触碰的红线非常具体、可操作。加上改动执行代码前的 **4 个自问清单**，是非常好的安全兜底机制。

4. **按任务类型的推荐阅读路径**
   - 针对 LLM 输出问题、交易行为问题、provider 故障、dashboard 问题、backtest 问题分别列出了该读哪些文件。这让 Agent 能快速定位，减少盲目搜索。

5. **Output Expectations**
   - 规定了汇报工作时必须包含：改了什么、改了哪些文件、如何验证、残留风险。这对于代码审查和团队协作非常友好。

6. **文档职责边界清晰**
   - 明确声明：通用规则放 `AGENT.md`，Claude 专属规则放这里。避免了"该放哪"的困惑。

### 不足

1. **缺少 Claude 特定优化策略**
   - 没有利用 Claude 的特性，比如 XML 标签使用习惯、思考链提示风格等。对于 Claude 这个特定的 AI，可以加入一些针对性的交互优化。

2. **"Start From the Active Path" 的文件列表静态维护**
   - 硬编码了 8 个文件路径，如果项目重构或文件拆分，这个列表会过期。可以考虑指向 AGENT.md 的核心执行路径来避免重复维护。

3. **可以与 AGENT.md 进一步去重**
   - Verification Checklist 中的命令、Recommended Read Order 等内容在 AGENT.md 中也有类似出现。虽然少量重复可以容忍，但多了会导致两边不一致。

---

## 二、AGENT.md 评价

### 优点

1. **结构极其完整**
   - 从项目概述 → 核心路径 → 仓库映射 → 行为模型(状态机) → 持久化文件清单 → 变更规则 → 安全约束 → 任务路由 → 测试指南，覆盖了 AI Agent 需要的**所有信息**，没有明显的遗漏。

2. **行为模型（Behavioral Model）—— 10步状态机**
   - 用 10 步状态机描述系统运行流程是**非常精彩的设计**。比起长篇大论的架构说明，状态机让 Agent 能清晰地理解每一步的先后关系和决策点。附带的状态枚举（market_closed / no_trade / filled 等）也很实用，并明确警告不要随意重命名。

3. **Module-Level Docstring 规则**
   - 这是最有洞察力的设计之一。考虑到代码的主要读者是 AI Agent（而非人类），强制要求每个 `.py` 文件在行 1 加模块级 docstring，帮助 Agent 快速判断是否需要读取该文件。这是一个**将"为 AI 设计"落到实处**的规则。

4. **持久化文件清单 + 修改注意事项**
   - 列出了 18 个重要的本地文件，并明确要求：改了这些文件要去查 producers、dashboard readers、report generators、和 tests。这对于避免"改了 A 炸了 B"的连锁反应非常有效。

5. **Planning vs Execution 分离原则**
   - 明确指出 planning 逻辑归属 `llm/*`、execution 逻辑归属 `execution/*`、dashboard 是只读的。这种明确的责任边界有助于 Agent 做正确的局部修改。

6. **文档层次指引**
   - 告诉 Agent 应该按 `AGENT.md → docs/Code-Wiki.md → 源代码` 的顺序查阅，并且要求：如果发现文档与代码不符，更新文档。形成了**文档即代码**的闭环。

### 不足

1. **文件较长（约 370 行）**
   - 每次 Agent 启动都要读入这么长的文件，会消耗上下文窗口。可以考虑将一些静态内容（如完整的仓库地图、文件路径清单）拆分到 `docs/` 中。

2. **缺少环境依赖说明**
   - 没有明确说明 Python 版本要求、关键依赖的版本范围等。如果项目升级依赖导致不兼容，Agent 可能无法自行判断。

3. **没有标准化的贡献流程**
   - 比如"如何添加一个新策略"、"如何接入一个新的数据 Provider"、"如何添加一个 Dashboard 页面"——这些常见的扩展任务没有一个标准的步骤指南。如果写了这些，Agent 在完成这类任务时会更有章法。

4. **"Small Changes" vs "Reviewable Increments" 的表述存在张力**
   - 两条规则看起来有些矛盾（Prefer Small, Traceable Changes vs Prefer Reviewable Increments, Not Artificially Tiny Slices），虽然正文中的解释澄清了意图（不要大到跨层，不要小到无意义），但标题本身容易让人困惑。

---

## 三、总结对比

| 维度 | CLAUDE.md | AGENT.md |
|------|-----------|----------|
| 覆盖面 | Claude 操作习惯 + 安全规则 | 完整仓库指南 |
| 可操作性 | 极强（正反例+自问清单） | 很强（状态机+文件清单） |
| 创新性 | 任务分类引导 | Module-Level Docstring 规则 |
| 维护成本 | 中（静态文件列表会过时） | 低（结构稳定） |
| 对 AI 友好度 | 高 | 极高 |
| 去重情况 | 部分内容与 AGENT.md 重叠 | 部分内容与 CLAUDE.md 重叠 |

**最令人印象深刻的设计**：`AGENT.md` 中的 Module-Level Docstring 规则和 10 步状态机——这表明作者深刻理解 AI Agent 工作方式的特殊性（短暂的上下文窗口、文件级别的选择决策等），并为之做了针对性设计。这种"为 AI 设计"的思维在当前开源项目中非常少见，值得借鉴。

**最值得改进的地方**：补充标准化的扩展流程（如添加策略/Provider 的 checklist），以及进一步减少两文件之间的内容重复，降低维护负担。
