# Stage 5 / 5A 成交、组合、账本与确定性回放精确规则包 v0.1

文档状态：`draft_for_owner_approval`

阶段：`Stage 5 / 5A rule governance`

覆盖需求：`FR-GATE-006`、`FR-RISK-001`、`FR-RISK-002`、`FR-RISK-003`、`FR-EXEC-001`、`FR-AUDIT-001`，以及 `FR-EXIT-001` 的执行投影

拟议批准范围：`stage5_synthetic_execution_validation`

当前权限：`仅供 owner 审阅；无 runtime capability；不授权 backtest、paper、shadow、live、真实仓位、真实账户、真实订单或券商接入`

上游拟固定依赖：`Stage 4 / 4B v0.1.0 complete synthetic engine；不继承其 capability`

## 1. 目的

本包把 Stage 4 的理论研究结论与 Stage 6 的正式历史验证之间，最容易产生后见偏差和账目漂移的一层收敛为四十项可逐项批准的精确决策：

- 什么时间开始具备成交候选资格，什么价格可以被称为首次可成交价格；
- 如何按历史有效的 A 股市场规则、交易日历、证券状态、最小申报单位和价格限制判断可成交性；
- 如何计算费用、税费、滑点、冲击、容量、部分成交和未成交；
- 如何从压力损失反推合成目标仓位，并执行单票、风险簇、现金、组合风险和回撤硬约束；
- 如何分离 `target / approved / submitted / filled / actual`，并用 append-only 双分录账本重建现金、持仓和 P&L；
- 如何处理 T+1、公司行动、复权、估值、对账、修订和 deterministic replay。

本文只是一份待批准规格。只有 owner 明确批准第 13 节全部四十项后，才可另行保留本 draft、生成 approved machine bundle 与 approval record，并进入 Stage 5B—5D 的合成实现。本文及配套 draft machine proposal 不得被当作已批准规则、可运行代码或资金权限。

## 2. 依据、证据地位与阶段边界

### 2.1 需求与上游规则

本提案依据：

- [PRD v0.3](../01_需求/产业卡点及事件驱动系统_PRD_v0.3.md)第 3、4、14—21、23 节；
- [4A-4 市场预期、估值与退出规则包](Stage4_4A4市场预期估值与退出规则包_v0.1.md)关于“真实首次可成交价、交易日历、风险预算和账本留给 Stage 5”的边界；
- [4B 完整引擎集成与合成验收规则包](Stage4_4B完整引擎集成与合成验收规则包_v0.1.md)及其已批准完整合成输出；
- [框架审计与研究结论](../02_研究/框架审计与研究结论_v0.1.md)关于“先算会亏多少”“执行优势不等于 Alpha”和“Agent 不拥有资金权限”的裁决；
- `原始文档/` 与 `归档/` 中的仓位、Kelly、成本和市场状态建议，仅作为候选设想与反例来源。

PRD 中的 `3 个交易日`、`5%` 容量、`0.5%` 单笔风险、`5%/10%` 仓位、`1.5%/20%/4%` 组合约束和 `8%/12%/15%` 回撤线均仍是 `hypothesis`。本包把它们作为只适用于拟议合成 scope 的明确候选提交 owner 决定；它们没有历史有效性证明，不得因写入草案而自动生效。

### 2.2 官方规则来源与时间版本

市场制度事实必须来自按生效日固定的官方材料，不能从本草案或历史归档中读取。当前核对入口包括：

- [上海证券交易所交易规则（2026 年修订）](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)，其页面同时声明生效日、废止关系和暂缓实施条文；
- [深圳证券交易所交易规则（2026 年修订）](https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf)；
- [证监会《证券市场程序化交易管理规定（试行）》](https://www.csrc.gov.cn/csrc/c100028/c7480577/content.shtml)；
- [财政部、税务总局关于减半征收证券交易印花税的公告](https://fgk.chinatax.gov.cn/zcfgk/c102416/c5211343/content.html)。

这些链接只证明规则来源类型和版本化必要性，不构成本包内置的完整历史规则表。Stage 5B 实现前必须把实际使用的官方规则字节、文号、生效区间、暂缓条文、证券板块和费用来源固定为 InvestSystem 自有、只读、内容寻址的 `MarketRuleSet`；运行时不得联网追随“最新规则”。本规格不构成法律、税务或券商操作意见。

### 2.3 本包的关键边界

本包拟议批准后仍只允许：

```text
scope = stage5_synthetic_execution_validation
run_mode = research
market_input = InvestSystem-owned anonymous synthetic fixture
account_input = InvestSystem-owned anonymous synthetic account fixture
stage4_input = exact Stage 4B synthetic result
runtime_side_effects = none
```

明确不包含：

- 真实 KB Release、KB current-status authority 或正式 `StrategyRunManifest`；
- 真实行情下载、真实券商行情、账户、资产、持仓、委托、成交或对账单；
- backtest、paper、shadow、live、自动交易、程序化交易报告或券商接入；
- 策略有效性、费用模型准确性、容量可扩展性或收益证明；
- 题材策略信号、组合、账本、成交或 P&L；两个策略继续零信号互通、零账本互通。

## 3. 上游身份、输入合同与结果状态

### 3.1 精确上游身份

任何未来 Stage 5 合成 capability 必须独立固定：

| 对象 | 固定身份 |
|---|---|
| Stage 4B bundle SHA-256 | `ba8886cf85beef084c2a2d3b83446b499c7786fbc3f0e56066fb8cedc8e27e77` |
| Stage 4B rules SHA-256 | `3477d237523ce84239ca1363ad1c8d2e467528ec90acb0034193aeb320740019` |
| Stage 4B approval record SHA-256 | `d809394ef00beab2053795779878025fb1b3b0cd2a49da76302e500ef7f4b2fe` |
| Stage 4 P0 inventory SHA-256 | `fc07b10bb17d91b3447504fe7f5b2e346023fd98bb14da991e1a1dd85381bf53` |

Stage 4B 输出必须由同次运行从原始合成输入重新计算。`ENTER/ADD` 要求当前四门全部 `PASS`；`ADD` 还要求已完成 E5/E6 append-only 重新承保。`REDUCE/EXIT` 不要求四门继续 PASS，但必须绑定同次 Stage 4 `EXIT_CANDIDATE`，或本包批准的回撤/风险硬约束，并且只能减少风险。`TRADE_READY` 仍只是上游研究标签；Stage 5A 不得把它解释为现成仓位、批准或订单。任一上游身份漂移都必须拒绝旧 Stage 5 capability，而不是静默迁移。

### 3.2 合成输入对象

`Stage5SyntheticExecutionCase` 至少由以下不可变、规范化对象组成：

```text
case_id / strategy_id / security_id / account_fixture_id
action_intent = ENTER | ADD | REDUCE | EXIT
knowledge_cutoff / decision_at / strategy_processing_completed_at
stage4_complete_result + stage4_replay_hash
SyntheticApprovalFixture
SyntheticAccountSnapshot
MarketRuleSet / TradingCalendar / SecuritySessionState
ProposalReferencePrice / MarketObservationSet / CostSchedule / ImpactCurve
CorporateActionSet / InitialLedgerSnapshot
all object ids / versions / hashes / supersedes
```

所有时间使用 UTC 存储，同时保存市场时区和本地交易日；所有金额、价格、数量、比例、费用和 P&L 使用十进制定点数。一个 case 只允许一个产业策略、一个证券、一个匿名账户和一条不可变版本链；批量组合由一组已排序 case 明确构成，不能隐式扫描目录或读取其他策略状态。

### 3.3 执行结果状态

Stage 5 不复用 Gate 状态冒充成交状态。拟议状态固定为：

```text
PRECHECK_BLOCKED
ABSTAIN
GATE_REJECTED_AT_EXECUTABLE_PRICE
NON_EXECUTABLE
ENTRY_EXPIRED
TARGET_READY
SYNTHETIC_APPROVED
SYNTHETIC_REJECTED
SIMULATED_SUBMITTED
PARTIALLY_FILLED
FILLED
CANCELLED
RECONCILIATION_BLOCKED
```

- 结构、身份、权限、hash、规则时点、账本不平或未来信息错误为 `PRECHECK_BLOCKED`；
- 合法输入缺失、冲突或无法可靠定价为 `ABSTAIN`；
- 市场规则明确禁止或没有可验证对手流动性为 `NON_EXECUTABLE`；
- 在实际候选价格重跑 Gate 3/4 不通过为 `GATE_REJECTED_AT_EXECUTABLE_PRICE`；
- 新开仓三次候选交易日均未成交为 `ENTRY_EXPIRED`；
- 任何 `FILLED` 都只是合成账本事件，不能被导出为真实委托。

## 4. 市场规则、决策时钟与首次可成交

### 4.1 `MarketRuleSet`

每个市场规则集至少保存：

```text
ruleset_id / version / canonical_hash / supersedes
venue / board / security_type / risk_label_scope
published_at / effective_from / effective_to
source_document_ids / source_byte_hashes / rule_clause_refs
implementation_state = effective | suspended | deferred | repealed
trading_sessions / order_types / price_tick / price_limit_rule
buy_lot_rule / sell_lot_and_odd_lot_rule
same_day_sellability / settlement_rule
suspension_and_resume_rule / ex_rights_ex_dividend_rule
```

适用规则按历史 `execution_at` 选择，不按回放运行日选择。生效区间重叠、断档、官方条文暂缓但本地标为生效、规则来源 hash 漂移或证券板块无法确定均为 `BLOCKED`。本包不把“主板 100 股”“固定 10%/20% 涨跌幅”或当前费用写成跨历史默认值。

### 4.2 决策可执行起点

```text
execution_eligible_from = max(
  decision_at,
  strategy_processing_completed_at,
  synthetic_approval_at
)
```

只有 `execution_eligible_from` 之后的市场观察可参与成交。盘后、休市或日期级信息顺延到下一适用交易时段；盘中候选只有在信息、策略处理、批准和行情均有精确时间戳，且批准的处理延迟已全部经过时才可使用盘中窗口。任一输入只有日期或时间质量不足时，禁止假设当日开盘前已知，顺延到下一完整交易日并标记 `date_only_low_precision`。

为打破“先知道成交价才能定 target、先有 target 才能批准”的循环，批准前只允许使用 `ProposalReferencePrice` 计算风险上限和 proposed target。该价格必须是 `strategy_processing_completed_at` 后、`synthetic_approval_at` 前最后一个合法合成观察，并明确标记 `not_executable_price=true`；它不能进入 fill 或冒充首次可成交价格。批准只确认最大数量、最大金额、最大计划损失和有效期。批准后在真正首个合格窗口重新计算 Gate、风险、容量和现金，最终可提交数量只能下降，不能因价格变化超过已批准上限。

### 4.3 最早合格窗口

窗口按 `window_start_at` 升序扫描。一个窗口只有同时满足以下条件才是候选：

1. 位于适用交易日历和 `MarketRuleSet` 的开放时段；
2. 证券已上市且属于 MVP 允许范围，不是 ST/*ST、上市初期排除期或长期停牌；
3. 没有适用停牌、临时停牌或交易所禁止状态；
4. 申报价和成交基准位于按当时规则计算并按 tick 舍入的合法价格范围；
5. 存在与交易方向相反的可验证成交能力；
6. 行情质量足以计算该窗口 VWAP、容量和成本；
7. 至少一个适用买入申报单位能在全部风险上限内成交。

`first_executable_at` 和 `first_executable_price` 必须来自第一个合格窗口。禁止在后续窗口、开盘价、最低价、收盘价或事后最优价中择优。

### 4.4 行情精度与 VWAP

行情质量固定为 `order_book | tick | minute | daily`：

- `order_book/tick/minute` 可在其实际覆盖和字段支持范围内构建窗口；
- `daily` 只允许在 `execution_eligible_from` 早于当日开盘、成交量和成交额均为正、非停牌、非单一价格涨跌停且规则状态完整时，使用完整交易日 `turnover / volume` 作为 `daily_vwap_low_precision`；
- `daily` 不允许声称盘中某分钟可成交，也不能证明排队顺序或对手盘；
- 只有 OHLC 而没有可信成交额/成交量时为 `ABSTAIN`，不得用 OHLC 平均值；
- 一字涨停买入、一字跌停卖出、无对手盘、零成交、停牌或无法证明报价合法时为 `NON_EXECUTABLE`。

### 4.5 三日进入窗口与退出持续性

拟议的新开仓失效规则为：从第一个本应检查的交易日计为 `attempt_day=1`，第 3 个候选交易日收盘前仍可成交；第 3 日结束仍没有任何合成 fill 时输出 `ENTRY_EXPIRED`。每个 attempt day 都必须用当日首次合格候选价、当日成本和当前估值重跑 Gate 3/4；不能沿用 E4 价格或前一日 PASS。

该三日规则只适用于新增风险。已存在合成持仓的退出不得因三日未成交而放弃；退出意图保持有效，但每日按最新市场规则、风险状态和可成交价格生成新的 append-only 尝试，直至成交、论点重新承保或被治理硬阻断。

## 5. 数量、容量、摩擦与模拟成交

### 5.1 申报数量与价格舍入

买入数量只能向下舍入到当时 `buy_lot_rule` 允许的单位；风险上限和现金上限不得通过向上取整突破。若最小合法买入单位的全成本金额大于任一风险、现金或容量上限，结果为 `NON_EXECUTABLE/MINIMUM_LOT_EXCEEDS_CAP`。

卖出和零股处理严格服从有效 `sell_lot_and_odd_lot_rule`，不得假设所有板块都与主板相同。价格按交易方向和官方 tick/价格笼子规则作不改善风险的舍入；舍入前后值及规则引用都必须留痕。

### 5.2 容量候选

本包提议只在合成 scope 内批准：

```text
maximum_participation_rate = 0.05
capacity_quantity = floor_to_lot(
  verified_executable_window_volume * maximum_participation_rate
)
```

等于 `5%` 允许通过，超过则目标数量先被容量约束缩小，不能把超额部分假设成交。`verified_executable_window_volume` 必须与方向、窗口和数据质量一致；日线低精度模式只可保守使用完整日总量，且仍受一字板/停牌否决。真实 backtest 的参与率和盘口容量必须另行校准、批准，不能继承本候选值。

### 5.3 费用与税费

`CostSchedule` 必须按成交日、市场、证券类型、方向和账户费率版本化，逐项保存：

```text
exchange_fee / regulatory_fee / transfer_fee
stamp_duty_or_other_tax
broker_commission_rate / broker_minimum_commission
rounding_rule / currency
effective_from / effective_to
official_or_broker_source_ref / source_hash
```

税费、交易所费率和券商佣金不得合成一个历史常数。买卖方向不同的项目分别计算，最低佣金只在其实际适用层级执行。缺失适用费率、时点或舍入规则时为 `ABSTAIN`；规则重叠、hash 漂移或把当前费率回填历史为 `BLOCKED`。

### 5.4 滑点与冲击

滑点和冲击不得使用隐藏默认常数。`ImpactCurve` 至少保存窗口、方向、流动性分组、版本/hash，以及按参与率递增的显式 `participation_rate → adverse_slippage_rate` 节点：

- 节点参与率严格递增，买入/卖出的不利滑点绝对值单调不减；
- 节点间只允许确定性的线性插值；禁止超过最大批准节点外推；
- 买入合成价不得因模型低于基准 VWAP，卖出合成价不得因模型高于基准 VWAP；
- 滑点进入成交价格，交易费和税费另记现金分录，不得重复扣除；
- 缺失适用曲线为 `ABSTAIN`，非单调曲线、方向有利化或版本漂移为 `BLOCKED`。

### 5.5 Gate 3/4 重跑

在提交任何新增风险目标前，必须用候选窗口、all-in 买入价格、实际适用进入摩擦和版本化预期退出摩擦重新评估 FR-GATE-006 的当前可交易视图。E4 前冻结的 `public_economic_expectation_class`、ExpectationSnapshot 和历史 Gate 3 结果保持不变；Stage 5 只能新增 `current_executable_market_reflection_state`，并用 Stage 5 发现的合成可成交价格重新计算 Gate 4 的剩余收益和赔率。这样满足“首次可成交价格重跑 Gate 3/4”的需求，但不使用 E4 后价格篡改 E4 前预期。

- 对 `ENTER/ADD`，冻结经济预期不合格、当前价格已充分反映或 Gate 4 非 PASS → `GATE_REJECTED_AT_EXECUTABLE_PRICE`，新增目标数量为零；
- 缺失价格、成本、退出摩擦或估值口径 → `ABSTAIN`；
- Stage 5 不得修改 Stage 4 的旧结果，只能生成引用旧结果的新 re-underwriting 结果；
- 价格上涨不能提高估值，价格下跌不能放宽 Gate 1—3。
- `REDUCE/EXIT` 不因当前 Gate 非 PASS 而被阻断；它们按可成交规则减少风险，但不能反向增加仓位。

### 5.6 订单寿命、部分成交与顺序

拟议合成订单类型只允许 `DAY`。每个批准窗口生成一个不可变 `SyntheticOrderIntent`；窗口结束后未成交余量自动 `CANCELLED`，不得跨日静默保留。多日拆单必须预先登记 schedule，且每个交易日重新检查 Gate、风险、现金和容量。

若批准后市场可用容量下降，只允许按最新允许数量形成 `PARTIALLY_FILLED`，余量取消；不得为了“完成目标”突破容量。填充顺序固定为 `event_time → event_type_priority → stable_event_id`。Stage 5A 禁止随机排队、随机滑点或 Monte Carlo fill；未来引入随机执行必须新建规则版本、固定种子和分布并重新批准。

## 6. 合成组合与风险预算

### 6.1 合成账户边界

`SyntheticAccountSnapshot` 必须为匿名 fixture，并至少保存：

```text
account_fixture_id / version / hash / as_of
base_currency = CNY
cash / receivables / payables / positions / sellable_lots
net_asset_value / high_water_mark / drawdown
risk_cluster_exposures / planned_loss_exposures
synthetic = true / no_broker_binding = true
```

首版禁止融资、融券、做空、杠杆和负现金；组合 `gross_weight <= 1`、`0 <= net_weight <= 1`。本包产生的账户、仓位、批准、order intent 和 fill 都是合成制品，不能映射到真实账户 ID 或券商接口。

### 6.2 压力损失与初始目标

```text
stress_loss_rate = max(abs(min(0, stress_scenario_return)), 0.10)

size_by_loss_budget
  = account_nav * planned_account_loss_rate / stress_loss_rate

initial_target_value = min(
  size_by_loss_budget,
  account_nav * 0.05,
  liquidity_capacity_value,
  company_remaining_cap,
  every_risk_cluster_remaining_cap,
  aggregate_open_risk_remaining_value,
  available_cash_after_cost_reserve
)
```

所有约束先换算为 CNY 金额再比较。压力损失率等于 `10%` 允许；压力情景缺失、非有限值或口径不一致为 `ABSTAIN`。舍入到合法申报数量后必须再次验证全部上限。

### 6.3 候选风险参数

仅针对拟议合成 scope，提交以下值审批：

| 约束 | 候选值 | 等号 |
|---|---:|---|
| `NORMAL` 单笔计划损失 | `0.5% NAV` | 允许 |
| `DEFENSIVE` 单笔计划损失 | `0.25% NAV` | 允许 |
| `CRISIS` 新增风险 | `0` | 禁止新仓 |
| E4 初始目标上限 | `5% NAV` | 允许 |
| 单一公司总权重上限 | `10% NAV` | 允许 |
| 每个风险簇计划损失上限 | `1.5% NAV` | 允许 |
| 每个风险簇市值权重上限 | `20% NAV` | 允许 |
| 全部未平仓计划损失上限 | `4% NAV` | 允许 |

证券同时属于多个风险簇时，必须对每个簇都通过；不能选择最宽松的分类。风险簇来自版本化 `RiskClusterSnapshot`，至少保存公司、客户、产品价格、政策催化和共同流动性依赖。缺失必要簇归属为 `ABSTAIN`，跨策略共享簇账本或 P&L 为 `BLOCKED`。

### 6.4 市场状态输入

Stage 5A 只定义风险缩放接口，不批准真实市场状态分类器。`MarketRegimeSnapshot` 必须来自另行批准的精确规则，或在本 scope 内明确标为 synthetic fixture。状态只允许 `NORMAL / DEFENSIVE / CRISIS`，只缩小风险，不改变 E4、四道门、估值或证据判断。

真实状态规则不存在、hash 不匹配或当前状态未知时，新风险为 `ABSTAIN`；不得默认 `NORMAL`。合成测试必须覆盖三个状态和未知状态。

### 6.5 回撤闸门

回撤使用扣除外部现金流影响后的账户净值历史高点：

```text
drawdown = max(0, 1 - current_nav / adjusted_high_water_mark)
```

拟议动作固定为：

| 回撤区间 | 动作 |
|---|---|
| `<8%` | 仍受市场状态和全部普通上限约束 |
| `>=8% and <12%` | 新交易计划损失上限降为 `0.25% NAV`，禁止加仓 |
| `>=12% and <15%` | 暂停全部新开仓，只处理退出和降险 |
| `>=15%` | `STOPPED`；禁止新增风险，按可成交条件处理退出并要求人工复盘 |
| `>=20%` | 标记 `SURVIVAL_LIMIT_BREACH`，不得作为等待触发线 |

等号进入更严格档。恢复不能由净值反弹自动触发，必须有 append-only 恢复记录、归因、规则检查和 owner/人工批准；本合成 scope 只验证该记录结构，不授予真实恢复权限。

### 6.6 五层仓位与批准单向性

```text
target      = 策略和风险引擎计算的期望数量
approved    = 合成批准后允许的数量
submitted   = 送入合成执行器的数量
filled      = 合成成交事件累计数量
actual      = 账本从有效 fill 和公司行动派生的数量
```

五层不得互相覆盖。`SyntheticApprovalFixture` 只能把 target 减少到更小非负值或拒绝，不能增加数量、改变方向、放宽风险、替换证券或延长订单寿命；增加风险必须形成新 target 和新 replay。`approved >= submitted >= filled` 按每个 intent 成立，`actual` 只能从账本派生。所有差异必须有 reason code。

批准前 proposed target 使用第 4.2 节 `ProposalReferencePrice`；首次可成交窗口出现后：

```text
final_submittable_quantity = min(
  approved_quantity,
  recomputed_gate_and_risk_quantity,
  current_capacity_quantity,
  current_cash_affordable_quantity
)
```

任一重算结果为零则不提交。价格下降不能自动增加股数，价格上涨、费用或风险恶化必须缩小或取消；需要增加批准数量、金额、风险或有效期时必须生成新 target 和新 `SyntheticApprovalFixture`。

## 7. Append-only 双分录账本

### 7.1 账本原则

`PositionLedger` 是 InvestSystem 自有、按策略和匿名账户隔离的 append-only journal。每个事件至少保存：

```text
ledger_event_id / idempotency_key / event_type
strategy_id / account_fixture_id / security_id
effective_at / trade_date / settlement_date
source_object_ids / source_hashes
postings[] = {account, currency_or_security, debit, credit}
rule_ids / rule_versions / rule_hashes
supersedes_or_reversal_of / canonical_hash
```

每个事件的 debit 与 credit 必须按资产单位平衡；现金、证券、应收、应付、费用、税费、股息和 P&L 分账户记录。不得用直接修改余额、覆盖旧 fill 或重写成本来“修正”历史。

### 7.2 事件类型、幂等与修订

首版事件类型至少包括：

```text
OPENING_BALANCE
CASH_RESERVATION / CASH_RELEASE
SYNTHETIC_ORDER_ACCEPTED / SYNTHETIC_ORDER_CANCELLED
TRADE_FILL / FEE / TAX
TRADE_SETTLEMENT / SECURITY_AVAILABILITY
CASH_DIVIDEND / SHARE_DISTRIBUTION / SPLIT_OR_CONSOLIDATION
RIGHTS_OR_ALLOTMENT / DELISTING_OR_CASH_OUT
MARK_TO_MARKET / EXTERNAL_CASH_FLOW
REVERSAL / REPLACEMENT
```

相同 `idempotency_key + canonical bytes` 重放为幂等；相同 key 不同内容为 `BLOCKED`。错误事件只能追加等额反向 `REVERSAL` 后追加替代事件。排序固定为 `effective_at → event_type_priority → ledger_event_id`，同序结果不得依赖数据库返回顺序。

### 7.3 T+1、交收与可用余额

买入成交、证券交收、可卖数量、卖出成交、资金应收/应付和可用现金分别记录。是否可当日卖出、交收日、资金可用规则和特殊证券例外全部来自有效 `MarketRuleSet`；不能只用一个布尔 `T+1` 覆盖所有历史和证券类型。

任何卖出数量必须小于等于当时 `sellable_quantity`；现金预留必须覆盖买入价款和最坏适用费用。负可用现金、超卖、提前释放预留或结算日错配为 `RECONCILIATION_BLOCKED`。

### 7.4 Lot 与公司行动

每个 fill 建立带获得时间、数量、全成本和可卖时间的不可变 lot；卖出按 `acquired_at → lot_id` 的 FIFO 顺序耗用。FIFO 只作为本合成账本拟议规则，不声称等于任何券商展示成本算法。

公司行动必须以未复权原始成交价和独立 ledger event 回放：

- 现金分红进入应收/现金与收益分录；
- 送股、转增、拆股和合股调整 lot 数量及单位成本，但不改写历史 fill；
- 配股、供股、权利选择、退市或现金收购需要显式事件和策略选择；
- 无法完整建模的适用公司行动必须 `BLOCKED`，不得用前复权/后复权价格静默代替；
- 复权行情只可用于收益研究或交叉检查，不能作为成交价或账本现金流来源。

### 7.5 持仓派生与对账

`actual_quantity`、可卖数量、现金、成本、应收/应付和净资产都从已排序 journal 派生，不把缓存余额当作权威。每个事件后必须验证：

```text
cash_identity_balances
security_quantity_identity_balances
reserved_cash <= cash_available_under_rules
sellable_quantity <= actual_quantity
actual_quantity = opening + buys - sells + corporate_action_quantity_changes
```

任一不平必须停止后续事件并输出 `RECONCILIATION_BLOCKED`；不得以自动补差分录掩盖问题。

## 8. 估值、P&L 与归因

### 8.1 净资产与总 P&L

每个估值时点：

```text
position_market_value = sum(actual_quantity * unadjusted_mark_price)

equity = settled_cash
       + unsettled_cash_receivable
       - unsettled_cash_payable
       + position_market_value
       + other_explicit_receivables
       - other_explicit_payables

period_total_pnl = ending_equity
                 - beginning_equity
                 - net_external_cash_inflow
```

外部入金/出金与投资 P&L 分离。费用、税、滑点、现金股息、公司行动现金流、已实现和未实现 P&L 分项保存，并必须加总到 `period_total_pnl`；不得把滑点同时计入成交价和费用。

### 8.2 标记价格与缺失

正常交易日使用该估值时点前最后一个合法、未复权市场价格。停牌时可沿用停牌前最后合法价格，但必须标记 `stale=true`、停牌时长和来源；这只用于净值展示，不代表可成交。没有历史合法 mark 时 P&L 为 incomplete/`ABSTAIN`，不得记零价或回填未来复牌价。

已实现 P&L 按 FIFO lot 的全成本与卖出净收入计算，未实现 P&L 按剩余 lot 全成本与当前未复权 mark 计算。任何成本算法改变都需要新规则版本并重跑，不能改写旧 ledger。

### 8.3 策略和风险簇隔离

产业策略必须拥有独立 `strategy_id`、case、input ref、Manifest、target、approval、order intent、fill、ledger、P&L 和 replay。题材策略即使使用相同证券或市场规则，也不得共享仓位、现金分录、成本摊销或 P&L。

风险簇可以使用 provider-neutral 共用分类库，但每个策略必须独立计算和保存簇暴露。任何未来跨策略净额、共享资金或统一组合优化都需要新 ADR、契约和 owner approval。

## 9. Deterministic replay 与审计

### 9.1 Replay 内容

Stage 5 `replay_hash` 至少绑定：

- Stage 5 approved bundle/approval identity，以及第 3.1 节精确 Stage 4B 身份；
- Stage 4 complete result hash/replay hash 和 Stage 5 case input hash；
- MarketRuleSet、TradingCalendar、SecuritySessionState、行情、费用、ImpactCurve、公司行动和初始账本全部 canonical hash；
- 合成账户、风险簇、市场状态、target、合成 approval、order intent、fill、ledger event、mark 和 P&L 结果；
- 代码 commit、配置 hash、Decimal/rounding 规则和明确注入的 clock。

墙钟时间、进程号、机器路径、日志位置、数据库行号、字典插入顺序和网络端点不得进入 replay identity。相同规范输入必须得到相同事件顺序、fill、账本、P&L 和 replay hash；任一承重输入变化必须改变相应 hash。

### 9.2 `audit_replay`

历史材料或撤回 Release 只允许显式 `audit_replay`：

- 固定原输入、原规则、原代码、原市场规则和原账本，复现旧结果；
- 不重新判断当前 Release 状态，不形成新 current decision；
- 不产生新 target、批准、仓位、order intent、fill 或 P&L 权威；
- 输出必须标记 `audit_only=true` 并引用原 replay；
- 新规则重算属于独立研究 run，不能覆盖旧结果或冒充当时可得结果。

## 10. 失败关闭和副作用顺序

所有计算先纯函数化完成并验证，再形成一次性不可变结果；本草案不允许任何外部副作用。未来 durable 实现的顺序必须是：

```text
校验 capability 与所有输入身份
→ 选择历史有效 MarketRuleSet/Calendar/Cost/CorporateAction
→ 计算候选窗口、Gate 重跑、风险和 target
→ 生成合成 approval/order/fill 事件
→ 在内存重放完整 ledger 并完成对账
→ 验证 P&L 与 replay hash
→ 原子持久化整组结果或全部不写
```

任何阶段失败都不得留下“有 fill 无账本”“有仓位无批准”“有 P&L 无市场数据 hash”或部分提交。durable SQLite 的表、事务、幂等、冲突、恢复和迁移语义必须在 Stage 5B—5D 实现前另有技术设计；本包不提前创建 migration 或写数据库。

## 11. 提议的测试与验收矩阵

获批后才允许实现下列测试；当前清单不表示 evaluator、ledger 或回放已经存在：

| 类型 | 最低覆盖 |
|---|---|
| 市场规则 | 历史规则切换、暂缓条文、板块/风险标签、T+1、tick、买卖 lot、停复牌、除权除息 |
| 时间 | 盘前、盘中精确、盘后、date-only、周末/节假日、处理延迟、批准延迟 |
| 可成交 | 正常 VWAP、一字涨跌停、零成交、无对手盘、停牌、最小 lot 超风险、三日到期 |
| Gate 重跑 | 首次价仍 PASS、上涨后 Gate 3/4 REJECT、摩擦缺失 ABSTAIN、价格/hash 漂移 BLOCKED |
| 摩擦 | 费用生效切换、方向税费、最低佣金、5% 等号、略超、impact 节点/插值/禁止外推 |
| 组合 | `0.5%/0.25%/0`、`5%/10%`、簇 `1.5%/20%`、总风险 `4%` 的等号和略超 |
| 回撤 | `8%/12%/15%/20%` 等号，恢复记录缺失，市场状态未知和 CRISIS |
| 状态分离 | target、approved、submitted、filled、actual 差异；批准只能减少；部分成交与取消 |
| 账本 | 双分录、T+1 可卖、现金预留、交收、FIFO、幂等冲突、reversal/replacement、原子失败 |
| 公司行动 | 现金分红、送转、拆并股、配股/选择缺失、停牌 stale mark、禁止复权价成交 |
| P&L | 费用/税/滑点/股息/已实现/未实现/外部现金流加总与全账户对账 |
| Replay | 同输入同 hash；规则、行情、成本、公司行动、risk、approval 或事件顺序变化均改 hash |
| 隔离 | KB 内部路径、真实账户/券商标识、Stage 2B/4B capability 替代、题材账本和运行模式漂移全部拒绝 |

## 12. 当前明确禁止实现或默认的内容

在第 13 节全部批准且 approved artifacts 另行形成前，不得：

- 新增 Stage 5 evaluator、市场规则引擎、组合优化器、账本、P&L、数据库表或 migration；
- 把本 Markdown 或 draft JSON 作为运行规则解析；
- 把 `3 日/5%/0.5%/5%/10%/1.5%/20%/4%/8%/12%/15%` 写入代码或配置默认值；
- 使用历史归档中的费用常数、Kelly、固定仓位、市场状态阈值或券商假设；
- 下载真实行情、读取真实账户、创建真实仓位、调用券商 API 或产生可提交订单；
- 授权 backtest、paper、shadow、live、程序化交易或任何资金部署；
- 把 Stage 4 `TRADE_READY`、`SHADOW_ONLY` 或 `EXIT_CANDIDATE` 直接转换为仓位或订单；
- 读取或修改 KB SQLite、raw、staging、published 目录、工作树或内部包；
- 跨产业/题材策略共享 signal、Manifest、cash、position、ledger、fill 或 P&L。

当前只允许校验 draft identity、文字文档 hash、四十项 pending、零 approval record、空运行模式和全部权限 false。

## 13. Owner 逐项批准清单

以下四十项当前全部为待批准；勾选框不得在没有 owner 明确批准的情况下修改。

### A. 身份、范围与失败语义

- [ ] `5A-01`：批准 Stage 5A 只提出独立 `stage5_synthetic_execution_validation` capability；Stage 4B、局部 4A、Stage 2B 或本草案均不能替代它。
- [ ] `5A-02`：批准精确固定第 3.1 节 Stage 4B bundle/rules/approval/inventory hash；`ENTER/ADD` 要求本次重算四门 PASS，`REDUCE/EXIT` 则要求精确 exit/risk mandate 且只能减险。
- [ ] `5A-03`：批准单 strategy/security/account/case 版本链、规范 hash、UTC + 市场交易日、十进制定点和所有输入显式 version/hash/supersedes。
- [ ] `5A-04`：批准 `MarketRuleSet` 按官方字节、文号、生效/废止/暂缓区间和证券范围固定，按历史执行时点选取，禁止用当前规则回填历史。
- [ ] `5A-05`：批准 `BLOCKED / ABSTAIN / NON_EXECUTABLE / GATE_REJECTED / ENTRY_EXPIRED / PARTIAL / FILLED / RECONCILIATION_BLOCKED` 分层，不用 Gate 标签冒充成交状态。

### B. 决策时钟与首次可成交

- [ ] `5A-06`：批准 `execution_eligible_from=max(decision_at, processing_completed_at, synthetic_approval_at)`；批准前仅可用处理完成后、批准前的 `ProposalReferencePrice` 形成上限，且该价格明确不可成交、不可进入 fill。
- [ ] `5A-07`：批准盘中仅接受精确时间和完整延迟；盘后、休市或 date-only 信息顺延下一完整交易时段并标记低精度。
- [ ] `5A-08`：批准按时间扫描第一个同时满足 session、证券状态、价格、对手流动性、数据质量、容量和最小 lot 的窗口，禁止事后择优。
- [ ] `5A-09`：批准一字涨停买入、一字跌停卖出、零成交、无对手盘、停牌或报价合法性不可证明时不得模拟成交。
- [ ] `5A-10`：批准日线只在决定开盘前已生效且数据完整、非一字板时使用完整日 `turnover/volume`，不得声称盘中时间或排队顺序。
- [ ] `5A-11`：批准新开仓第 1—3 个候选交易日逐日重跑 Gate 3/4，第 3 日仍无 fill 后 `ENTRY_EXPIRED`；等号日仍可尝试。
- [ ] `5A-12`：批准退出不适用三日放弃；已有合成仓位的退出按每日新价格和规则持续 append-only 尝试，不保证能在止损价成交。
- [ ] `5A-13`：批准买入向下舍入到有效 lot、卖出/零股服从历史规则、价格按 tick 作不改善风险的舍入，最小 lot 超任一上限即跳过。

### C. 容量、成本与 fill

- [ ] `5A-14`：批准仅在合成 scope 使用窗口成交量 `5%` 最大参与率、等号通过、超额先缩减且真实历史验证必须重新校准。
- [ ] `5A-15`：批准显式单调 `ImpactCurve`、节点间线性插值、禁止外推、买卖方向只能产生不利滑点，并禁止任何隐藏默认值。
- [ ] `5A-16`：批准费用、税费、佣金和最低佣金按市场/证券/方向/账户/生效日分项版本化，禁止一个常数覆盖历史。
- [ ] `5A-17`：批准 VWAP/滑点成交价与 fee/tax 现金分录分离，禁止滑点或费用重复扣除。
- [ ] `5A-18`：批准冻结 E4 前经济预期和历史 Gate 3，新增当前可成交价格反映状态并重算 Gate 4；`ENTER/ADD` 非 PASS 时目标为零，`REDUCE/EXIT` 不被反向阻断，且不得改写 Stage 4 旧结果。
- [ ] `5A-19`：批准 Stage 5 合成 intent 仅为 `DAY`；部分成交按最新允许容量，窗口结束取消余量，多日拆单必须预登记并每日重审。
- [ ] `5A-20`：批准 fill 完全确定性，事件顺序为 `time → type priority → stable id`；Stage 5A 不使用随机队列、随机滑点或 Monte Carlo。

### D. 组合与风险

- [ ] `5A-21`：批准匿名 CNY 合成账户、无杠杆/做空/负现金、gross 不超过 100%、net 位于 0—100%，且没有真实账户或券商绑定。
- [ ] `5A-22`：批准 `stress_loss_rate=max(压力下行绝对值,10%)` 和第 6.2 节取最小值的目标金额公式，所有约束先统一为 CNY。
- [ ] `5A-23`：批准合成 `NORMAL/DEFENSIVE/CRISIS` 的单笔计划损失率分别为 `0.5%/0.25%/0`，E4 初始上限 `5%`、单公司总上限 `10%`，等号通过。
- [ ] `5A-24`：批准每风险簇计划损失 `1.5% NAV`、权重 `20% NAV`、全部未平仓计划损失 `4% NAV`，等号通过。
- [ ] `5A-25`：批准证券同时属于多个风险簇时逐簇通过，簇身份显式版本化，缺失为 ABSTAIN，禁止跨策略共享簇账本或 P&L。
- [ ] `5A-26`：批准市场状态只缩小风险、不改变四道门；真实分类器未另行批准时不得默认 NORMAL，合成测试只用明确 fixture。
- [ ] `5A-27`：批准 `8%/12%/15%/20%` 等号进入更严格回撤档、动作和人工恢复记录语义，阈值仅限拟议合成 scope。
- [ ] `5A-28`：批准 target/approved/submitted/filled/actual 五层分离；首次可成交窗口按批准量、重算 Gate/风险量、容量量和现金可负担量取最小值，只能缩小或取消；增加上限必须形成新 target 和新合成批准。

### E. 账本、公司行动与 P&L

- [ ] `5A-29`：批准按 strategy/account 隔离的 append-only 双分录 journal、资产单位平衡和禁止直接修改余额。
- [ ] `5A-30`：批准 opening/cash reservation/order/fill/fee/tax/settlement/security availability/corporate action/mark/external flow/reversal 事件集合和固定排序。
- [ ] `5A-31`：批准同 idempotency key 同字节幂等、不同字节 BLOCKED；错误只以 reversal + replacement 修订，不覆盖历史。
- [ ] `5A-32`：批准成交、交收、可卖数量、现金可用分别记账，T+1/交收例外来自有效 MarketRuleSet，超卖或负可用现金阻断对账。
- [ ] `5A-33`：批准每个 fill 建立 lot，卖出按 `acquired_at → lot_id` FIFO；该方法仅是合成账本规则，不声称等于券商成本展示。
- [ ] `5A-34`：批准公司行动以未复权价格和独立 ledger event 回放；分红/送转/拆并/配股/退市缺失时失败关闭，复权价不得作为 fill。
- [ ] `5A-35`：批准 actual position、cash、cost、sellable 和 NAV 全部从 journal 派生，每事件后执行现金、证券、预留和数量恒等式对账。
- [ ] `5A-36`：批准 equity/P&L 公式、外部现金流剥离、费用/税/滑点/股息/已实现/未实现分项及加总恒等式。
- [ ] `5A-37`：批准未复权合法 mark、停牌 stale 标记、无历史 mark 时 P&L incomplete/ABSTAIN，禁止未来复牌价或零价回填。

### F. Replay、隔离与零权限

- [ ] `5A-38`：批准 replay hash 覆盖规则、Stage 4、行情、费用、impact、公司行动、risk、approval、fill、ledger 和 P&L，并排除机器运行噪声。
- [ ] `5A-39`：批准 `audit_replay` 只复现原固定结果，不形成新的 current decision、target、批准、仓位、fill 或 P&L 权威。
- [ ] `5A-40`：批准产业/题材策略全链隔离，以及本包零 backtest/paper/shadow/live、零真实仓位/账户/订单、零券商/KB 写权限。

## 14. 批准后的唯一下一步

即使 owner 批准全部四十项，授权也仍只能是：

```text
scope = stage5_synthetic_execution_validation
run_mode = research
synthetic_market_fixture = true
synthetic_account_fixture = true
validation_only = true
runtime_capability = exact Stage 5 approved bundle only
backtest = false
paper = false
shadow = false
live = false
real_positions = false
real_accounts = false
real_orders = false
broker_connectivity = false
```

批准后才允许另行：

1. 保留本 draft 和 draft machine proposal 不变，生成独立 approved bundle、approval record 和 capability；
2. Stage 5B 实现历史有效 `MarketRuleSet`、交易日历、首次可成交与合成 fill；
3. Stage 5C 实现合成组合风险、五层仓位和 append-only 双分录账本；
4. Stage 5D 实现 P&L、deterministic replay、合成 golden matrix 和全仓回归；
5. 完成后仍不得进入 Stage 6 backtest，必须等待 Stage 3D 与 Stage 5 全部完成，并由 owner 另行批准 Stage 6。

任何条款、阈值、官方规则版本、成本方法、lot 方法、账本事件或权限变化都必须产生新版本、canonical hash 和新的 owner approval。
