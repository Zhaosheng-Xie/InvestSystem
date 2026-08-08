# Stage 4 / 4A-4 市场预期、估值与退出规则包 v0.1

文档状态：`draft_for_owner_approval`

阶段：`Stage 4 / 4A-4`

覆盖规则：`FR-GATE-004`、`FR-GATE-005`、`FR-EXIT-001`

拟议批准范围：`stage4_synthetic_research_validation`

当前权限：`仅供 owner 审阅；无 runtime capability；不授权 backtest、paper、shadow、live、仓位或订单`

上游已批准依赖：`4A-1 context/industry v0.1.0；4A-2 event semantics v0.1.0；4A-3 gate/profit/scenario v0.1.0`

## 1. 目的

本包把 Stage 4 最后三项 P0 规则收敛为二十四项可逐项批准的精确决策：

- `FR-GATE-004`：在 E4 首次公开前重建公开经济预期，并把“经济信息意外”与“价格是否已经反映”分开；
- `FR-GATE-005`：把基础业务价值与 E4 有限期增量自由现金流分开估值，在显式合成价格与摩擦假设下判断剩余收益和赔率；
- `FR-EXIT-001`：形成 evidence/risk/time/value 四类策略退出判断、重新承保和 proof window 语义。

本文只是一份待批准规格。只有 owner 明确批准第 10 节全部二十四项后，才可另行生成 approved machine bundle、approval record 和相应 evaluator。本文、配套 draft machine proposal 及其校验代码均不得被当作已批准业务规则或运行能力。

## 2. 依据、裁决与阶段边界

本提案依据：

- PRD v0.3 第 11、13、14、17 节；
- Stage 4 完整 P0 清单中的 `FR-GATE-004/005` 与 `FR-EXIT-001`；
- 4A-3 已批准的 Gate 固定顺序、四情景、利润桥、Decimal、PIT、短路和审计语义；
- Stage 2B 已批准窄规则仅作为候选基线，不继承其 capability；
- 研究审计关于“研究论点与股票论点分离”“价格与可成交性不可被研究分数代替”的裁决。

本包作出五项关键裁决：

1. Gate 3 拆成 `public_economic_expectation_class` 与 `market_pricing_state`；前者回答公开经济信息是否意外，后者用区间反推判断价格是否已容纳该价值。两者都满足才能 PASS。
2. 公告前异常收益和成交量是必留的 PIT 上下文及冲突检查材料，但在没有校准阈值前不能单独制造 `unexpected`、`fully_priced` 或 PASS。
3. `0.15` 净基准剩余收益、`2.00` 基准/下行赔率和 `120` 个交易日作为新的 Stage 4 合成研究假设提交批准，不从 Stage 2B 自动继承。
4. Stage 4 只接受显式的匿名合成价格、成本、滑点、交易日计数和风险预算快照；它不实现首次实际可成交价、市场规则、账本、仓位、订单或 P&L。
5. 4A-4 获批后可以在精确合成 scope 内产生 `TRADE_READY` 或 `EXIT_CANDIDATE` 研究标签，但所有权重、approver、position 和 order 字段仍为空或零；标签不是运行模式和资金权限。

以下继续属于 Stage 5，而不是本包：

- 首次实际可成交价格发现、盘后/盘中可用时点、VWAP、T+1、涨跌停、停牌、一手和公司行动；
- 真实费用、滑点、冲击、容量和连续不可成交规则；
- 风险预算生成、组合/持仓/订单/成交/P&L 账本和可成交退出；
- 真实交易日历的维护及 elapsed trading days 的计算；
- backtest、paper、shadow、live 或资金部署。

## 3. 公共输入、结果与失败语义

### 3.1 固定身份与数值口径

所有输入和派生结果继续服从 4A-1—4A-3：

- 金额、价格、数量、比例、折现率和计算结果只使用十进制定点数；
- 同一估值集固定 `currency`、`unit`、`as_of`、税率、少数股东、归属比例和完全稀释股数口径；
- Fact/Assumption/Derived/Judgment/Audit 分层，依赖只能沿已批准方向；
- 每个集合保存 `id`、`version`、canonical hash、`supersedes`、`knowledge_cutoff` 和来源 ID；
- 未来信息、静默换算、隐藏默认值、hash/版本漂移、跨 run 隐式继承或 KB 写回均为 `BLOCKED`；
- 合法材料缺失、冲突或区间不可比较为 `ABSTAIN`，不得把未知当零、假或行业均值。

### 3.2 Gate 3 与 Gate 4 结果

沿用 4A-3 的 Gate 契约：

```text
evaluation_state = evaluated | not_evaluated
outcome = PASS | REJECT | ABSTAIN | BLOCKED | SHADOW_ONLY | null
reason_codes
fact_ids / assumption_ids / derived_ids
rule_id / rule_version / rule_hash
as_of
```

Gate 顺序仍为 Gate 1 → Gate 2 → Gate 3 → Gate 4。前一门非 `PASS` 时后一门为 `not_evaluated`；为 Gate 3 计算共享估值区间不等于 Gate 4 已被评估。

### 3.3 策略退出判断

退出使用独立结果，不与事件状态、Gate 结果或持仓状态混写：

```text
evaluation_state = evaluated | not_evaluated | blocked
disposition = HOLD | REUNDERWRITE_REQUIRED | EXIT_CANDIDATE | NOT_APPLICABLE | null
trigger_states = confirmed | refuted | unknown | not_applicable
confirmed_trigger_ids
reason_codes
rule_id / rule_version / rule_hash
as_of
```

`EXIT_CANDIDATE` 只表示策略判断；不得生成卖单、目标权重、成交记录或 P&L。结构/权限/hash/PIT 硬失败时 `evaluation_state=blocked` 且 `disposition=null`；已确认的触发器只能作为审计材料保留，不得伪造已执行退出。

## 4. FR-GATE-004：市场预期重建

### 4.1 E4 前预期快照

`ExpectationSnapshot` 必须在 `e4_first_public_at` 前冻结，并至少保存：

```text
snapshot_id / version / hash / supersedes
as_of / knowledge_cutoff
event_identity
counterparty_scope / product_scope
currency / unit
anticipated_event_state = explicitly_absent | directional_nonbinding | binding_expected
binding_minimum_amount_or_quantity_interval
effective_period / delivery_and_acceptance_timing
material_conditions / cancellation_and_return_floor
expected_ntm_incremental_parent_profit_interval
expected_ntm_incremental_fcf_interval
source_fact_ids / assumption_ids / derived_ids
coverage_by_material_dimension
```

“没有检索到材料”不等于 `explicitly_absent`。`explicitly_absent` 必须有 E4 前公开材料明确否定事件、确认最低义务为零，或确认同一事件仍不具约束力。任何 `as_of` 或来源晚于 E4 均为未来信息硬失败。

只有相同 `event_identity`、主体、产品/服务、币种、单位、期间、义务口径、利润/FCF 口径和实质条件的快照才可比较。非关键字段可显式标记 `not_material`，但必须给出 reason code 和审计引用；系统不得自行忽略差异。

### 4.2 公告前市场上下文

`PreE4MarketContext` 必须结束于 E4 首次公开之前，并保存：

```text
context_id / version / hash
window_start_at / window_end_at
security_price_observation_ref
fully_diluted_shares_ref
benchmark_id / benchmark_return
security_return / relative_return
security_turnover / reference_turnover / relative_turnover
source_refs / method_id / method_version / method_hash
```

窗口、基准、复权、股数和成交量口径必须显式给出。4A-4 不批准通用异常收益或异常成交量阈值，因此这些字段只用于 PIT 审计、反例复盘和未来校准，不能以涨跌幅或放量单独改变分类。缺失合法市场上下文时 Gate 3 为 `unknown → ABSTAIN`；E4 后价格和成交量禁止回填该快照。

### 4.3 价格反推状态

使用 E4 前最后一个合格市场价格观察、完全稀释股数、基础业务价值区间和 E4 基准事件增量 FCF 现值区间：

```text
pre_e4_market_cap = pre_e4_price * fully_diluted_shares

market_implied_event_value_interval.lower
  = pre_e4_market_cap - base_business_equity_value_interval.upper

market_implied_event_value_interval.upper
  = pre_e4_market_cap - base_business_equity_value_interval.lower
```

价格反推结果固定为：

| 条件 | `market_pricing_state` |
|---|---|
| `implied.lower >= event_value_interval.upper` | `fully_reflected` |
| `implied.upper < event_value_interval.lower` | `not_fully_reflected` |
| 两区间重叠、任一区间不可可靠建立或口径不可比 | `indeterminate` |

不得把负的隐含事件价值截断为零，不得选择单点、上下界或估值方法以追求 PASS。估值区间由第 5 节建立；共享预计算必须保留依赖图，不改变 Gate 固定评估顺序。

### 4.4 经济预期分类

以 4A-3 Gate 2 已确认的 E4 基准 NTM 增量归母标准化利润/FCF 区间与先验快照严格比较：

| 条件 | `public_economic_expectation_class` |
|---|---|
| 先验为 `explicitly_absent`，E4 产生正的绑定最低义务且基准增量利润、FCF 下界均大于零 | `unexpected` |
| 先验已预期同一事件；E4 基准增量利润下界严格大于先验利润上界，且 E4 基准 FCF 区间的上下界分别不低于先验 FCF 区间对应端点 | `partially_priced` |
| E4 基准增量利润上界不高于先验利润上界，或实际经济结果低于先验 | `fully_priced`，reason 说明“无正预期差/负预期差” |
| 区间重叠、跨维度有利/不利不可排序、材料不完整/冲突、事件不可比或先验仅为 `directional_nonbinding` 且无法量化 | `unknown` |

客户、期限、金额或条款的新颖性只有在它改变绑定最低义务、基准增量利润或基准增量 FCF 区间时才能形成经济意外；叙事变化本身不能 PASS。

### 4.5 Gate 3 聚合

| 条件 | Gate 3 |
|---|---|
| 治理、PIT、hash、单位、依赖图或未来信息硬失败 | `BLOCKED` |
| `market_pricing_state=fully_reflected` | `REJECT`，最终分类为 `fully_priced` |
| 经济分类为 `fully_priced` | `REJECT` |
| 任一状态为 `unknown/indeterminate`，或合法材料缺失/冲突 | `ABSTAIN` |
| 经济分类为 `unexpected` 或 `partially_priced`，且价格状态为 `not_fully_reflected` | `PASS` |

公告后上涨不能反证公告前已定价，但必须进入 Gate 4 的当前合成价格假设。任何加权分数、热度、研报数量或概率都不能补偿 Gate 3。

## 5. FR-GATE-005：基础价值、事件价值与 Gate 4

### 5.1 基础业务价值

`BaseBusinessValuation` 必须排除目标 E4 及其衍生收入、利润、现金流、复购和估值溢价，并至少保存：

```text
valuation_id / version / hash / supersedes
as_of / knowledge_cutoff
method_id / method_version / method_hash
normalized_earnings_or_cash_flow_inputs
explicit_multiple_or_discount_inputs
base_business_equity_value_interval
currency / unit / tax / minority / ownership / fully_diluted_shares
fact_ids / assumption_ids / derived_ids
sensitivity_and_falsifiers
```

允许使用显式版本化的标准化盈利倍数、有限期 DCF 或 EPV 类方法，但同一情景集只能声明一个主方法；其他方法只作交叉检查。倍数、折现率、长期增长、净债务、股数和任何调整项必须显式提供来源/假设与区间，本包不设置行业默认值。基础业务区间不可可靠建立时为 `ABSTAIN`；静默选用最有利方法、重复纳入 E4 或 hash/口径漂移为 `BLOCKED`。

### 5.2 E4 有限期增量 FCF 现值

每个情景按相同期间、币种、折现日和公式计算：

```text
event_finite_life_incremental_fcf_present_value
  = sum(period_incremental_fcf_t / discount_factor_t)

scenario_equity_value
  = base_business_equity_value
  + event_finite_life_incremental_fcf_present_value
```

其中：

- 期间 FCF 来自 4A-3 已批准利润/FCF 桥及其有限期延伸；
- NTM 以后只有最低义务、金额、期限和执行条件均有公开约束力的现金流才能进入 base/downside；
- 单次订单和未公开约束的复购、扩产、份额或涨价不得使用终值或永续增长；
- 无约束复购只能进入 upside，出现新的公开绑定事实时必须新建估值版本；
- 折现因子、时间分数和折现率曲线必须显式、正值、同币种并可重放；
- 概念热度、无依据倍数扩张和概率加权值不能替代 base/downside 准入。

### 5.3 防重复计价与区间一致性

每个收入、成本、营运资本、资本开支、税费、净债务和股数调整都必须登记唯一 `valuation_component_id`、期间、主体、产品/合同范围和 `base_business | event_incremental` 归属。相同经济现金流不得同时进入基础业务、事件 FCF、“新业务估值”或多个情景组件。

四情景价值区间按对应端点逐端弱排序：

```text
upside_value_interval.lower >= base_value_interval.lower
upside_value_interval.upper >= base_value_interval.upper
base_value_interval.lower >= downside_value_interval.lower
base_value_interval.upper >= downside_value_interval.upper
downside_value_interval.lower >= stress_value_interval.lower
downside_value_interval.upper >= stress_value_interval.upper
```

区间内部必须 `lower <= upper`。重复组件、区间反转、同一现金流多次归属或计算图循环为 `BLOCKED`；合法组件缺失或来源冲突为 `ABSTAIN`。

### 5.4 Stage 4 合成价格边界

4A-4 只接受 `SyntheticResearchPriceAssumption`：

```text
price_assumption_id / version / hash
as_of / knowledge_cutoff
price / fully_diluted_shares
explicit_cost_rate / explicit_slippage_rate
currency / unit
synthetic = true
not_first_actual_executable_price = true
source_fixture_ref
```

上述值只用于验证公式和状态路径，必须逐项显式提供，价格与股数严格大于零，成本/滑点非负。本包不发现、选择或声称该价格可成交。任何真实输入、非合成标识、隐藏默认摩擦或把该值命名为首次实际可成交价均为 `BLOCKED`。Stage 5 将来提供真实可成交观察后必须重新运行 Gate 3/4，不得继承合成结论。

### 5.5 Gate 4 公式与阈值提案

```text
synthetic_market_cap = synthetic_price * fully_diluted_shares
explicit_friction_rate = explicit_cost_rate + explicit_slippage_rate

gate4_base_value = base_scenario_equity_value_interval.lower
gate4_downside_value = downside_scenario_equity_value_interval.lower

net_base_remaining_return
  = gate4_base_value / synthetic_market_cap
  - 1
  - explicit_friction_rate

net_downside_return
  = gate4_downside_value / synthetic_market_cap
  - 1
  - explicit_friction_rate

downside_loss = abs(min(0, net_downside_return))
reward_to_downside = net_base_remaining_return / downside_loss
```

提议在精确 `stage4_synthetic_research_validation` scope 内批准：

- `net_base_remaining_return >= 0.15`；
- `reward_to_downside >= 2.00`；
- `downside_loss > 0`；等于零时不输出无穷赔率，而是 `ABSTAIN`；
- base/downside/upside/stress 价值及全部公式输入完整；
- 只有 upside 达标时为 `REJECT`；概率加权达标不能补偿 base/downside；
- 至少预登记两个可观察 falsifier 和一个下一个公开验证点；验证点距 E4 不超过 `120` 个交易日。

`0.15`、`2.00` 和 `120` 都是本次提交 owner 决定的新假设，不具有历史有效性证明。

### 5.6 Gate 4 与完整合成决策

| 条件 | Gate 4 |
|---|---|
| 治理、hash、单位、计算图、合成身份或依赖硬失败 | `BLOCKED` |
| 合法估值、价格、摩擦、下行损失、falsifier 或验证点缺失/冲突 | `ABSTAIN` |
| 验证点超过 120 日、任一阈值未达或只有 upside 达标 | `REJECT` |
| 第 5.5 节全部条件满足 | `PASS` |

四门均 PASS 时，完整 Stage 4 合成引擎可产生：

```text
decision_state = TRADE_READY
validation_only = true
position_state = FLAT
target_weight = null
approved_weight = null
actual_weight = null
approver = null
order_intent = null
execution_basis = synthetic_research_assumption_not_actual_executable
```

该标签只证明精确规则路径可达。Stage 4 capability 仍必须等 14 项 P0 全部 approved、完整 machine bundle、完整集成和验收后另行签发；局部 4A-4 批准本身不能签发完整 capability。

## 6. FR-EXIT-001：四类退出与重新承保

### 6.1 适用性与输入

Stage 4 不拥有仓位。退出判断只允许两类输入：

- `no_position`：输出 `NOT_APPLICABLE`，不得伪造持仓或退出；
- 明确标记的 `SyntheticHoldingSnapshot`：只用于合成研究验证，保存 snapshot ID/version/hash、建立时规则/估值/风险预算引用、当前时点和零执行权限。

将来真实持仓快照、市场价格、交易日计数和账户损失必须由 Stage 5 的批准契约提供。4A-4 不读取 Stage 5 SQLite/账本，也不反向修改其状态。

### 6.2 `evidence_exit`

以下任一项被合格 PIT 证据确认即触发 `EXIT_CANDIDATE`：

- 合同/订单取消或最低义务被实质清零；
- 关键验收失败；
- 延期越过原登记的利润桥或 proof-window 最晚日期；
- 价格、数量或绑定金额被实质下调，使当前 Gate 2/4 不再通过；
- 客户信用恶化，使回款、坏账或履约假设失效；
- 利润桥任一承重关系被反事实证据推翻。

每个触发器必须预先登记 `trigger_id`、可观察条件、评估窗口、来源类型、对应利润/估值组件和 `confirmed/refuted/unknown` 判定规则。新自由文本理由不得事后变成触发器；合法证据缺失或冲突为 `unknown`。

### 6.3 `risk_budget_exit`

```text
risk_budget_exit = current_actual_loss_amount >= registered_account_loss_budget_amount
```

等号触发。两者必须来自同一币种、同一持仓身份和不可变 snapshot；损失预算必须是建立 synthetic holding 时登记的原值，价格下跌后不得扩大。4A-4 只比较 Stage 5 风格的显式合成快照，不生成风险预算、不估计成交损失，也不下单。适用时缺失/冲突为 `ABSTAIN`，无仓位为 `not_applicable`。

### 6.4 `time_exit`

```text
time_exit = elapsed_trading_days >= 120
            AND preregistered_verification_event_not_confirmed
```

等号触发。`elapsed_trading_days` 必须由显式 calendar ID/version/hash 的外部观察提供，4A-4 不自行维护交易日历。初始验证事件 ID、可观察条件和截止日不得原地替换；旧验证点失败后临时换催化点仍触发退出。若新事实足以形成新论点，必须先结束旧版本，再以新的事件/估值/decision 版本重新承保。

### 6.5 `value_exit`

```text
current_base_value_for_exit = current_base_scenario_equity_value_interval.lower
value_exit = current_market_cap >= current_base_value_for_exit
             AND no_approved_e5_or_e6_evidence_increases_current_value
```

等号触发。市场价格上涨不能自动提高价值；价格下跌不能放松 Gate 1—3。存在合格 E5/E6 新证据时，不得直接把旧估值调高，应先输出 `REUNDERWRITE_REQUIRED`，建立新的 append-only 利润桥和估值版本并重新运行相关 Gate。新证据未知或冲突不能阻止已确认的 value exit。

### 6.6 重新承保与聚合

“如果现在没有仓位，是否会在当前价格重新买入？”被操作化为：使用当前 PIT 证据、当前版本化估值和显式价格重新运行适用 Gate；不得由自由文本 `yes/no` 覆盖结果。

聚合顺序固定为：

1. 权限、hash、PIT、单位、依赖或结构硬失败 → `blocked/null`；
2. 任一可信触发器 `confirmed` → `evaluated/EXIT_CANDIDATE`，未知的其他触发器不能抵消它；
3. 无 confirmed，但任一适用触发器 `unknown` → `evaluated/null`，原因码为 `ABSTAIN`；
4. 无 confirmed/unknown，但有估值相关新证据尚未重新承保 → `evaluated/REUNDERWRITE_REQUIRED`；
5. 全部适用触发器 refuted 且重新承保仍通过 → `evaluated/HOLD`；
6. 无仓位 → `evaluated/NOT_APPLICABLE`。

所有结果 append-only；规则、事实、价格、估值、proof window 或持仓快照变化都必须形成新版本并引用 `supersedes`。任何结果都不得写回 KB、改写历史材料或产生仓位/订单副作用。

## 7. 版本、迁移与审计

4A-4 的 `ExpectationSnapshot`、`PreE4MarketContext`、估值集、价格假设、proof window、退出触发器和退出结果均为 InvestSystem 自有策略制品。每个制品必须：

- 绑定唯一策略、事件、固定输入、`knowledge_cutoff` 和上游 4A-1—4A-3 结果；
- 保存规则 ID/version/hash、计算图、Fact/Assumption/Derived/Judgment 引用；
- append-only，修订使用新 ID/version/hash 和 `supersedes`；
- 在规则迁移时用固定输入重放；结果变化必须产生新 replay hash；
- 不读取或写入 KB SQLite、raw、staging、published 工作目录或内部实现；
- 不把合成 fixture、价格或退出判断冒充正式 KB Release 或真实市场事实。

历史规则下的结果只能按原规则审计重放，不得静默用新估值/退出规则重写旧 DecisionRecord。

## 8. 提议的测试与验收矩阵

获批后才允许实现下列测试；当前清单不表示测试或 evaluator 已存在：

| 类型 | 最低覆盖 |
|---|---|
| 正例 | `unexpected + not_fully_reflected + G4 PASS`；`partially_priced + G4 PASS`；四类 exit 各一项 confirmed |
| 反例 | `fully_reflected`；经济结果不超先验；收益/赔率/120 日任一不达标；只有 upside 达标 |
| 边界例 | 区间严格相离/刚好相接；`0.15`、`2.00`、`120` 等号；`downside_loss=0`；价值等号；风险预算等号 |
| `ABSTAIN` | 先验/市场上下文/价值区间不可建立；区间重叠；下行损失为零；适用退出快照缺失 |
| `BLOCKED` | 未来信息、hash/版本/单位漂移、重复计价、真实价格伪装合成、跨仓读取或权限漂移 |
| 确定性 | 同输入/规则/时钟得到相同分类、价值、退出判断和 replay hash；单字段变化改变 hash |
| 隔离 | Stage 2B capability、其他策略、真实 KB、Stage 5 账本和任何运行模式均不能加载本 draft |

## 9. 当前明确禁止实现或默认的内容

在第 10 节全部批准且 approved artifacts 另行形成前，代码不得实现或默认：

- Gate 3 分类、价格反推状态、异常收益/成交量阈值或完整 Gate 3 结果；
- 任一估值方法选择、倍数、折现率、长期增长、区间宽度、费用或滑点；
- `0.15`、`2.00`、`120` 在 Stage 4 的业务含义；
- Gate 4 evaluator、完整 Stage 4 `TRADE_READY` 或全引擎 capability；
- evidence/risk/time/value exit、重新承保、持仓读取、卖出意图或订单；
- 首次实际可成交价、交易日历、市场规则、风险预算、组合、账本或 P&L；
- 从 Stage 2B 规则、历史文档、PRD hypothesis、LLM 或行业经验推导任何默认值。

当前只允许校验：draft 身份、canonical hash、二十四项均为 pending、上游批准依赖精确、无 approval record、空运行模式和零交易权限。

## 10. 所有者逐项批准清单

以下二十四项当前全部为待批准；勾选框不得在没有 owner 明确批准的情况下修改：

### FR-GATE-004

- [ ] `4A4-APPROVAL-001`：批准 E4 前 append-only `ExpectationSnapshot` 的字段、PIT 和“未找到不等于明确为零”语义。
- [ ] `4A4-APPROVAL-002`：批准相同事件、主体、产品、币种、单位、期间、义务、利润/FCF 和实质条件的严格可比口径。
- [ ] `4A4-APPROVAL-003`：批准 `PreE4MarketContext` 必留但异常收益/成交量无校准阈值前不得单独改变分类，缺失为 `ABSTAIN`，E4 后信息不得回填。
- [ ] `4A4-APPROVAL-004`：批准以基础价值区间反推公告前隐含事件价值，以及 `fully_reflected/not_fully_reflected/indeterminate` 的严格区间关系。
- [ ] `4A4-APPROVAL-005`：批准 `unexpected` 仅限先验明确无绑定事件、而 E4 带来正的绑定义务及正的基准增量利润/FCF。
- [ ] `4A4-APPROVAL-006`：批准 `partially_priced/fully_priced/unknown` 的利润区间严格超越、FCF 区间逐端不劣、跨维度不可排序和叙事新颖性不得替代经济增量。
- [ ] `4A4-APPROVAL-007`：批准 Gate 3 聚合、短路、冲突/缺失/硬失败和禁止分数补偿的语义。

### FR-GATE-005

- [ ] `4A4-APPROVAL-008`：批准基础业务价值必须排除目标 E4，并固定 equity/currency/unit/tax/minority/ownership/fully-diluted-shares 口径。
- [ ] `4A4-APPROVAL-009`：批准版本化主估值方法、显式倍数/折现/长期增长/净债务/股数和无行业默认值；交叉方法不得择优替换主方法。
- [ ] `4A4-APPROVAL-010`：批准 E4 有限期增量 FCF 现值公式、显式折现因子及单次事件无终值/永续增长。
- [ ] `4A4-APPROVAL-011`：批准 NTM 后现金流只纳入公开绑定最低义务，无约束复购/扩产/份额/涨价只进入 upside。
- [ ] `4A4-APPROVAL-012`：批准 base/downside/upside/stress 价值区间的一致口径、上下界逐端顺序、缺失和失败语义。
- [ ] `4A4-APPROVAL-013`：批准 `valuation_component_id` 唯一归属和基础业务/事件现金流防重复计价图。
- [ ] `4A4-APPROVAL-014`：批准 Stage 4 只接受显式 `SyntheticResearchPriceAssumption`，且它不是首次实际可成交价；真实价格和摩擦机制仍归 Stage 5。
- [ ] `4A4-APPROVAL-015`：批准 Gate 4 固定使用 base/downside 价值区间下界，以及仅限 Stage 4 合成研究验证的 `0.15` 净基准收益、`2.00` 赔率、`downside_loss>0`、等号通过及只有 upside 达标为 `REJECT`。
- [ ] `4A4-APPROVAL-016`：批准两个 falsifier、一个不超过 `120` 交易日的预登记验证点、Gate 4 聚合及合成 `TRADE_READY` 始终 FLAT/零权限。

### FR-EXIT-001

- [ ] `4A4-APPROVAL-017`：批准退出是独立策略判断，输入仅为 `no_position` 或匿名 `SyntheticHoldingSnapshot`，输出不产生卖单、权重、成交或 P&L。
- [ ] `4A4-APPROVAL-018`：批准合同取消/义务清零、验收失败、越窗延期、价格数量下调、客户信用恶化和利润桥失效六类 evidence exit。
- [ ] `4A4-APPROVAL-019`：批准 risk-budget exit 只比较外部不可变快照，实际损失大于等于建仓时登记预算即触发，4A-4 不生成预算或账本。
- [ ] `4A4-APPROVAL-020`：批准 time exit 在 `elapsed_trading_days>=120` 且预登记验证事件未确认时触发，外部版本化交易日计数及禁止临时换催化点。
- [ ] `4A4-APPROVAL-021`：批准 current market cap 大于等于当前基准价值区间下界且无 E5/E6 价值提升证据时触发 value exit。
- [ ] `4A4-APPROVAL-022`：批准 E5/E6 新证据必须 append-only 重新承保，以当前 PIT 证据/价格重跑适用 Gate，涨跌本身不改价值或事实门槛。
- [ ] `4A4-APPROVAL-023`：批准 exit 的 `blocked → confirmed exit → unknown/ABSTAIN → reunderwrite → hold → not applicable` 聚合语义，未知不能抵消已确认触发器。
- [ ] `4A4-APPROVAL-024`：批准 4A-4 全部制品 append-only/version/hash/supersedes/replay、禁止 KB 写回及零 backtest/paper/shadow/live/仓位/订单权限。

## 11. 批准后的唯一授权边界

若 owner 批准全部二十四项，授权仍仅可为：

```text
scope = stage4_synthetic_research_validation
run_mode = research
validation_only = true
input = InvestSystem-owned anonymous synthetic fixture
runtime_capability = exact 4A-4 bundle only
full_stage4_capability = false until separate 14-rule integration approval
backtest = false
paper = false
shadow = false
live = false
positions = false
orders = false
```

批准不证明阈值、估值方法或退出规则具有历史有效性，也不得外推到真实 KB 输入、其他策略、其他版本或 Stage 5。任何修改都必须产生新版本、canonical hash 和新的 owner approval。
