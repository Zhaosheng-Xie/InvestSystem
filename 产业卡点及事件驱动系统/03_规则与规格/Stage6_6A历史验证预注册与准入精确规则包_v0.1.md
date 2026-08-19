# Stage 6 / 6A 历史验证预注册与准入精确规则包 v0.1

状态：`draft`

适用策略：`industrial_bottleneck_event`

目标 scope：`stage6_historical_validation_governance`

本文只形成 Stage 6 历史验证的预注册与准入治理草案。它不签发运行 capability，不下载数据，不确认 Release 当前状态，不写 InvestSystem 状态库，不执行回测，不计算策略表现，也不授权 paper、shadow、live、真实仓位、真实订单或资金部署。

## 1. 为什么 Stage 6 必须从预注册开始

Stage 3 已证明 InvestSystem 能通过固定公共契约消费真实 Published Release 与 Context Pack，但没有 current-status authority。Stage 5D-1 只证明第一条匿名合成 ENTER/BUY 订单合同事件能够被准确回放；它没有覆盖 SELL、公司行动、外部现金流或完整证券会计。

因此 Stage 6 不能把“能取数”和“单例能算账”解释为“可以正式回测”。在观察任何策略表现之前，必须先冻结：研究问题、输入范围、样本切分、竞争假设、支持矩阵、统计方法、通过线和失败处理。

PRD 中的 `30` 笔、置信区间下限、`15%` 最大回撤和最大盈利交易占比等数值仍是 `hypothesis`。本草案保留它们作为待 owner 决定的候选，不把它们变成实现默认值。

## 2. Stage 6 的阶段拆分

| 子阶段 | 目标 | 当前状态 | 进入下一阶段的门 |
| --- | --- | --- | --- |
| 6A | 冻结历史验证预注册、准入、样本、统计和失败合同 | `draft_governance_only` | owner 原子批准精确规则包与 machine bundle |
| 6B | 实现 historical-validation admission、run-scoped Release 状态确认和 IS 自有原子运行留存 | `not_authorized` | 只读 transport、状态证据、Receipt/Observation/Manifest 闭包和失败零写通过验收 |
| 6C | 在开发样本执行 golden、PIT replay、walk-forward、消融、参数邻域和压力测试 | `not_authorized` | 所有候选、拒绝、ABSTAIN、BLOCKED 和参数搜索完整留存；规则在 holdout 前冻结 |
| 6D | 一次性运行冻结 holdout，完成冠军挑战、偏差审计和正式报告 | `not_authorized` | owner 基于预注册判定 `go / revise / stop / insufficient_evidence` |

6A 的批准不能替代 6B—6D 的实现与验收。6B 的运行准入不能替代 6C/6D 的统计结论。6D 的历史结果不能替代 Stage 7 前瞻 shadow/paper 证据。

## 3. 精确上游与隔离边界

### 3.1 上游身份

6A machine draft 必须绑定：

- 当前 PLAN 与产业 PRD v0.3 的原始字节 SHA-256；
- Stage 3D 正式 Context Pack 验收记录及其 `authority_eligible=false` 边界；
- Stage 5D 第一条订单合同回放预注册与受限验收记录；
- Stage 5D bounded replay 实现基线提交 `caf1e6702e2653e61c668508d32eb4f7c8f27783`；
- Stage 5A/5C 历史制品保持不变，受限 Stage 5D 支持矩阵不得被预注册文本扩张。

任一依赖身份漂移都必须重新形成预注册版本，不能沿用旧批准。

### 3.2 跨仓边界

InvestSystem 只消费 KB 的固定公共契约与不可变 Published Release。禁止读取 KB SQLite、`raw/`、`staging/`、`published/`、工作树源码或内部 Python 包；禁止共享可写缓存、数据库或迁移。

### 3.3 策略隔离

产业事件与题材轮动必须保持不同的 `strategy_id`、输入引用、Manifest、候选全集、参数搜索、账本、P&L 和验证结论。Stage 6A 不授权信号互通，也不允许用题材结果补产业策略样本。

## 4. 预注册对象与冻结时点

正式预注册对象 `HistoricalValidationPreregistration` 至少包含：

- `preregistration_id`、版本和 canonical hash；
- 精确规则、代码提交、锁文件和 semantic config hash；
- 数据总体、日历范围、证券范围和纳入/排除规则；
- 决策时点、label horizon、最大持有期、purge 和 embargo；
- development / walk-forward / frozen holdout 的精确边界；
- 主估计量、次要指标、风险指标、基线、竞争模型和统计方法；
- Stage 5D 支持矩阵、事件 closed world 和未支持输入的处理；
- 样本充分性、通过线、停止线和 `insufficient_evidence` 条件；
- 随机种子、重采样单位、多重检验族和调整方法；
- owner 批准记录与批准时间。

冻结时点必须早于任何本次候选策略表现、walk-forward 汇总或 holdout 结果的读取。冻结后任何承重字段变化都创建新版本并使旧 holdout 资格失效。

## 5. 样本、时间与信息集

### 5.1 研究单位

首版研究单位定义为一个在 PIT 条件下形成的 `event × listed_company × decision_time` 机会。相同经济事件、公司或风险簇产生的多条观测不是独立样本；统计重采样必须使用预注册的聚类单位，禁止把重复公告或同一订单拆成独立胜率。

### 5.2 候选全集

候选登记先于策略门判断。全集必须保留 `TRADE_READY`、`SHADOW_ONLY`、`REJECT`、`ABSTAIN`、`BLOCKED` 和无成交结果。不得只登记成功事件、可成交标的或最终持仓。

### 5.3 PIT

每个事实、规则、价格、市场状态、财务值、公司行动和 Release 状态只能在其 `available_at <= decision_time` 时使用。修订、撤回和更正按实际可得时点追加，不得回写历史知识。

### 5.4 样本切分

样本只按时间前进切分。development 与 frozen holdout 不得随机混合；purge 至少覆盖 label overlap，embargo 至少覆盖预注册的最大信息泄漏窗口。精确日期、比例、最短窗口和最小有效样本量均保持 owner 待决定，未填写时 6B—6D 必须失败关闭。

### 5.5 holdout

holdout 身份必须内容寻址、一次冻结、一次打开。任何在 holdout 结果可见后发生的规则、特征、门槛、样本、成本或支持矩阵变化，都只能进入新一轮研究，不能重跑同一 holdout 后择优报告。

## 6. historical-validation admission

首个正式历史 run 前，6B 必须独立实现并验收：

1. 使用已认证 transport 获取精确 Release、Manifest、Status 与制品；
2. 从本次新鲜状态证据签发 run-scoped `RunReleaseStatusConfirmation`；
3. 验证 Published、未撤回、Schema 兼容、Manifest/hash chain 和完整引用闭包；
4. 将原始状态证据、Receipt、Observations、StrategyRunManifest、预注册和 Release 闭包原子写入 InvestSystem 自有状态层；
5. 任一检查失败时策略 evaluator 调用为零、状态写入为零；
6. 撤回或无法确认的 Release 阻止新 run，历史材料仅可 `audit_replay`；
7. 每个 run 只允许一个 `strategy_input_ref`。

Stage 3D 的 validation-only 对象不能直接升级成确认；Stage 7 也不得复用 Stage 6 的历史确认作为当前 shadow/paper authority。

## 7. Stage 5D 支持矩阵门

每次预注册必须在查看表现前固定会计和执行支持矩阵。当前基线只支持第一条匿名合成 ENTER/BUY bounded replay，不足以覆盖正式历史总体。

正式样本遇到未支持的 SELL、公司行动、外部现金流、特殊结算、成本或 mark 场景时：

- 在任何 partial NAV/P&L 发布前返回 `BLOCKED` 或 `ABSTAIN`；
- 保留在候选全集和 coverage 报告中；
- 不得静默删除、事后补实现后只重跑失败样本，或把失败视为零收益；
- coverage 本身是完成门。若预注册最低 coverage 未满足，整轮结论只能是 `insufficient_evidence`。

扩大 Stage 5D 支持范围必须独立实现、验收并形成新的 Stage 6 预注册版本。

## 8. 竞争假设与冠军挑战

必须至少包含：

1. `H0_no_independent_alpha`：结果可由市场、行业、风格、偶然性或研究偏差解释；
2. `no_trade`：不承担策略风险的零交易基线；
3. `market_or_industry_matched`：与候选在可观测风险暴露上匹配的基准；
4. `simple_e4_only`：只使用最小 E4 公开事实、固定持有和统一执行的简单模型；
5. `simple_valuation_threshold`：只使用预注册价值/赔率门的简单模型；
6. `full_system`：使用完整 E0—E7、四道门、利润桥、估值、执行和风险链。

所有模型必须共享同一候选总体、PIT 信息集、可成交约束、成本、持有期定义和风险预算。完整系统只在 frozen holdout 稳定优于“最佳简单竞争模型”时保留额外复杂度；不能只与指数比较。

## 9. 指标、统计与通过线

### 9.1 指标层级

主估计量应为预注册 horizon 内、扣除费用/税/滑点/冲击后、相对预注册基准的组合级增量收益或 P&L，且能回溯到逐机会 contribution。具体 horizon 与标准化方式待 owner 决定。

必须同时报告：绝对与基准超额收益、覆盖率、ABSTAIN/BLOCKED 率、成交率、容量、回撤、尾部损失、最大赢家贡献、风险簇集中度、换手和成本敏感性。风险过滤器和执行优势单独归因，不得冒充 Alpha。

### 9.2 不确定性

置信区间和重采样必须按预注册的事件/公司/风险簇及时间依赖结构进行，不能把交易逐笔视为独立同分布。随机种子、重采样次数和统计实现版本在 holdout 前冻结。

### 9.3 多重检验

全部竞争假设、参数组合、特征、消融和指标族必须进入搜索台账。确认性结论使用预注册的 family 与调整方法；未登记探索只能标为 `exploratory`，不得作为通过依据。

### 9.4 数值门槛

PRD 候选门槛只作为 owner 待决定输入：

- 最少独立交易数候选：`30`；
- 扣费后平均期望收益候选：`> 0`；
- 聚类重采样 `95%` 置信区间下限候选：`> 0`；
- 样本外最大回撤候选：`<= 15%`；
- 最大盈利交易占总净利润候选：`<= 25%`。

这些值在 owner 原子批准前均为 `hypothesis`，不得进入 evaluator。还必须另行决定：完整系统相对最佳简单模型的最小实质增量、coverage 下限、有效样本下限、成本/容量压力情景和失败容忍度。

## 10. 参数、消融与偏差审计

- 参数搜索空间、顺序、停止规则和全部结果完整登记；
- 只在 development/walk-forward 内选择参数，holdout 禁止调参；
- 对 E0—E7、四道门、利润桥、估值、退出、风险和执行层分别消融；
- 在预注册邻域测试参数稳定性，单点尖峰不得作为稳定证据；
- 压力测试费用、税、滑点、冲击、容量、延迟、跳空、停牌、涨跌停和不可成交；
- 审计幸存者偏差、前视偏差、重复事件、选择性纳入、不可成交偏差和研究者自由度；
- 最大赢家、单一公司、单一风险簇或单一时期主导时必须单独披露。

## 11. 结果状态与留存

Stage 6 结果状态限定为：

- `PASS`：所有预注册门同时满足；
- `FAIL`：至少一个确认性门明确失败；
- `INSUFFICIENT_EVIDENCE`：样本、coverage、PIT、支持矩阵或统计稳定性不足；
- `PRECHECK_BLOCKED`：身份、准入、Schema、Release 状态、Manifest 或权限失败；
- `AUDIT_REPLAY_ONLY`：仅重放已冻结历史材料，不产生新结论。

所有 run、候选、拒绝、ABSTAIN、BLOCKED、错误、搜索和报告均 append-only 留存。失败 run 不能被成功重跑覆盖；规则、代码、配置、预注册、数据和随机种子必须进入 deterministic replay identity。

## 12. 6A 完成门

6A 只有在以下条件同时满足时才可关闭：

- owner 原子批准第 13 节全部项目；
- 形成独立 approved machine bundle、approval record 和只限历史验证治理/准入的 capability；
- 原始规格与 draft machine proposal 保持不可变；
- 没有 backtest evaluator、历史表现、Release confirmation、状态写入或交易权限被提前实现；
- 6B—6D 仍各自保留独立实现和验收门。

## 13. Owner 逐项批准清单

- [ ] `6A-01`：批准 Stage 6 拆分为 6A 预注册治理、6B 准入与原子留存、6C development/walk-forward、6D frozen holdout 冠军挑战，任何前一阶段批准不得替代后一阶段验收。
- [ ] `6A-02`：批准本包只形成 `stage6_historical_validation_governance` 草案，当前 allowed run modes 为空，不签发 runtime capability，不执行 backtest/paper/shadow/live。
- [ ] `6A-03`：批准精确绑定 PLAN、PRD v0.3、Stage 3D 验收、Stage 5D 预注册/验收和 `caf1e67` 实现基线；任一承重身份漂移必须形成新版本。
- [ ] `6A-04`：批准 KB/IS 隔离与产业/题材零信号互通边界，禁止 KB 内部读取、共享写存储或跨策略样本/P&L 混用。
- [ ] `6A-05`：批准完整 `HistoricalValidationPreregistration` 内容寻址，并要求冻结时点早于任何本次表现结果读取。
- [ ] `6A-06`：批准研究单位为 PIT `event × listed_company × decision_time` 机会，重复公告、同一经济事件、公司和风险簇不得冒充独立样本。
- [ ] `6A-07`：批准先登记候选全集，再运行策略门；保留 TRADE_READY、SHADOW_ONLY、REJECT、ABSTAIN、BLOCKED 和无成交结果。
- [ ] `6A-08`：批准所有事实、价格、财务、市场规则、Release 状态、修订与更正按实际 `available_at` 进入 PIT 信息集，禁止回写。
- [ ] `6A-09`：批准只按时间前进切分 development、walk-forward 和 frozen holdout，并使用覆盖 label overlap 的 purge 与预注册 embargo。
- [ ] `6A-10`：批准样本日期、切分比例、purge、embargo、horizon 和最小样本量都是 owner 必填项；缺任一项 6B—6D 失败关闭。
- [ ] `6A-11`：批准 holdout 内容寻址、一次冻结、一次打开；结果可见后的规则、特征、门槛、样本、成本或支持矩阵变化只能进入新预注册版本。
- [ ] `6A-12`：批准 6B 使用本次新鲜公共状态证据签发 run-scoped `RunReleaseStatusConfirmation`，不得复用 Stage 3D validation-only 对象或 Stage 7 authority。
- [ ] `6A-13`：批准 6B 原子固定原始状态证据、Receipt、Observations、StrategyRunManifest、预注册和完整 Release 闭包；任一失败 evaluator 零调用且状态零写。
- [ ] `6A-14`：批准撤回或无法确认的 Release 阻止新 run，历史材料仅允许 `audit_replay`，且每个 run 只允许一个 `strategy_input_ref`。
- [ ] `6A-15`：批准每轮在看表现前固定 Stage 5D 支持矩阵和事件 closed world，当前单一 ENTER/BUY bounded replay 不足以授权正式历史总体。
- [ ] `6A-16`：批准未支持会计/执行输入必须保留为 BLOCKED/ABSTAIN，禁止静默剔除、事后择样扩展或发布 partial NAV/P&L。
- [ ] `6A-17`：批准 coverage 是正式完成门；低于 owner 冻结下限时整轮只能 `INSUFFICIENT_EVIDENCE`。
- [ ] `6A-18`：批准零假设、no-trade、风险匹配基准、simple E4、simple valuation 和 full system 为首版冠军挑战 closed world。
- [ ] `6A-19`：批准所有竞争模型共享候选总体、PIT、执行、成本、持有期和风险预算，完整系统必须稳定优于最佳简单模型才保留复杂度。
- [ ] `6A-20`：批准主估计量为扣除全部交易摩擦后的组合级基准增量结果，并要求逐机会 contribution 可追溯；精确 horizon/标准化待 owner 填写。
- [ ] `6A-21`：批准同时报告收益、coverage、ABSTAIN/BLOCKED、成交、容量、回撤、尾损、最大赢家、风险簇、换手和成本敏感性。
- [ ] `6A-22`：批准风险过滤器、发现工具与执行优势必须单独归因，未经竞争检验不得称为 Alpha 来源。
- [ ] `6A-23`：批准置信区间与重采样反映事件/公司/风险簇和时间依赖，随机种子、重采样次数及实现版本在 holdout 前冻结。
- [ ] `6A-24`：批准全部假设、参数、特征、消融和指标进入搜索台账；确认性结论使用预注册 multiple-testing family 与调整方法。
- [ ] `6A-25`：批准 PRD 的 `30`、`>0`、`95% CI lower >0`、`max drawdown <=15%`、`largest winner <=25%` 当前均为 hypothesis，owner 原子批准前不得进入 evaluator。
- [ ] `6A-26`：批准另行冻结 full-vs-best-simple 最小实质增量、coverage 下限、有效样本下限、成本/容量压力和失败容忍度。
- [ ] `6A-27`：批准参数搜索空间、顺序、停止规则和全部结果完整登记，holdout 禁止调参或择优重跑。
- [ ] `6A-28`：批准对 E0—E7、四道门、利润桥、估值、退出、风险和执行层做消融，并把参数邻域稳定性作为完成门。
- [ ] `6A-29`：批准交易费用、税、滑点、冲击、容量、延迟、跳空、停牌、涨跌停和不可成交压力测试。
- [ ] `6A-30`：批准幸存者、前视、重复事件、选择性纳入、不可成交和研究者自由度审计，并披露最大赢家/公司/风险簇/时期集中。
- [ ] `6A-31`：批准 Stage 6 结果状态 closed world 为 PASS、FAIL、INSUFFICIENT_EVIDENCE、PRECHECK_BLOCKED、AUDIT_REPLAY_ONLY。
- [ ] `6A-32`：批准 run、候选、拒绝、ABSTAIN、BLOCKED、错误、搜索和报告 append-only 留存，失败不得被成功重跑覆盖。
- [ ] `6A-33`：批准 deterministic replay identity 固定规则、代码、配置、预注册、数据、随机种子和完整输入闭包。
- [ ] `6A-34`：批准 6D 只按冻结预注册形成正式报告，并由 owner 作 `go / revise / stop / insufficient_evidence` 决策；历史结果不等于前瞻或 live 证据。
- [ ] `6A-35`：批准 6A 全部 35 项必须整包原子批准，部分批准不得签发 capability 或授权部分实现。

## 14. 批准后的唯一顺序

1. 保持本规格与 draft machine proposal 原始字节不可变；
2. 形成独立 approved bundle、approval record 和 6A 治理验收；
3. 另行形成 6B 精确输入/状态/事务规则与失败注入，再由 owner 授权实现；
4. 6B 完成后形成包含精确日期和数值门槛的正式 run preregistration；
5. 只在 6C development/walk-forward 完成并冻结所有规则后打开 6D holdout；
6. 6D 报告完成后由 owner 决定是否进入 Stage 7。

任一 pending 项、身份漂移、未填参数或验收失败都必须停止；不得直接进入历史执行。
