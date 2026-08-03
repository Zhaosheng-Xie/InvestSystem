# Stage 4 / 4A-3 四道门、利润分母与情景规则包 v0.1

文档状态：`draft_for_owner_approval`

阶段：`Stage 4 / 4A-3`

覆盖规则：`FR-GATE-001—003`

拟议批准范围：`stage4_synthetic_research_validation`

当前权限：`仅供 owner 审阅；无 runtime capability；不授权 backtest、paper、shadow、live、仓位或订单`

上游已批准依赖：`4A-1 context/industry v0.1.0；4A-2 event semantics v0.1.0`

## 1. 目的

本包把 Stage 4 的第三批规则收敛为二十项可逐项批准的精确决策：

- `FR-GATE-001`：四道门的固定顺序、Gate 1/2 输入映射、短路和局部完成边界；
- `FR-GATE-002`：E4 前反事实 NTM 标准化归母利润分母、事件增量利润/FCF 桥和 Gate 2 结果；
- `FR-GATE-003`：基准、下行、上行、压力四情景的一致性、概率和版本语义。

本包不批准 Gate 3 的预期分类、Gate 4 的估值/可成交收益、退出规则或完整 Stage 4 决策。它也不复用 Stage 2B 的 capability。只有 owner 明确批准第 9 节全部二十项后，才能另行生成 approved machine bundle、approval record 和局部 evaluator。

## 2. 依据与裁决

本提案依据：

- PRD v0.3 第 11—12 节；
- Stage 4 完整 P0 清单中的 `FR-GATE-001—003`；
- Stage 2B 已批准的窄规则仅作为候选基线，不获得 Stage 4 权限；
- 4A-1 的 `profit_beneficiary/four_gate_eligible` 结果；
- 4A-2 的 E4、主体/PIT、审计知识图和独立证据链结果；
- 原始框架关于 GPM、利润和证据的设想，以及研究审计对“GPM 不能代替利润与现金流桥”的裁决。

本包作出四项关键裁决：

1. `10%` 重新作为 Stage 4 合成研究假设提请批准，不从 Stage 2B 自动继承；
2. 不设置跨公司通用的“接近零金额”或净利率阈值；用 PIT 反事实利润区间是否严格排除零判定分母稳健性；
3. Gate 2 不只看利润重要性：基准 NTM 增量 FCF 必须为正，利润达标但 FCF 不为正时只能得到研究观察标签；
4. 4A-3 只完成 Gate 1—2；Gate 3—4 固定为 `not_evaluated`，不得产生 `TRADE_READY` 或完整 Stage 4 结论。

## 3. 公共类型和结果层级

### 3.1 数值与时间

- 所有货币值使用十进制定点数，禁止二进制浮点参与 canonical 计算；
- 同一情景集必须固定 `currency`、`unit`、`e4_first_public_at`、`knowledge_cutoff` 和 NTM 区间；
- NTM 区间定义为从 `e4_first_public_at` 所在日期开始的连续十二个月半开区间 `[anchor_date, anchor_date + 12 calendar months)`，按公司收入确认和财务报告口径投影；
- 任何 Fact 必须满足 `available_at <= e4_first_public_at <= knowledge_cutoff`；Assumption/Derived/Judgment 继续服从 4A-2 审计分层；
- 情景集使用上市公司财务列报币种；外币合同必须登记 PIT 汇率 Fact/Assumption、换算日期和汇率版本。合法汇率材料缺失为 `ABSTAIN`，口径/hash 漂移或静默换算为 `BLOCKED`。

### 3.2 Gate 结果

每个 Gate 同时保存：

```text
evaluation_state = evaluated | not_evaluated
outcome = PASS | REJECT | ABSTAIN | BLOCKED | SHADOW_ONLY | null
reason_codes
fact_ids
assumption_ids
derived_ids
rule_id / rule_version / rule_hash
as_of
```

`not_evaluated` 时 `outcome=null`，并必须有 `short_circuit_reason_code`。`SHADOW_ONLY` 只是研究结果标签，不授权 shadow 运行。

结果优先级固定为：

```text
BLOCKED > REJECT > ABSTAIN > SHADOW_ONLY > PASS
```

该优先级只用于聚合已经评估的结果，不能把未评估 Gate 伪造成失败，也不能让多个弱证据用分数补偿硬门。

## 4. FR-GATE-001：四道门顺序与局部完成边界

### 4.1 固定顺序

完整 Stage 4 的顺序固定为：

```text
治理与 capability
→ 4A-1 profit_beneficiary/four_gate_eligible
→ 4A-2 audit/party/E4/event-state
→ Gate 1 真实性
→ Gate 2 利润与现金流重要性
→ Gate 3 预期差（4A-4）
→ Gate 4 价值与可成交收益（4A-4）
→ 完整 Stage 4 结论
```

前一 Gate 非 `PASS` 时，后续 Gate 一律 `not_evaluated`。已有明确 `REJECT` 不因后续未运行而降为 `ABSTAIN`；未评估永远不等于通过。

### 4.2 Gate 1 输入映射

Gate 1 不重新解释 KB Fact，只组合精确批准的 4A-1/4A-2 结果：

| 条件 | Gate 1 |
|---|---|
| 输入/capability/hash/PIT/审计结构硬失败 | `BLOCKED` |
| 4A-1 明确不是 `profit_beneficiary`，或 4A-2 明确否定 E4 | `REJECT` |
| 当前只到 E3.5 且无硬失败 | `SHADOW_ONLY` |
| 4A-1/4A-2 关键结果未知、冲突或不可恢复 | `ABSTAIN` |
| 4A-1 `profit_beneficiary` 且 `four_gate_eligible`；4A-2 audit、party、E4、event-state 均 `PASS`；E4 已达到且两条独立公开证据链就绪 | `PASS` |

Gate 1 `PASS` 还必须至少包含一条权威原文证据链、两个不同责任发布者、两个不同 acquisition lineage。重复转述不能增加独立性。

### 4.3 Gate 2 与 4A-3 局部输出

Gate 2 只在 Gate 1 `PASS` 后运行，并由 `FR-GATE-002/003` 联合决定。若 Gate 2 `PASS`，4A-3 只可输出：

```text
gate2_research_qualified = true
remaining_gate_ids = [FR-GATE-004, FR-GATE-005]
full_stage4_decision = null
position_state = FLAT
target_weight = null
order_intent = null
```

Gate 3、Gate 4 在 4A-4 获批前固定为 `not_evaluated / RULE_BATCH_NOT_APPROVED`。4A-3 不得输出 `TRADE_READY`，也不得签发完整 Stage 4 capability。

## 5. FR-GATE-002：反事实 NTM 分母与 Gate 2

### 5.1 反事实定义

分母是 E4 首次公开时点的公司级反事实：假设目标事件没有发生，在随后连续十二个月中可归属于上市公司股东的标准化利润。

```text
counterfactual_ntm_normalized_parent_profit
  = recurring_operating_revenue
  - recurring_operating_cost
  - recurring_selling_expense
  - recurring_administrative_expense
  - recurring_research_expense
  - net_finance_cost
  - recurring_impairment_and_credit_losses
  + recurring_other_operating_income
  + recurring_investment_and_associate_income
  - normalized_income_tax
  - minority_interest_deduction
```

销售、管理、研发、经营成本、减值、税费和少数股东扣除以非负绝对额输入。`net_finance_cost` 使用有符号口径：正数表示净成本、负数表示净收益；原始报表符号到该口径的转换必须版本化并保留来源。事件桥中的 `incremental_financing_cost` 使用同一符号约定。

### 5.2 标准化和来源

分母必须：

- 由公司/分部驱动的 bottom-up bridge 建立；
- 排除目标 E4 的收入、成本、费用、税费和融资影响；
- 排除资产处置、与经营无关补贴、公允价值变动、债务重组、一次性税项、一次性减值转回等非经常项目；
- 对确属经常经营的其他收益保留明确 reason code 和支持 Fact；
- 以当时一致预期和 TTM 只作交叉验证，二者均不能替代 bottom-up bridge；
- 保存 bridge version、component Fact/Assumption、calculation input hash 和 result hash。

若声明的计算图实际包含目标事件或重复计价，属于确定性的结构错误，为 `BLOCKED`；若计算图设计正确，但合法材料不足以量化事件剔除额或其他分量，则为 `ABSTAIN`。

### 5.3 `standard_track` 与 `fragile_profit_shadow_track`

分母必须同时计算：

- `base_counterfactual_profit`；
- `downside_counterfactual_profit`；
- 由各关键假设预先登记的可支持区间传播得到的 `counterfactual_profit_interval=[lower, upper]`。

支持区间必须用同一版本公式做确定性区间算术传播：加项使用下界之和/上界之和，减项使用被减数下界减减项上界/被减数上界减减项下界；禁止从不同情景逐项挑选最有利端点。

仅当以下三项均严格大于零时进入 `standard_track`：

```text
base_counterfactual_profit > 0
downside_counterfactual_profit > 0
counterfactual_profit_interval.lower > 0
```

若 bridge 完整但任一值不大于零，则进入 `fragile_profit_shadow_track`，不得计算重要性比率，不得输出无穷或负分母比率。该规则用“支持区间是否排除零”替代跨公司固定金额或净利率阈值。若区间本身无法可靠建立，则为 `ABSTAIN`，不是 fragile 自动归类。

### 5.4 事件增量利润和 FCF

四个情景使用同一公式：

```text
ntm_incremental_parent_normalized_profit
  = ntm_recognizable_revenue
  - incremental_operating_cost
  - incremental_operating_expense
  - incremental_tax_and_surcharges
  - incremental_financing_cost
  - minority_interest_deduction

ntm_incremental_free_cash_flow
  = ntm_incremental_parent_normalized_profit
  + incremental_non_cash_items
  - incremental_working_capital
  - incremental_capex
```

`ntm_recognizable_revenue` 必须由有约束力义务、交付/验收节奏、净价格和收入确认口径推导。合同总额、收入占比、行业 ASP、历史综合毛利率、GPM 趋势或 LLM 估计均不能代替该桥。

### 5.5 重要性与结果

只在 `standard_track` 计算：

```text
profit_materiality
  = base.ntm_incremental_parent_normalized_profit
  / base_counterfactual_profit
```

候选门槛为精确十进制 `0.10`，等号通过。Gate 2 映射：

| 条件 | Gate 2 |
|---|---|
| 治理、hash、单位、时间、重复计价或计算图硬失败 | `BLOCKED` |
| 关键经济字段、bridge、区间或必需情景缺失/冲突 | `ABSTAIN` |
| 完整但基准重要性 `<0.10`，或只有上行情景达到 `0.10` | `REJECT` |
| `fragile_profit_shadow_track`，或利润达标但基准 NTM 增量 FCF `<=0` | `SHADOW_ONLY` |
| `standard_track`、基准重要性 `>=0.10`、基准 NTM 增量利润 `>0`、基准 NTM 增量 FCF `>0` 且四情景完整 | `PASS` |

概率加权、上行情景、GPM、市场热度或估值均不能把 Gate 2 的非 `PASS` 补偿为 `PASS`。

## 6. FR-GATE-003：四情景

### 6.1 必需情景

每个 case 必须有且仅有：

| 情景 | 精确定义 |
|---|---|
| `base` | E4 时点公开证据下最可能的执行路径；必须有 Judgment 和 reason code，不是上下行机械中点 |
| `downside` | 至少一个承重变量相对基准恶化，且有合同、历史或产业 Fact/Assumption 支持的合理不利路径 |
| `upside` | 至少一个承重变量相对基准改善，并登记可观察触发器；触发前不进入基准 |
| `stress` | 极端但现实的资本损失或流动性路径；至少包含取消/延期、价格/毛利、回款/营运资金、资本开支或融资中的一个压力驱动 |

压力情景不替代下行情景，也不参与 Gate 2 的概率加权。

### 6.2 统一驱动表

四情景共享一个版本化 driver schema，至少包括：

```text
binding_amount_or_quantity
net_unit_price
delivery_and_acceptance_timing
ntm_revenue_recognition
incremental_operating_cost_or_margin
incremental_operating_expense
tax_and_surcharges
financing_cost
minority_interest
non_cash_items
working_capital
capex
cash_collection_timing
fx_rate_and_translation_basis
```

每个 driver 保存 `source_fact_ids / assumption_id / as_of / value / unit / uncertainty_interval / trigger / falsifier`。未变化的 driver 必须显式继承基准，变化项必须给出因果理由；禁止为每个变量独立挑选最有利值。

### 6.3 经济一致性

- 四情景使用相同公式、NTM 区间、货币、单位、税/少数股东和所有权口径；
- `upside.ntm_incremental_parent_normalized_profit >= base >= downside`；
- 压力情景必须在 `增量利润更低 / 增量 FCF 更低 / 峰值外部融资需求更高 / 最低流动性余量更低 / 不可逆核销更高` 中至少一个指标严格劣于下行情景，并登记 `stress_severity_metric`；
- `upside/base/downside` 利润顺序不满足时为 `BLOCKED`；压力情景中其他指标表面改善时必须用版本化现金时点/取消路径 reason code 解释，否则为 `ABSTAIN`；
- 无约束复购、未来扩产、份额提升或价格上涨只能进入上行情景，直到新的公开约束事实使其成为后续版本的基准。

### 6.4 概率

概率默认可缺省。若任一 `base/downside/upside` 概率存在，则：

- 三者必须全部存在、互斥，并以精确十进制合计 `1.000000`；
- 必须保存校准样本、方法、版本和 `as_of`；
- `stress` 不分配概率；
- 概率加权值只作展示，不能替代基准重要性、正 FCF 或下行情景，也不能改变 Gate 2 结果。

缺少可靠校准时保持概率为空，不因此单独 `ABSTAIN`。

### 6.5 缺失、版本和重放

- 四情景、统一 driver schema、base/downside 的承重变量和所有 Gate 2 必需输出缺一项为 `ABSTAIN`；
- future、non-public、来源不明、跨 run 隐式引用、隐藏默认值或后见回填为 `BLOCKED`；
- 情景集只允许 append-only 新版本；修改必须产生新的 `scenario_set_id/version/hash` 和 supersedes；
- 固定输入和规则 bundle 迁移必须可重放，结果 hash 不一致或不可重放为 `BLOCKED`；
- 任何情景输出均不能写回 KB，也不能直接生成仓位或订单。

## 7. 失败关闭与测试要求

批准后，每项规则至少覆盖：

- 正例：Gate 1—2 均通过，四情景完整，但 Gate 3—4 仍未评估且无完整决策；
- 反例：E4 明确失败、重要性低于门槛、只有上行达标；
- 边界：`0.10` 等号、FCF 等于零、利润区间 lower 等于零、概率精确合计、情景单调等号；
- `ABSTAIN`：分母区间、交付/价格/毛利/回款或必需情景不可可靠建立；
- `SHADOW_ONLY`：fragile 分母或利润达标但基准 FCF 不为正；
- `BLOCKED`：未来信息、单位漂移、重复计价、隐藏默认、hash 漂移、非法依赖或不可重放；
- 属性测试：固定点十进制、顺序无关 canonical hash、概率和、情景关系、短路 evaluator 调用次数；
- replay：相同输入/规则/情景版本产生相同 Judgment、result hash 和短路记录。

测试不得读取 KB 工作树、SQLite、raw、staging、published 或内部包。正例必须使用 InvestSystem 自有、匿名、明确标记的 synthetic fixture。

## 8. 明确不包含

- Gate 3 `unexpected/partially_priced/fully_priced/unknown` 的完整语义；
- Gate 4 基础业务价值、事件 FCF 现值、首次可成交价格、净收益、赔率和 proof window；
- `FR-EXIT-001`；
- 完整 Stage 4 machine bundle、完整 DecisionState 或 `TRADE_READY`；
- KB transport/current-status/Context Pack smoke；
- backtest、paper、shadow、live、TargetPortfolio、仓位、订单、成交或 P&L。

## 9. Owner 批准项

以下二十项必须整体明确批准或逐项修改；普通“继续”不等于批准：

### FR-GATE-001

- [ ] `4A3-APPROVAL-001`：批准四道门固定顺序、前门非 PASS 后短路及“未评估不等于失败/通过”。
- [ ] `4A3-APPROVAL-002`：批准 Gate 1 只组合精确 4A-1/4A-2 结果，不重新解释或补写 KB Fact。
- [ ] `4A3-APPROVAL-003`：批准 Gate 1 的 `BLOCKED/REJECT/ABSTAIN/SHADOW_ONLY/PASS` 映射和两条独立证据链条件。
- [ ] `4A3-APPROVAL-004`：批准 GateResult 分离 `evaluation_state` 与 `outcome`，并固定结果优先级和 reason/evidence lineage。
- [ ] `4A3-APPROVAL-005`：批准 4A-3 只运行 Gate 1—2；Gate 3—4 固定未评估，禁止 `TRADE_READY` 和完整 Stage 4 capability。

### FR-GATE-002

- [ ] `4A3-APPROVAL-006`：批准从 E4 首次公开日开始的连续十二个月半开 NTM 区间、PIT 截面、列报币种/外汇换算、统一单位和固定点十进制。
- [ ] `4A3-APPROVAL-007`：批准公司级 bottom-up 反事实利润逐项公式、非负减项和有符号净财务成本口径；一致预期/TTM 只作交叉验证。
- [ ] `4A3-APPROVAL-008`：批准排除目标事件和非经常项目、禁止重复计价；计算图确定包含事件/重复计价为 `BLOCKED`，合法材料不足以量化剔除额为 `ABSTAIN`。
- [ ] `4A3-APPROVAL-009`：批准用确定性区间算术得到的 base/downside/支持区间 lower 均严格大于零定义 `standard_track`，不设跨公司固定“接近零”阈值。
- [ ] `4A3-APPROVAL-010`：批准完整但区间触零/跨零/为负进入 `fragile_profit_shadow_track`，不计算重要性比率；区间不可建立为 `ABSTAIN`。
- [ ] `4A3-APPROVAL-011`：批准事件 NTM 增量归母标准化利润与增量 FCF 的精确公式，并把融资成本纳入利润桥。
- [ ] `4A3-APPROVAL-012`：批准 `0.10` 作为仅限 Stage 4 合成研究验证的 Gate 2 候选阈值，等号通过、只有上行达标为 `REJECT`。
- [ ] `4A3-APPROVAL-013`：批准 Gate 2 PASS 还要求基准增量利润和 FCF 均严格大于零；利润达标但 FCF `<=0` 为研究标签 `SHADOW_ONLY`。

### FR-GATE-003

- [ ] `4A3-APPROVAL-014`：批准 base/downside/upside/stress 四情景必需且定义互不替代。
- [ ] `4A3-APPROVAL-015`：批准统一 driver schema、显式继承、变化项因果依据以及禁止逐变量挑选最有利值。
- [ ] `4A3-APPROVAL-016`：批准四情景公式/口径一致、upside/base/downside 利润顺序，以及压力情景至少一个指定资本风险指标严格恶化和其他表面改善的显式 reason code。
- [ ] `4A3-APPROVAL-017`：批准无约束复购、扩产、份额或涨价在新约束事实出现前只能进入上行情景。
- [ ] `4A3-APPROVAL-018`：批准情景概率默认可空；一旦使用，base/downside/upside 全有、合计 `1.000000`、有校准来源，stress 无概率且概率不得补偿 Gate。
- [ ] `4A3-APPROVAL-019`：批准四情景/必需 driver 缺失为 `ABSTAIN`，未来信息、隐藏默认、单位/hash/依赖硬失败为 `BLOCKED`。
- [ ] `4A3-APPROVAL-020`：批准情景集 append-only 版本、supersedes、固定输入迁移重放和零 KB 写回/零交易权限。

## 10. 批准后的唯一授权边界

若 owner 批准本包全部二十项，授权仍仅为：

```text
scope = stage4_synthetic_research_validation
run_mode = research
validation_only = true
input = InvestSystem-owned anonymous synthetic fixture
runtime_capability = exact 4A-3 bundle only
full_stage4_capability = false
backtest = false
paper = false
shadow = false
live = false
positions = false
orders = false
```

批准不得解释为阈值已具有历史有效性，也不得外推到真实 KB 输入或其他策略。任何修改都必须产生新版本、canonical hash 和新的 owner approval。
