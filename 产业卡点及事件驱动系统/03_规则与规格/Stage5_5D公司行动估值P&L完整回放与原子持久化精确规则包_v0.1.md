# Stage 5 / 5D 公司行动、估值、P&L、完整回放与原子持久化精确规则包 v0.1

文档状态：`draft_for_owner_approval`

阶段：`Stage 5 / 5D governance proposal`

上游批准范围：`stage5_synthetic_execution_validation`

当前权限：`zero_runtime_authority`；仅供 owner 审阅，不签发 capability，不实现业务规则，不写 SQLite

拟议交付顺序：`5D-1 pure complete replay → owner acceptance → 5D-2 SQLite v4 atomic persistence`

## 1. 目的

本包把 Stage 5A 已批准、但 Stage 5C 明确没有实现的公司行动、未复权 mark、NAV、P&L、完整 replay 和 durable persistence 收敛为恰好四十八项可逐项审阅、但只能整包原子批准的决定。目标不是扩大权限，而是在匿名合成 `research` 验证范围内，先建立无 I/O 的确定性纯函数，再决定是否把同一组已验证结果原子写入 InvestSystem 自有 SQLite。任意少于四十八项的部分批准只能作为审阅记录，固定 `zero_runtime_authority`，不得形成 partial capability、部分实现授权或 5D-1/5D-2 入口。

本文特别解决以下已确认边界：

- Stage 5C 的完整未来 settlement plan 不是当前状态；任何 replay 都只完整到显式 `ending_at/injected_clock`；
- Stage 5C 买入费用和税费已进入 lot `full_cost`，但尚未与逐证券 `SECURITY_COST` 全局闭合；
- 当前账本的 CNY posting 没有证券维度，不能用全账户净额代替逐证券成本对账；
- opening lot 只有汇总全成本，不能凭空拆出本金、滑点、费用和税费；
- realized/unrealized 与 fee/tax/slippage 是两个正交维度，平铺相加会重复计价；
- 非空公司行动、mark、NAV/P&L、external flow、完整 Stage 5 replay、SQLite v4 和 durable atomic commit 当前都不存在。

本文件只是待批准规则。即使第 13 节全部四十八项获得 owner 明确批准，也必须保留本 draft 原始字节不变，另行生成 approved machine bundle、approval record 和 typed capability verifier 后，才能开始 5D-1；5D-2 还必须等待 5D-1 独立验收。本文不得被运行时解析，不得冒充已实现能力或持久化授权。

## 2. 精确上游身份与不可继承权限

### 2.1 Stage 5A approved identity

本提案只依赖以下精确 Stage 5A 身份，不修改、覆盖或重写任何既有 Stage 5A 文件：

| 对象 | 精确身份 |
|---|---|
| strategy | `industrial_bottleneck_event` |
| approval scope | `stage5_synthetic_execution_validation` |
| bundle id | `industrial_event_stage5_5a_execution_portfolio_ledger_replay` |
| bundle version | `0.1.0` |
| bundle SHA-256 | `c69bc7170b608bc6f3e2dd4119e08b13d4f10f03730be115dbc191b47544eeb7` |
| rules SHA-256 | `bb7ef84b1287be1111fe95571efa58cd268a65d862b7d235508fc31ccbaf0c69` |
| approval id | `rule_approval_stage5_5a_execution_portfolio_ledger_replay_v0_1_0` |
| approval record SHA-256 | `5b9536f546337ba38408d255b3fbad68fbbdf6d9ccba9af79b10b6e04ca8cd78` |
| specification SHA-256 | `df866949bdfcc8eb52451b38155080551291d7539f17b730a01a233cf60a5740` |
| approval document SHA-256 | `4862d0c8add5d28db8f24432d4d3958c9de6f73bf74ae7d4754e0290916cbf02` |

Stage 5A 的 capability 只证明四十项上游规则身份已获批准，不证明 5D evaluator、公司行动、mark、P&L、完整 replay 或 persistence 已存在。Stage 5B、Stage 5C、Stage 4B、局部 Stage 4A、Stage 2B capability 均不能替代未来独立的 Stage 5D typed rules view。

### 2.2 Stage 5C code baseline

Stage 5D 固定以下 Stage 5C 已验收代码基线：

```text
stage5c_git_commit = 7f64c584c5c7be5e2385a177fab9e5d31e3f665b
subject = feat: implement stage 5c synthetic portfolio ledger
```

该提交是 5D 的行为与回归基线，不是不可修改的运行二进制。Ledger V2 和费用资本化必然改变 Stage 5C canonical event/replay bytes；任何此类变化必须提升相应 schema、重新运行全部 Stage 5A—5C 专项和全仓回归，并在未来 Stage 5D approved bundle 中同时绑定上述基线提交与实际 Stage 5D `code_commit`。未提交工作树、分支名和机器路径不得成为规则身份。

### 2.3 零权限边界

当前以及未来获批后的 5D-1/5D-2 都只允许：

```text
scope = stage5_synthetic_execution_validation
run_mode = research
synthetic_market_fixture = true
synthetic_account_fixture = true
validation_only = true
backtest = false
paper = false
shadow = false
live = false
real_positions = false
real_accounts = false
real_orders = false
broker_connectivity = false
kb_write = false
```

Stage 5D 不接触 KB SQLite、`raw/`、`staging/`、工作树或内部包，不下载真实行情，不读取真实账户，不创建可提交订单，不把 P&L 验证结果解释为策略有效性或资金部署依据。

## 3. 分段实施与纯函数总边界

### 3.1 5D-1

5D-1 只实现无 I/O 的纯函数 complete replay：

```text
raw Stage5DCompleteReplayCase
→ 内部重新运行 exact Stage 5C
→ 校验 typed PIT inputs 与完整覆盖
→ 按状态投影公司行动、mark 和 external flow events
→ replay Ledger V2 through ending_at
→ 从同一 journal 的 beginning/end 前缀派生 valuation
→ 计算二维 P&L matrix
→ 对账并生成 Stage5CompleteReplayEnvelope
```

公开入口不得接受 caller-supplied Stage 5C PASS、ledger state、NAV、P&L 或 replay result 作为权威捷径。所有派生结果必须在同一次调用内从原始 typed case 重算。任何失败只返回不可变失败结果，不写文件、日志数据库、缓存或 SQLite。

### 3.2 5D-2

5D-2 只能消费已由 5D-1 完整验证且 canonical hash 闭合的 envelope。它不得重新解释业务规则，不得在写入时补事件、补余额、补 mark 或修正 P&L。持久化目标只能是 InvestSystem 现有 `var/state/invest_system.sqlite3` 的 schema v4；不得新建策略专用数据库、共享可写 KB 数据库或把 SQLite 作为计算权威。

## 4. Typed PIT 输入合同

`Stage5DCompleteReplayCase` 至少包含：

```text
case_id / strategy_id / account_fixture_id
raw_stage5c_case
account-wide multi-security opening state
OpeningLotAttributionSet
CorporateActionCoverageSet + CorporateActionElectionSet
UnadjustedMarkObservationSet
SyntheticExternalCashFlowSet
ValuationPeriod(beginning_at, ending_at, interval=(beginning_at, ending_at])
injected_clock / knowledge_cutoff
code_commit / config_hash / decimal_context_id
purpose = new_research_validation | audit_replay
all object ids / schema versions / canonical hashes / supersedes
```

一个 5D case 只允许一个产业策略和一个匿名账户，但账户可以包含多个证券。所有账户内非零 lot、公司行动覆盖和 opening attribution 必须按 `security_id → lot_id` 规范排序并逐一闭合；每个 valuation point 只对该 prefix 中 `actual_quantity > 0` 的证券要求 mark coverage 和合法 observation，已经在该 valuation point 前全部处置的证券不要求该点 mark。不能只为本次成交证券估值而忽略账户内其他持仓。

每个外部状态都必须保存自己的经济时点和自己的知识可得时点，不得把 action-wide `available_at` 复用于支付、现金可用、证券交付或可卖状态。公司行动 typed 时间至少固定：

```text
terms: announced_at / terms_available_at
entitlement: entitlement_cutoff_at / entitlement_rule_available_at
economic action: economic_effective_at / economic_state_available_at
cash: payable_at / paid_at / paid_state_available_at
      cash_available_at / cash_available_state_available_at
security: security_delivered_at / delivered_state_available_at
          security_sellable_at / sellable_state_available_at

entitlement_determined_at
  = max(entitlement_cutoff_at, terms_available_at, entitlement_rule_available_at)
recognized_at
  = max(economic_effective_at, economic_state_available_at, entitlement_determined_at)
paid_recognized_at
  = max(paid_at, paid_state_available_at, recognized_at)
cash_available_recognized_at
  = max(cash_available_at, cash_available_state_available_at, paid_recognized_at)
security_delivered_recognized_at
  = max(security_delivered_at, delivered_state_available_at, recognized_at)
security_sellable_recognized_at
  = max(security_sellable_at, sellable_state_available_at,
        security_delivered_recognized_at)
```

不适用的状态必须是 typed `NOT_APPLICABLE`，不能省略。已支付但其支付事实尚不可得时仍只保留应收；支付事实已可得但现金尚不可用时进入 `CASH_SETTLED_UNAVAILABLE`；证券已确认但尚未交付/可卖时依次保留在 `SECURITY_UNSETTLED/SECURITY_UNSELLABLE`。任何状态事件的 ledger `effective_at` 使用相应 `*_recognized_at`，不得回写到较早经济时点。

`CorporateActionElectionSet` 对覆盖内每个 action 必须声明 `election_requirement=NOT_APPLICABLE | MANDATORY | CHOICE_REQUIRED`。`NOT_APPLICABLE/MANDATORY` 的选择字段和选择时点只能是 typed `NOT_APPLICABLE`，不得伪造 caller choice；`CHOICE_REQUIRED` 至少固定 `election_id/action_id/strategy_id/account_fixture_id/security_id/choice_code/election_made_at/election_available_at/election_deadline_at/deadline_rule_id/deadline_rule_version/deadline_rule_hash/source_id/source_bytes_hash/revision_id/supersedes/canonical_hash`，且 `choice_code` 必须来自 exact action terms。选择时点唯一为：

```text
terms_available_at <= election_made_at <= election_deadline_at
election_recognized_at
  = max(election_made_at, election_available_at, terms_available_at)
choice_dependent_phase_recognized_at
  = max(base_action_phase_recognized_at, election_recognized_at)
default_recognized_at
  = max(election_deadline_at, default_available_at, terms_available_at)
default_choice_dependent_phase_recognized_at
  = max(base_action_phase_recognized_at, default_recognized_at)
```

选择在截止前作出但到 valuation horizon 后才可得时，不得回填较早 phase。若 phase 尚未应在 current horizon 生效，只保留 `PENDING_ELECTION` future plan；若 current horizon 已要求 choice-dependent phase 而仍无有效选择，则在首事件前 `PRECHECK_BLOCKED`。截止后只能使用 action terms 已显式固定且内容寻址的 `default_choice_code/default_rule_id/default_rule_version/default_rule_hash/default_available_at`，并严格按上述 `default_recognized_at` 生效；没有显式 default 时为 `UNKNOWN_BLOCKED`，不得把缺失选择推断为 `DECLINE`。同一 journal prefix 至多一个 active election；同 identity 同字节幂等、异字节冲突。revision 只有 action terms 明确允许且 `revision_made_at <= election_deadline_at` 才合法；revised election 复用 `election_recognized_at=max(revision_made_at,revision_available_at,terms_available_at)`，并在自己可得后以 append-only reversal + replacement 生效，禁止覆盖或回写。

mark 固定为 `(observed_at, mark_available_at)`，`MARK_TO_MARKET.effective_at=max(observed_at,mark_available_at)`；external flow 固定自己的 `(economic_effective_at, flow_available_at, cash_available_at, cash_state_available_at)`，只有 `recognized_at=max(...)` 后才能改变现金。对 current-style research validation，任何输入都必须在相应 valuation/event 时点可得，不能用结束时已知事实回填期初。

受 Ledger V2 影响的 Stage 5C settlement moments 同样使用各自的 `(moment_effective_at, market_rule_available_at, state_available_at)`，分别派生 `buy_cash_paid_recognized_at`、`security_delivered_recognized_at`、`security_sellable_recognized_at`、`sell_cash_paid_recognized_at` 和 `sell_cash_available_recognized_at`，均为该状态三者的 `max` 且不得共用另一状态的 available time。首版任何 non-empty `special_exception_id` 仍先于这些计算失败关闭。

`ValuationPeriod` 固定 `beginning_at < ending_at <= injected_clock`。beginning state 是 `effective_at <= beginning_at` 的 canonical journal prefix，ending state 是 `effective_at <= ending_at` 的 prefix，因此本期事件唯一归属区间为 `(beginning_at, ending_at]`：恰好在 `beginning_at` 的事件已属于期初，恰好在 `ending_at` 的事件必须进入本期和期末；全链禁止再使用 `[beginning_at, ending_at)`。

输入集合必须声明明确的 strategy/account/security scope、覆盖起止时点、来源对象、来源字节 SHA-256 和 completeness。空集合只有在覆盖声明证明区间内确实为空时才合法；缺失适用公司行动、mark、external flow coverage 或 opening lot attribution 不得默认为零。mark scope/coverage/completeness/source hash 缺失或不可验证属于 `PRECHECK_BLOCKED`；只有 coverage 已完整证明、但某 valuation point 的持仓证券确实不存在合法历史 observation 时，才进入第 7 节的 `ABSTAIN + incomplete_pnl`。

## 5. Ledger V2 与逐证券全成本

### 5.1 Posting 与 lot 维度

Ledger V2 的 posting 至少区分：

```text
account
asset_unit = CNY | SHARE
security_id = null | exact security
debit / credit
```

posting 采用固定符号：`signed_delta = debit - credit`，每条 posting 只能一侧为严格正数，零 posting 禁止；每个事件分别满足 CNY 借方合计等于贷方合计、SHARE 借方合计等于贷方合计。以下 scope 与控制账户冻结为 Ledger V2 合同的一部分：

| asset/scope | 允许账户 |
|---|---|
| `CNY/null` | `CASH_AVAILABLE`、`CASH_RESERVED`、`CASH_SETTLED_UNAVAILABLE`、`EXTERNAL_CAPITAL`、`OPENING_CONTROL` |
| `CNY/security` | `CASH_RECEIVABLE`、`CASH_PAYABLE`、`SECURITY_COST`、`TRADE_CLEARING`、`REALIZED_PNL_CONTROL`、`FEE_EXPENSE_CONTROL`、`TAX_EXPENSE_CONTROL`、`CORPORATE_ACTION_RECEIVABLE`、`CORPORATE_ACTION_PAYABLE`、`CORPORATE_ACTION_CLEARING`、`CORPORATE_ACTION_INCOME_CONTROL`、`DIVIDEND_INCOME_CONTROL`、`OTHER_RECEIVABLE`、`OTHER_PAYABLE`、`OPENING_CONTROL` |
| `SHARE/security` | `SECURITY_UNSETTLED`、`SECURITY_UNSELLABLE`、`SECURITY_SELLABLE`、`SECURITY_CONTROL`、`OPENING_CONTROL` |

现金 bucket 和 external capital 必须是 `security_id=null`；交易/公司行动应收应付、成本、clearing、收入费用控制及证券数量必须绑定 exact security。双分录按资产单位平衡，逐证券成本、应收应付、clearing 和数量另行逐证券核对，禁止用 A 证券盈余抵消 B 证券缺口。`TRADE_CLEARING` 与 `CORPORATE_ACTION_CLEARING` 在各自处置事件结束时必须归零，差额进入显式 `REALIZED_PNL_CONTROL`；它们不能长期承载或隐藏 P&L。`OPENING_CONTROL` 只能使用 typed opening control amount，不得把计算残差当 plug。

每个 lot 必须保存不可变 acquisition lineage，以及以下 cost components：

```text
benchmark_principal
execution_slippage
fees
taxes
corporate_action_basis_adjustment
full_cost = sum(all cost components)
```

成本分量采用投资成本正号：`benchmark_principal >= 0`、`fees >= 0`、`taxes >= 0`；买入 `execution_slippage = quantity × (execution_price - benchmark_price)`，可以正负；`corporate_action_basis_adjustment` 可以正负，但必须由 action rule 证明且同一 action 的跨 lineage 转移总额闭合。每个仍存在的 lot 必须满足 `full_cost >= 0`；任何导致负 full cost、未解释 basis 产生/消失或不精确闭合的事件失败关闭。

opening lot 必须提供相同分量；若只有汇总 `full_cost`，可以继续完成数量/现金 ledger replay，但不得声称 complete P&L。首版 complete P&L 对分量缺失失败关闭，不引入 `unknown`、`other` 或自动补差桶。

### 5.2 费用资本化与处置

买入 fill 的执行本金、买入 fee 和买入 tax 全部进入该证券 `SECURITY_COST` 与对应 lot components；fee/tax 仍保留独立事件类型和归因身份。卖出 fee/tax 从应收中扣除并作为卖出期费用。卖出按 `acquired_at → lot_id` FIFO，同时按确定性比例移除被处置 lot 的每个成本分量；最后一笔处置必须精确耗尽剩余分量，不能留下舍入尾差。

每个会改变成本或 lot 的事件之后至少验证：

```text
for every security:
  sum(remaining lot cost components)
  = sum(remaining lot full_cost)
  = SECURITY_COST ledger balance for that security

sellable_quantity <= actual_quantity
actual_quantity = unsettled + unsellable + sellable
cash / receivable / payable / reservation identities all hold
```

任何不平为 `RECONCILIATION_BLOCKED`，不得生成 plug entry、改写旧 fill 或覆盖旧 lot。

### 5.3 完整事件优先级

Ledger V2 沿用并完整冻结以下排序优先级；排序键仍为 `effective_at → event_type_priority → ledger_event_id`：

| 事件 | priority |
|---|---:|
| `REVERSAL` | 5 |
| `OPENING_BALANCE` | 10 |
| `CASH_RESERVATION` | 20 |
| `SYNTHETIC_ORDER_ACCEPTED` | 30 |
| `TRADE_FILL` | 40 |
| `FEE` | 50 |
| `TAX` | 51 |
| `SYNTHETIC_ORDER_CANCELLED` | 60 |
| `CASH_RELEASE` | 70 |
| `TRADE_SETTLEMENT` | 80 |
| `SECURITY_AVAILABILITY` | 90 |
| `REPLACEMENT` | 95 |
| `CASH_DIVIDEND` | 100 |
| `SHARE_DISTRIBUTION` | 101 |
| `SPLIT_OR_CONSOLIDATION` | 102 |
| `RIGHTS_OR_ALLOTMENT` | 103 |
| `DELISTING_OR_CASH_OUT` | 104 |
| `MARK_TO_MARKET` | 105 |
| `EXTERNAL_CASH_FLOW` | 106 |

更正事件使用其实际获知/追加时点，不能把 reversal/replacement 伪造为早于原事件。Stage 5C replay 入口继续只接受其既有事件子集，并拒绝公司行动、mark 和 external flow；只有独立 Stage 5D replay policy 可以验证完整事件集合。

首版继续拒绝任何非空 settlement `special_exception_id`。只有未来内容寻址、版本化且由适用 `MarketRuleSet` 精确绑定的例外合同另获批准后，才可打开该路径；5D 不得用公司行动合同或自由文本 ID 绕过 settlement cycle。

### 5.4 Ledger V2 exact event semantic map v1

本表 identity 固定为 `event_semantic_map_id=stage5d_ledger_v2_exact_event_map`、`version=1.0.0`；未来 approved machine rules view 的该对象 canonical hash 必须进入每个 event 和 complete replay，任一字段变化必须升版并重新批准。本表是 closed-world allowlist。记 `D(A,x,s)` 为账户 `A` 借记 `x`、`C(A,x,s)` 为贷记；`s=null` 只用于账户级现金，其他示例均为 exact security。`X→Y(x)` 等于 `D(Y,x)+C(X,x)`。未列 posting、lot effect、phase 或账户一律禁止，金额为零的整组 posting 省略。基础变量固定为：

```text
q > 0
B = q * buy_benchmark_price
S_buy = q * (buy_execution_price - buy_benchmark_price)
G_buy = B + S_buy = q * buy_execution_price > 0
F_buy >= 0; T_buy >= 0; K_buy = G_buy + F_buy + T_buy

G_sell = q * sell_execution_price > 0
C_disposed = sum(exact FIFO disposed lot components) >= 0
F_sell >= 0; T_sell >= 0; P_sell = G_sell - F_sell - T_sell >= 0

gain(x) control close:
  if x >= 0: D(clearing,x) + C(REALIZED_PNL_CONTROL,x)
  if x < 0:  D(REALIZED_PNL_CONTROL,-x) + C(clearing,-x)
```

#### 5.4.1 Stage 5C 交易事件受影响语义

| 事件/phase | 唯一允许的 posting | lot effect 与强制时点 |
|---|---|---|
| `OPENING_BALANCE` | typed opening 中所有正资产借记、负债/控制贷记；差额只能由输入已声明且独立闭合的 `OPENING_CONTROL` 平衡 | 每个 opening lot 一条 `+q/+sellable/components/full_cost`；`effective_at=opening_as_of`；禁止计算残差 plug |
| `CASH_RESERVATION/BUY` | `CASH_AVAILABLE→CASH_RESERVED(R)`，且 `R >= K_buy` | 无 lot；`submitted_at` |
| `SYNTHETIC_ORDER_ACCEPTED` | 空 | 空；只绑定 order/approval/rule/source hashes |
| `TRADE_FILL/BUY` | `D(SECURITY_COST,G_buy,s)+C(CASH_PAYABLE,G_buy,s)`；`D(SECURITY_UNSETTLED,q,s)+C(SECURITY_CONTROL,q,s)` | 创建唯一 fill lot：`+q, sellable+0, B, S_buy, fee=0, tax=0, basis=0, full=G_buy`；`filled_at` |
| `FEE/BUY` | `D(SECURITY_COST,F_buy,s)+C(CASH_PAYABLE,F_buy,s)` | 同一 fill lot `fees += F_buy; full += F_buy`；`filled_at` |
| `TAX/BUY` | `D(SECURITY_COST,T_buy,s)+C(CASH_PAYABLE,T_buy,s)` | 同一 fill lot `taxes += T_buy; full += T_buy`；`filled_at` |
| `TRADE_FILL/SELL` | `D(CASH_RECEIVABLE,G_sell,s)+C(TRADE_CLEARING,G_sell,s)`；`D(TRADE_CLEARING,C_disposed,s)+C(SECURITY_COST,C_disposed,s)`；`D(SECURITY_CONTROL,q,s)+C(SECURITY_SELLABLE,q,s)`；最后按 `gain(G_sell-C_disposed)` 归零 `TRADE_CLEARING` | exact FIFO lots：`-q/-sellable`，五个 cost components 与 full cost 按规则 5.2 移除；`filled_at` |
| `FEE/SELL` | `D(FEE_EXPENSE_CONTROL,F_sell,s)+C(CASH_RECEIVABLE,F_sell,s)` | 无 lot；`filled_at`；只减少本 fill 应收 |
| `TAX/SELL` | `D(TAX_EXPENSE_CONTROL,T_sell,s)+C(CASH_RECEIVABLE,T_sell,s)` | 无 lot；`filled_at`；只减少本 fill 应收 |
| `SYNTHETIC_ORDER_CANCELLED` | 空 | 空；释放现金必须是独立 `CASH_RELEASE` |
| `CASH_RELEASE/UNUSED_BUY_RESERVE` | `CASH_RESERVED→CASH_AVAILABLE(R-K_buy)` | 无 lot；buy cash payable recognized time |
| `TRADE_SETTLEMENT/BUY_CASH` | `D(CASH_PAYABLE,K_buy,s)+C(CASH_RESERVED,K_buy,null)` | 无 lot；`buy_cash_paid_recognized_at` |
| `TRADE_SETTLEMENT/BUY_SECURITY` | `SECURITY_UNSETTLED→SECURITY_UNSELLABLE(q)` | 无 cost change；`security_delivered_recognized_at` |
| `SECURITY_AVAILABILITY/BUY` | `SECURITY_UNSELLABLE→SECURITY_SELLABLE(q)` | 同 lot `sellable += q`；`security_sellable_recognized_at` |
| `TRADE_SETTLEMENT/SELL_CASH` | 若 `paid_recognized_at < cash_available_recognized_at`：`D(CASH_SETTLED_UNAVAILABLE,P_sell,null)+C(CASH_RECEIVABLE,P_sell,s)`；若二者相等：直接 `D(CASH_AVAILABLE,P_sell,null)+C(CASH_RECEIVABLE,P_sell,s)` | 无 lot；`paid_recognized_at`；同刻 direct 形式禁止另建 release |
| `CASH_RELEASE/SELL_CASH_AVAILABLE` | 仅当 `paid_recognized_at < cash_available_recognized_at`：`CASH_SETTLED_UNAVAILABLE→CASH_AVAILABLE(P_sell)` | 无 lot；`cash_available_recognized_at` |
| `REVERSAL` | 原事件全部 posting 借贷严格互换 | 原 lot effect 五分量和数量逐项取反；绑定唯一 original event；只在 correction available time 追加 |
| `REPLACEMENT` | 按本表重新验证的新事件 exact postings | 按本表的新 lot effects；一对一绑定已接受 reversal/original，禁止原地覆盖 |

上述 `FEE/TAX` market fill 语义不适用于公司行动。公司行动 fee/tax 必须是独立 typed source component，但为避免 priority `50/51` 在同刻早于 action `100—104`，其 ledger posting 必须并入相应 action phase 的 compound event；不得伪造成更早的 standalone `FEE/TAX` ledger event。

#### 5.4.2 Stage 5D 事件语义

公司行动金额记 `G_action` 为应确认的 gross cash，`C_action` 为被处置 lot 的 full cost，`Q_action` 为 exact entitlement quantity，`K_rights` 为配股本金加 typed acquisition fee/tax。现金从应收到可用的共同 phase 固定为：`PAID: D(CASH_SETTLED_UNAVAILABLE,P,s=null)+C(CORPORATE_ACTION_RECEIVABLE,P,s)`；`AVAILABLE: CASH_SETTLED_UNAVAILABLE→CASH_AVAILABLE(P)`。若 `paid_recognized_at == cash_available_recognized_at`，两步规范折叠为 `D(CASH_AVAILABLE,P,null)+C(CORPORATE_ACTION_RECEIVABLE,P,s)`。同一 action 的其他相邻 phase 若 recognized time 相同，也必须代数合并为一个 canonical compound event，禁止依赖同 priority 下 hash/event-id 的偶然顺序。

| 事件/phase | 唯一允许的 posting | lot effect、成本与时点 |
|---|---|---|
| `CASH_DIVIDEND/RECOGNIZE` | `D(CORPORATE_ACTION_RECEIVABLE,G_action,s)+C(DIVIDEND_INCOME_CONTROL,G_action,s)`；若 typed fee/tax `F/T` 同刻已确定，再加 `D(FEE_EXPENSE_CONTROL,F,s)+D(TAX_EXPENSE_CONTROL,T,s)+C(CORPORATE_ACTION_RECEIVABLE,F+T,s)` | 无 lot；`recognized_at`；应收净额 `P=G_action-F-T`，gross dividend、fee 与 tax 保持三个唯一 P&L cells |
| `CASH_DIVIDEND/PAID_OR_AVAILABLE` | 使用共同 cash phases，金额为当时 exact outstanding receivable | 无 lot；分别使用 `paid_recognized_at/cash_available_recognized_at` |
| `SHARE_DISTRIBUTION/RECOGNIZE` | `D(SECURITY_UNSETTLED,Q_action,s)+C(SECURITY_CONTROL,Q_action,s)` | 按 entitlement lots 比例追加 quantity lineage；五个成本分量均不增不减，总 full cost 不变；`recognized_at` |
| `SHARE_DISTRIBUTION/DELIVERED` | `SECURITY_UNSETTLED→SECURITY_UNSELLABLE(Q_action)` | 无 cost change；`security_delivered_recognized_at` |
| `SHARE_DISTRIBUTION/SELLABLE` | `SECURITY_UNSELLABLE→SECURITY_SELLABLE(Q_action)` | 对应 lots `sellable += Q_action`；`security_sellable_recognized_at` |
| `SPLIT_OR_CONSOLIDATION/RECOGNIZE` | 对每个现有 quantity bucket 的 exact `delta_q`：增加时 `D(bucket,delta_q)+C(SECURITY_CONTROL,delta_q)`，减少时反向 | 每个受影响 lot/bucket 乘 exact rational ratio；五个成本分量和 full cost 绝对额保持不变；`recognized_at` |
| `RIGHTS_OR_ALLOTMENT/DECLINE` | 空 | 空；保存 election/action/rule hashes；`recognized_at` |
| `RIGHTS_OR_ALLOTMENT/EXERCISE_RECOGNIZE` | `CASH_AVAILABLE→CASH_RESERVED(K_rights)`；`D(SECURITY_COST,K_rights,s)+C(CORPORATE_ACTION_PAYABLE,K_rights,s)`；`D(SECURITY_UNSETTLED,Q_action,s)+C(SECURITY_CONTROL,Q_action,s)` | 立即创建 unsettled action lot：`+Q_action, sellable+0, benchmark principal/fee/tax` 与 `full=K_rights` 精确闭合，使 entitlement market value 与 payable 同时进入 NAV；`recognized_at`；slippage/basis 固定为零，除非另有获批 basis allocation rule |
| `RIGHTS_OR_ALLOTMENT/PAID` | `D(CORPORATE_ACTION_PAYABLE,K_rights,s)+C(CASH_RESERVED,K_rights,null)` | 无 lot；`paid_recognized_at` |
| `RIGHTS_OR_ALLOTMENT/DELIVERED` | `SECURITY_UNSETTLED→SECURITY_UNSELLABLE(Q_action)` | 不改变 cost/lot full cost；`security_delivered_recognized_at` |
| `RIGHTS_OR_ALLOTMENT/SELLABLE` | `SECURITY_UNSELLABLE→SECURITY_SELLABLE(Q_action)` | 对应 lot `sellable += Q_action`；`security_sellable_recognized_at` |
| `DELISTING_OR_CASH_OUT/RECOGNIZE` | `D(CORPORATE_ACTION_RECEIVABLE,G_action,s)+C(CORPORATE_ACTION_CLEARING,G_action,s)`；`D(CORPORATE_ACTION_CLEARING,C_action,s)+C(SECURITY_COST,C_action,s)`；按 `gain(G_action-C_action)` 归零 clearing；数量按各 bucket `D(SECURITY_CONTROL,q_bucket)+C(bucket,q_bucket)` | exact eligible lots 全量/部分处置，逐项移除数量、sellable 与五成本分量；`recognized_at` |
| `DELISTING_OR_CASH_OUT/PAID_OR_AVAILABLE` | 使用共同 cash phases；同刻 typed fee/tax 先从 receivable 扣减并借记对应 expense control，再支付净额 | 无 lot；分别使用 cash state 自身 recognized time |
| `CASH_IN_LIEU` 子语义 | 必须嵌入来源 `SHARE_DISTRIBUTION` 或 `SPLIT_OR_CONSOLIDATION` event，完全复用 cash-out 的 receivable/clearing/realized-control、fractional cost removal 与 cash phases | 只处置明确 fractional quantity/cost；gross cash 固定进入 corporate-action-cash P&L cell；禁止把净额或零成本当 gross |
| 独立、无成本基础处置的公司行动现金 | `D(CORPORATE_ACTION_RECEIVABLE,G_action,s)+C(CORPORATE_ACTION_INCOME_CONTROL,G_action,s)`；同 phase typed `F/T` 借记对应 expense control、贷记 receivable；随后以净应收使用共同 cash phases | 无 lot；只允许 typed action 明确证明“不处置任何 security cost basis”；gross、fee、tax 各进唯一 P&L cell |
| `MARK_TO_MARKET` | 空；严格 memo | 空；绑定 mark observation/rule/source；`effective_at=max(observed_at,mark_available_at)` |
| `EXTERNAL_CASH_FLOW/DEPOSIT` | `D(CASH_AVAILABLE,G_flow,null)+C(EXTERNAL_CAPITAL,G_flow,null)` | 空；`effective_at=max(flow economic/knowledge/cash-state times)`；不得进入 P&L |
| `EXTERNAL_CASH_FLOW/WITHDRAWAL` | `D(EXTERNAL_CAPITAL,G_flow,null)+C(CASH_AVAILABLE,G_flow,null)` | 空；同上；余额不足失败关闭 |

每个 action phase 必须绑定 `action_id/election_id/source_hash/rule_hash/phase/economic_at/state_available_at/recognized_at`。任何 fee/tax、fractional quantity、basis allocation、paid amount 或 delivered/sellable amount不能由净额倒推。未覆盖分支、同刻不能按上述 compound rule 唯一合并、clearing 未归零、应收应付为负或 event/lots/postings 不满足本表时，整个 action 在产生第一条 accepted event 前 `PRECHECK_BLOCKED`。

## 6. 五类公司行动

### 6.1 共同合同

公司行动集合必须覆盖账户内全部证券和 valuation period，固定 action id、类型、证券、第 4 节每个状态自己的经济/知识时点、精确比例或现金条款、来源字节、官方条款引用、适用 lot 范围、选择要求、分数股规则及 canonical hash。确认、支付、现金可用、证券交付和可卖严格使用第 4 节各自 `*_recognized_at`；所有 choice-dependent phase 还必须使用 `max(base_action_phase_recognized_at,election_recognized_at)`。禁止复用 action-wide `available_at`，也禁止获知后把事件或选择静默插回更早的 PIT journal。

资格数量必须由 action terms 与适用 MarketRuleSet 明确说明登记时点、trade/settlement status、未交收证券、受限/不可卖证券及其他例外是否享有权利，再从对应 journal prefix 派生；`sellable` 不能代替 entitlement。任何 unsettled 或特殊证券的资格无法由版本化条款证明时，整个 action 失败关闭，不能采用“通常如此”的默认值。

适用但无法完整建模、覆盖不完整、时点冲突、同一 action/election identity 内容冲突、比例或现金条款缺失、选择或显式 default 缺失、截止后非法选择、revision 不合法或来源 hash 漂移，均在产生任何公司行动事件前失败关闭。复权价格不得作为 fill、mark、lot cost 或现金流来源。

### 6.2 `CASH_DIVIDEND`

分红资格数量从 entitlement cutoff 前的 journal prefix 派生。确认、typed fee/withholding tax、支付与现金可用严格执行第 5.4.2 节 exact phases：确认后的合法应收进入 NAV，未来支付不能提前成为现金；已支付但未可用的现金只进入 `CASH_SETTLED_UNAVAILABLE`。费用和税必须各有独立 typed source/component，但 ledger posting 并入对应 action compound phase，不能从净股息倒推未知费率/税率或创建同刻早于应收的 standalone `FEE/TAX` posting。

### 6.3 `SHARE_DISTRIBUTION`

送股或转增以 append-only lot lineage 增加数量，不修改原 fill。首版同证券分配按第 5.4.2 节在 recognized/delivered/sellable 三个 PIT phase 间移动，保持五个成本分量和总 full cost 不变，并按原 lot 建立可追踪 action effect；若产生不同证券、成本分配规则缺失或分数股处理未知，则失败关闭，不自动设零成本。

### 6.4 `SPLIT_OR_CONSOLIDATION`

拆股与合股使用精确有理数比例调整各 quantity bucket 和 lot 数量，五个成本分量绝对额及总成本不变。分数股必须由 action terms 与适用市场规则明确决定保留、舍弃或按第 5.4.2 节 cash-in-lieu 子语义处置；任何舍入、basis allocation 和现金替代都要独立来源并精确闭合，不能静默截断。

### 6.5 `RIGHTS_OR_ALLOTMENT`

配股、供股或权利分配必须绑定第 4 节完整选择合同。首版只允许条款明确的 `DECLINE`、`EXERCISE` 或 `MANDATORY`；`DECLINE/EXERCISE` 属于 `CHOICE_REQUIRED`，其 phase 不得早于 `election_recognized_at`，`MANDATORY` 不接受 caller choice。`EXERCISE` 必须按第 5.4.2 节依次形成现金预留+应收应付、支付、证券交付、新 lot 和可卖 phase，subscription fee/tax 资本化且全程不创建市场 order/fill。需要卖出权利或其他市场交易的选择不属于公司行动快捷路径，缺少独立执行合同即失败关闭。

### 6.6 `DELISTING_OR_CASH_OUT`

退市、强制现金收购或自愿 cash-out 必须明确强制性、选择、资格 lot、gross cash 条款、移除数量，以及 recognition/paid/cash-available 各自 PIT 时点。强制退出为 `MANDATORY`；自愿 `ACCEPT_CASH/DECLINE` 为 `CHOICE_REQUIRED`，choice-dependent phase 不得早于 `election_recognized_at`。按第 5.4.2 节移除 lot 五成本分量、归零 corporate-action clearing 并形成 realized attribution；支付事实可得前保留应收，已支付未可用时保留 `CASH_SETTLED_UNAVAILABLE`。未知退出价格、未来复牌价、零价回填、把净额冒充 gross、缺失选择或把缺失推断为 `DECLINE` 均不允许清零持仓。

## 7. 未复权 mark 与 NAV

每个 valuation point、该 prefix 中每个 `actual_quantity > 0` 的证券，只能选择同时满足以下条件的 mark；`actual_quantity == 0` 的证券在该点 market value 精确为零且不要求 mark：

1. `observed_at <= valuation_at` 且 `available_at <= valuation_at`；
2. 来源和内容 hash 已验证；
3. 价格严格大于零、合法且未复权；
4. 证券、市场、session state 和规则 scope 精确匹配；
5. 是 valuation point 前最后一条合法观察。

结果优先级固定为：首先验证 mark scope/coverage/completeness/source hash、identity、PIT 和同刻唯一性，缺失、不可验证、畸形、时点矛盾或同一 `observed_at` 不同 canonical 内容均为 `PRECHECK_BLOCKED`；其次重放并验证 ledger，任何不平为 `RECONCILIATION_BLOCKED`；最后只在完整合法 coverage 中选择 observation。相同规范字节可幂等。停牌时只有有效 `SecuritySessionState` 证明 mark 后持续停牌，才可沿用最后合法 mark，并必须保存 `stale=true`、`stale_since`、时长、状态来源和 mark 来源。stale mark 只用于估值，始终 `executable=false`。

coverage 完整且 ledger 已对账，但任一 valuation point 的持仓证券没有历史合法 mark 时，整个账户 valuation/P&L 必须返回 `ABSTAIN + incomplete_pnl`，不得只输出其他证券的 partial NAV/P&L；不得使用零价、期末后 mark、未来复牌价、复权价或 proposal/fill price 自动回填。`unreconciled cell`、cost/cash/equity 不平或 forbidden cell 非零永远是 `RECONCILIATION_BLOCKED`，不得降级为 mark-missing `ABSTAIN`。

`MARK_TO_MARKET` 是带 typed mark payload 的 append-only memo event，不修改现金、数量或历史成本；所有有余额影响的事件仍必须双分录平衡。mark 更正也只能使用 reversal/replacement，不能覆盖旧 observation。

每个 valuation point 从同一 journal prefix 派生：

```text
settled_cash = cash_available + cash_reserved + cash_settled_unavailable
position_market_value = sum(actual_quantity * selected_unadjusted_mark)

equity = settled_cash
       + trade_cash_receivable
       - trade_cash_payable
       + corporate_action_receivable
       - corporate_action_payable
       + position_market_value
       + other_receivable
       - other_payable
```

账户到 NAV 的映射是 closed-world：`trade_cash_receivable/payable` 分别且只分别取 `CASH_RECEIVABLE/CASH_PAYABLE`，`corporate_action_receivable/payable` 分别且只分别取 `CORPORATE_ACTION_RECEIVABLE/CORPORATE_ACTION_PAYABLE`，`other_receivable/payable` 分别且只分别取 `OTHER_RECEIVABLE/OTHER_PAYABLE`；每个余额恰好进入一次。证券用 market value 替代历史 cost，因此 `SECURITY_COST` 不再另加；所有 cash/security/corporate-action clearing、quantity/control、P&L control 和 `EXTERNAL_CAPITAL` 账户均不直接进入 equity。外部入出金只通过已改变的 cash 余额进入 NAV，`EXTERNAL_CAPITAL` 只作资本对手和 period external-flow reconciliation；公司行动应收应付不得混入 trade clearing 或 P&L。beginning 与 ending valuation 必须从同一规范 journal 的两个前缀计算，caller-supplied NAV 只用于交叉核对，不是权威余额。

## 8. 二维 P&L 矩阵

### 8.1 累计量、符号与唯一事实

P&L 采用 `realization × driver` 二维矩阵：

```text
realization rows = realized | unrealized | non_position_income

driver columns = price
               | slippage
               | fee
               | tax
               | cash_dividend
               | corporate_action_cash
```

所有金额以“增加 equity/P&L 为正、减少为负”。对同一 strategy/account/security 的 canonical journal prefix `J(t)`，定义：

```text
TB(t) = 累计普通卖出 benchmark gross proceeds
TS(t) = 累计普通卖出 q * (execution_price - benchmark_price)

DB/DS/DF/DT/DA(t)
      = 累计所有已处置 lot 的 benchmark principal / acquisition slippage /
        acquisition fee / acquisition tax / corporate-action basis adjustment
SF/ST(t) = 累计卖出或处置当期 fee / tax（不属于 acquisition lot cost）
CAD(t)   = 累计处置 security cost basis 的 gross corporate-action cash

MV(t) = 当前 remaining quantity * 合法未复权 mark
RB/RS/RF/RT/RA(t) = remaining lots 的五个 cost components

NF/NT(t) = 累计不处置 security cost basis 的收入相关 fee / tax
DIV(t)   = 累计 gross cash dividend income
CAI(t)   = 累计不处置 security cost basis 的 gross corporate-action income
```

`corporate_action_basis_adjustment` 唯一归属 `price` driver：disposed 为 `-DA`，remaining 为 `-RA`；它不得进入 `corporate_action_cash`。公司行动现金列始终保存 gross cash，不保存扣除 basis/fee/tax 后的净 P&L。所有 acquisition fee/tax 只通过 `DF/DT/RF/RT` 进入唯一 cell；sell/action fee/tax 只通过 `SF/ST/NF/NT` 进入唯一 cell。

`Stage5PnlCell` 是按 `(strategy_id, account_fixture_id, security_id, as_of, realization, driver)` 聚合的唯一可加总事实；每个 as-of 必须物化完整十八格。逐 source event/lot/action 的 lineage 使用独立 `Stage5PnlContribution`，identity 固定为 `(strategy_id, account_fixture_id, security_id, as_of, realization, driver, formula_term, source_event_id, source_lot_id|null, source_action_id|null)`；`formula_term` 只能是 `TB/TS/DB/DS/DF/DT/DA/SF/ST/CAD/MV/RB/RS/RF/RT/RA/NF/NT/DIV/CAI` 之一。`DB/DS/DF/DT/DA/MV/RB/RS/RF/RT/RA` 每个 source×lot×term 恰好一条；`TB/TS/SF/ST/CAD/NF/NT/DIV/CAI` 是 event/action-level，`source_lot_id=null` 且每个 source×term 恰好一条，禁止把 proceeds 任意分摊到 lots。重复 identity 或无法绑定来源失败关闭。contribution signed amounts 必须精确加总到 cell，不能把 `source_event_id` 放进聚合 cell identity 后再对不同 period cell 直接相减。row marginal、column marginal 和 grand total 都只是 derived disclosure，不是可再次相加事实。

### 8.2 十八格 closed-world signed formula

本表 identity 固定为 `pnl_formula_map_id=stage5d_pnl_3x6_signed_formula_map`、`version=1.0.0`，canonical hash 必须进入每个 P&L envelope 与 complete replay。下表恰好十八格；`FORBIDDEN` 格必须物化为 exact Decimal zero 且不得有 contribution，非零即 `RECONCILIATION_BLOCKED`。

| realization | driver | allowed | cumulative signed formula at `t` |
|---|---|---:|---|
| `realized` | `price` | yes | `TB(t) - DB(t) - DA(t)` |
| `realized` | `slippage` | yes | `TS(t) - DS(t)` |
| `realized` | `fee` | yes | `-SF(t) - DF(t)` |
| `realized` | `tax` | yes | `-ST(t) - DT(t)` |
| `realized` | `cash_dividend` | no | `0 (FORBIDDEN)` |
| `realized` | `corporate_action_cash` | yes | `CAD(t)` gross only |
| `unrealized` | `price` | yes | `MV(t) - RB(t) - RA(t)` |
| `unrealized` | `slippage` | yes | `-RS(t)` |
| `unrealized` | `fee` | yes | `-RF(t)` |
| `unrealized` | `tax` | yes | `-RT(t)` |
| `unrealized` | `cash_dividend` | no | `0 (FORBIDDEN)` |
| `unrealized` | `corporate_action_cash` | no | `0 (FORBIDDEN)` |
| `non_position_income` | `price` | no | `0 (FORBIDDEN)` |
| `non_position_income` | `slippage` | no | `0 (FORBIDDEN)` |
| `non_position_income` | `fee` | yes | `-NF(t)` |
| `non_position_income` | `tax` | yes | `-NT(t)` |
| `non_position_income` | `cash_dividend` | yes | `DIV(t)` gross only |
| `non_position_income` | `corporate_action_cash` | yes | `CAI(t)` gross only |

普通卖出贡献由 `TB+TS` 形成 gross execution proceeds，再由五个 disposed acquisition components 和 `SF/ST` 扣减。退市 cash-out、分数股 cash-in-lieu 或其他 basis disposal 不产生 `TB/TS`，其 gross cash 只进入 `CAD`，disposed `DB/DS/DF/DT/DA` 与处置 fee/tax 仍按各自 driver 扣减。因此同一 gross cash、basis、fee、tax、slippage 各进入且只进入一格；gross 与 net 不得互换。条款不能证明是否处置成本基础时，整个 action `PRECHECK_BLOCKED`。

### 8.3 期间矩阵与两 prefix 恒等式

期间归因严格使用第 4 节 `(beginning_at, ending_at]` 与两个 inclusive prefix：

```text
beginning_matrix = cumulative_matrix(J(beginning_at))
ending_matrix    = cumulative_matrix(J(ending_at))
period_cell[r,d] = ending_cell[r,d] - beginning_cell[r,d]

period_total_pnl = ending_equity
                 - beginning_equity
                 - net_external_cash_inflow

period_total_pnl = sum(period_matrix cells exactly once)
```

恰好在 `beginning_at` 的事件同时存在于两个 prefix，period contribution 为零；恰好在 `ending_at` 的事件只存在于 ending prefix，必须进入本期。这使期初未实现收益在期间卖出时只发生 realized/unrealized 重分类，不把持仓建立以来的历史收益重复计入本期。external flow 只改变资本，不进入任何 matrix cell；交易现金、股息和公司行动现金不得伪装为 external flow。

security-level P&L 先逐证券闭合，再汇总到账户；跨证券成本和归因不得互相补差。只有完整 mark coverage 中缺少合法 observation 且 ledger 已对账时，才返回 `ABSTAIN + incomplete_pnl`；成本、现金、任一 contribution/cell/formula、矩阵或 equity 恒等式不平固定为 `RECONCILIATION_BLOCKED`。任何 incomplete 结果都必须保留缺失证据和 reason codes，但不得声称 complete P&L。

## 9. Complete replay 与 audit replay

`complete` 只表示对显式 horizon 完整：所有 `effective_at <= ending_at <= injected_clock` 且 PIT 可得的事件均已排序、重放和对账。未来 settlement、availability、公司行动支付或其他 scheduled events 可以保留在独立 plan 中，但不能进入 current ledger、NAV 或 P&L。

`Stage5CompleteReplayEnvelope` 使用显式 allowlist，而不是直接 hash 任意 Python result。至少绑定：

- 本包未来 approved identity、Stage 5A 精确身份和 Stage 5C baseline commit；
- exact Stage 4、Stage 5B/5C 原始 case、规则、target、approval、candidate、constraint、order 和 fill identities；
- MarketRuleSet、TradingCalendar、SecuritySessionState、market observations、CostSchedule、ImpactCurve；
- opening account/lot attribution、公司行动/选择、mark、external flow、全部 accepted ledger events 和 journal heads；
- beginning/ending valuation、二维 P&L、失败或完整状态；
- 实际 `code_commit`、`config_hash`、Decimal/rounding identity、purpose 和 injected clock。

明确排除墙钟噪声、进程号、线程号、机器路径、工作树路径、日志位置、SQLite rowid、字典插入顺序、网络端点和数据库连接参数。相同规范输入必须得到相同事件、状态、矩阵和 replay hash；任一承重输入变化必须改变相应 hash。

`audit_replay` 必须绑定原 `source_replay_id/hash`、原规则、原代码、原输入和原 horizon，只验证能否精确复现；不得使用当前规则、当前 mark 或当前 Release 状态重新判断旧结果。输出固定 `audit_only=true`、`authority_eligible=false`，不形成新的 current decision、target、approval、position、fill、NAV/P&L 权威或 journal head。`audit_replay` 严格零写：不得调用 5D-2，不得创建或更新 artifact、membership、ledger event、account generation、缓存或任何 SQLite 行，即使复现成功也只能返回内存结果。新规则重算必须是独立 `new_research_validation`。

## 10. SQLite v4 原子持久化

### 10.1 同库迁移

5D-2 只允许把 `STORAGE_SCHEMA_VERSION` 从 `3` 原子迁移到 `4`，目标仍为 `var/state/invest_system.sqlite3`。v4 的完整新增表面精确限定为以下六表，不得用隐式第七表、第二数据库或文件旁路拆开原子边界：

```text
stage5_artifacts
stage5_run_aggregates
stage5_run_artifacts
stage5_ledger_events
stage5_run_ledger_events
stage5_account_generations
```

`stage5_artifacts` 保存内容寻址的 canonical artifacts；`stage5_run_aggregates` 保存 complete replay root/seal；`stage5_run_artifacts` 保存 root 到 artifact 的有序、typed role membership；`stage5_ledger_events` 保存不可变 projected/accepted events；`stage5_run_ledger_events` 保存 run 内事件次序和处置状态；`stage5_account_generations` 保存 strategy/account generation、expected prior head 与新 journal head。一次原子组必须覆盖 StrategyRunManifest、Stage 4/5 全部 canonical role artifacts、projected 与 accepted events、marks、valuation、二维 P&L、complete replay 和新 generation/head；零事件的完整 run 仍显式保存空的 ordered memberships，不能靠缺行猜测。

v4 不复制 KB 事实表，不保存可变计算缓存为权威。v3 表、约束和历史数据必须原样保留；只支持经过测试的 `3 → 4`，未知版本、漂移 schema 或半迁移状态失败关闭。

### 10.2 幂等、冲突与并发

同一 replay id/hash 和同一 canonical bytes 的重复写为幂等；相同 replay id、ledger event id、idempotency key 或 artifact hash 对应不同内容为冲突。写入使用单连接并固定 `journal_mode=WAL`、`synchronous=FULL`、foreign keys、显式有界 `busy_timeout` 和 `BEGIN IMMEDIATE`，验证唯一约束、expected prior journal head 和当前 account head；并发 writer 只有一个可从同一 expected head 前进，失败方回滚后重新读取，不做 last-write-wins。

semantic config 与 SQLite operational config 必须分离。规则、schema、Decimal、rounding 和影响 canonical 结果的配置进入 `config_hash`；数据库路径、WAL/synchronous、timeout、连接和重试参数只属于 operational config，不得改变 canonical bytes、事件或 P&L，也不得混入 replay identity。目标路径仍由 InvestSystem 配置解析并限制在自有 state surface；运行参数不满足上述安全下限时失败关闭。

### 10.3 一次提交或零写

写入前，5D-2 必须用批准的 typed codec 对 5D-1 envelope 和每个 member 执行 encode → decode → canonical re-encode，并重新验证 type/schema、role allowlist、content hash、root/member/event 次序、cross-reference、journal head 和关键 semantic invariants；禁止以通用 JSON 字典或数据库行形状替代 typed verification。写入后必须从六表 read-back，经同一 typed codec 解码、规范重编码和语义复验，字节与 hash 全部一致才可提交。

一个 complete replay 的 Manifest、Stage 4/5 canonical roles、projected/accepted events、marks、valuation、P&L、replay root/membership 和新 journal head 必须在同一事务中一次提交。只有 `pnl_complete=true`、全部 reconciliation 已通过且无资金/持仓变化的完整业务 `BLOCKED` 或 `ABSTAIN` run 可以 sealed 持久化以供审计，并且不得推进资金或持仓状态；mark 缺失产生的 `ABSTAIN + incomplete_pnl` 不调用 5D-2。技术错误、codec/schema/hash/identity 冲突、并发冲突、`RECONCILIATION_BLOCKED`、任何 `incomplete_pnl`、磁盘/SQLite 错误、进程中断或 read-back 不一致全部零写，不得留下可见 seal/root、孤儿 member、部分 journal、P&L 或推进后的 head。禁止通过删除历史事件恢复；恢复只允许重试同一幂等事务或追加合法 reversal/replacement。

## 11. Golden matrix 与验收

5D-1 至少覆盖：零持仓现金账户、买入费用资本化、跨 valuation 的 T+1、部分/全部 FIFO 卖出、多证券 NAV、分红确认与支付、送股、拆股、合股及分数股、配股选择缺失/截止/default/行权、自愿 cash-out 选择、选择 revision、退市 cash-out、停牌 stale mark、mark coverage 缺失与 coverage 完整但无合法 observation、已清仓证券期末无需 mark、外部入金/出金、公司行动/mark/external-flow revision、未来事件和未来选择不泄漏、closed-world account-to-NAV、逐证券成本和 P&L 对账、相同输入同 hash、承重输入漂移改 hash、运行噪声不改 hash、audit replay 精确复现。

第 5.4 节每一 event/phase 必须各有 exact happy case、缺 posting、额外 posting、错误 security scope、错误借贷符号、lot 分量漂移、clearing 不归零、同刻 compound 与未来 phase 不泄漏 case。第 8.2 节必须用固定数值分别验证普通卖出、remaining lot、gross dividend、退市 gross cash、fractional cash-in-lieu、独立公司行动收入、正负 acquisition slippage、非零 corporate-action basis adjustment、sell/action fee/tax，并逐一断言十八格公式、十三个允许格、五个 forbidden-zero 格、source contribution 汇总和零双计。

PIT golden 必须分别移动 terms/economic/entitlement/paid/cash-available/delivered/sellable 的 economic 与 available 时点，证明每个 phase 只在自己的 `*_recognized_at` 出现。期间边界至少固定三例：`effective_at == beginning_at` 只在两个 prefix 中共同存在、period contribution 为零；`beginning_at < effective_at < ending_at` 进入本期；`effective_at == ending_at` 必须进入 ending prefix 与本期。任何 `[beginning_at,ending_at)` 实现必须测试失败。

5D-2 另须覆盖干净 v3→v4、重复 migration、未知版本、schema drift、同内容幂等、同 key 不同内容、expected-head 冲突、双 writer 竞争、事务各阶段失败注入、重开数据库 read-back、零孤儿/零 partial root，以及全部 v3 storage 回归。

验收必须同时运行 Stage 5A governance、Stage 5B、Stage 5C、Stage 5D 专项、Ruff、format、mypy、compileall、全仓 pytest 和 `git diff --check`。任何 5D 通过都不等于 Stage 6 backtest 获准。

## 12. 当前明确禁止

在第 13 节全部批准且 approved machine artifacts 形成前，禁止：

- 新增 Stage 5D evaluator、typed runtime rules、公司行动/mark/P&L 业务代码；
- 修改 Ledger、fill projection、storage schema 或创建 migration；
- 把本文、配套零权限 draft JSON 或历史材料作为运行规则解析；
- 写入 `var/state/invest_system.sqlite3` 或创建替代数据库；
- 用调用者提交的 Stage 5C result、NAV、P&L 或 PASS 跳过内部重算；
- 用未知成本桶、自动补差、零价、未来价、复权价或当前规则回填历史；
- 读取 KB 内部状态、真实行情、真实账户、券商或交易凭据；
- 授权 backtest、paper、shadow、live、真实仓位、真实订单或资金部署。

## 13. Owner 逐项批准清单

以下恰好四十八项当前全部为待批准且可逐项审阅；勾选框和状态不得在没有 owner 明确批准的情况下修改。授权判定只能是整包原子 `all(5D-01..5D-48 == approved)`：任一 pending/rejected/缺失、不同 approval record 或不同 bundle/document hash 都使整包保持 `draft + zero_runtime_authority`；禁止签发 partial capability 或仅实现获批子集。

### A. 范围、谱系与实施顺序

- [ ] `5D-01`：批准本包仍只属于 `stage5_synthetic_execution_validation`、匿名合成 `research`、`validation_only`，当前 draft 为 `zero_runtime_authority`；四十八项只能在同一 exact bundle/document/approval record 中整包原子授权，partial capability/部分实现授权禁止，且任何未来 capability 不得继承 Stage 2B、Stage 4 或 Stage 5B/5C capability。
- [ ] `5D-02`：批准精确固定第 2.1 节 Stage 5A bundle/rules/approval/specification/document identities，保留全部既有 Stage 5A 文件原始字节不变；任一身份漂移必须重新批准。
- [ ] `5D-03`：批准 Stage 5C 行为基线精确固定为 Git commit `7f64c584c5c7be5e2385a177fab9e5d31e3f665b`，Ledger V2 改动必须提升 schema、绑定实际 code commit 并重验 Stage 5A—5C。
- [ ] `5D-04`：批准先完成无 I/O、无 SQLite、无副作用的 `5D-1 pure complete replay`，只有其独立验收通过后才允许开始 `5D-2 SQLite v4 atomic persistence`。
- [ ] `5D-05`：批准 5D-2 只能持久化 5D-1 已完整验证的 canonical envelope，不得在 storage 层重算业务、补事件、补余额、补 mark 或补 P&L。
- [ ] `5D-06`：批准 5D-1/5D-2 继续保持零 backtest/paper/shadow/live、零真实账户/仓位/订单、零券商连接、零 KB 内部读取或写入，且不证明策略收益、容量或费用模型有效。

### B. Typed PIT 输入与账户范围

- [ ] `5D-07`：批准公开入口只接受 raw `Stage5DCompleteReplayCase`，并在同次调用内从 `raw_stage5c_case` 内部重新运行 Stage 5C；caller-supplied Stage 5C result、ledger state、NAV、P&L 或 PASS 不得成为权威输入。
- [ ] `5D-08`：批准 `CorporateActionCoverageSet/ElectionSet` 为内容寻址 typed 输入，逐证券声明覆盖区间、完整性及第 4 节各状态自己的经济与知识时点；每个 action 固定 `NOT_APPLICABLE/MANDATORY/CHOICE_REQUIRED`，choice-required 绑定 made/available/deadline、显式 default available、deadline/default rule、source、revision/supersedes 和 canonical hash，空集合或缺字段不得代表未知。
- [ ] `5D-09`：批准 `UnadjustedMarkObservationSet` 保存逐证券 observed/available 时点、未复权合法价格、session/rule/source identities、覆盖区间和完整性，禁止未来、零价或复权价回填。
- [ ] `5D-10`：批准 `SyntheticExternalCashFlowSet` 按 strategy/account 隔离并保存 flow id、方向、CNY 金额、economic/knowledge/cash-state times、recognized time、合成授权来源和 hash，只在第 5.4.2 节 exact cash posting 时改变余额；交易、股息与公司行动现金不得冒充 external flow。
- [ ] `5D-11`：批准 `OpeningLotAttributionSet` 覆盖账户内每个 opening lot 的 benchmark principal、slippage、fee、tax、corporate-action basis 和 full-cost identity；分量缺失时不得声称 complete P&L，也不得使用未知补差桶。
- [ ] `5D-12`：批准一个 5D case 只允许一个产业 strategy/account，但支持 account-wide multi-security positions；所有非零 lot 必须有 opening attribution 和公司行动覆盖，每个 valuation point 只对该 prefix 中 `actual_quantity>0` 的证券要求 mark coverage，已清仓证券不强制期末 mark，并按 security/lot 规范排序。

### C. Ledger V2、成本与结算

- [ ] `5D-13`：批准 Ledger V2 posting 显式分离 `asset_unit` 与 `security_id` dimension；现金为 `CNY/null`，逐证券成本/应收应付为 `CNY/security`，数量为 `SHARE/security`，禁止跨证券成本净额补差。
- [ ] `5D-14`：批准第 5.3 节完整 priority map：`5/10/20/30/40/50/51/60/70/80/90/95/100—106` 与 `effective_at → priority → ledger_event_id`，任何变更需新版本和批准。
- [ ] `5D-15`：批准 lot cost components 固定为 benchmark principal、execution slippage、fees、taxes、corporate-action basis adjustment，且每个 lot 的 components sum 必须等于 full cost。
- [ ] `5D-16`：批准买入 fee/tax 资本化进入逐证券 `SECURITY_COST` 和 lot components，卖出 fee/tax 从应收扣除；事件类型和归因保持分离，禁止重复扣减。
- [ ] `5D-17`：批准卖出继续按 `acquired_at → lot_id` FIFO，并按确定性比例移除每个 cost component；最终处置精确耗尽尾差，不能自动 plug 或改写旧 fill。
- [ ] `5D-18`：批准新增显式 `EXTERNAL_CAPITAL`、corporate-action/other receivable 和 payable 账户；external flow、公司行动应收应付、trade clearing 与 P&L 不得混账。
- [ ] `5D-19`：批准第 5.4 节 `Ledger V2 exact event semantic map v1` 为 closed-world allowlist：每个 Stage 5C/5D event/phase 的账户、security scope、借贷 signed formula、lot 五分量、clearing 归零和 recognized time 必须 exact；每事件后逐证券闭合 lot/full-cost/`SECURITY_COST`、现金、预留、应收应付、数量与 sellable，任何额外/缺失/不平为 `RECONCILIATION_BLOCKED` 且零自动补差。
- [ ] `5D-20`：批准 Stage 5C replay 入口继续拒绝全部 5D 事件，Stage 5D 使用独立完整 policy；首版对任何非空 settlement `special_exception_id` 继续 fail-closed，未获批准的例外不得绕过 MarketRuleSet。

### D. 五类公司行动

- [ ] `5D-21`：批准所有公司行动使用 typed complete coverage、原始未复权价格/gross cash 条款及第 4 节每状态独立 PIT 时间；资格由 action terms/MarketRuleSet 从 entitlement prefix 派生，不能用 sellable 代替 entitlement；choice/default phase 分别使用第 4 节 `election_recognized_at/default_recognized_at` 的 max 公式，所有 accepted events 严格匹配第 5.4.2 节，未知分支在首事件前失败关闭。
- [ ] `5D-22`：批准 `CASH_DIVIDEND` 严格执行第 5.4.2 节 recognize/fee-tax/paid/available exact phases：gross 应收与收益控制、typed fee/tax 各自独立归因但同 phase compound、paid 后才转 settled cash、cash available 后才可用，未来状态不得提前进入 NAV。
- [ ] `5D-23`：批准 `SHARE_DISTRIBUTION` 严格执行第 5.4.2 节 recognized/unsettled→delivered/unsellable→sellable phases，以 append-only lineage 增加 quantity 且五成本分量和同证券总 full cost 不变；不同证券分配或成本规则缺失时失败关闭，不自动设零成本。
- [ ] `5D-24`：批准 `SPLIT_OR_CONSOLIDATION` 严格执行第 5.4.2 节各 quantity bucket 的 exact rational delta 与 lot effect，五成本分量绝对额/总成本不变；fractional cash-in-lieu 复用 gross cash+fractional basis disposal 子语义，禁止静默截断、净额冒充 gross 或舍入补差。
- [ ] `5D-25`：批准 `RIGHTS_OR_ALLOTMENT` 严格执行第 5.4.2 节 `DECLINE/EXERCISE/MANDATORY`；前两者必须有截止前作出且 PIT 可得的 choice 或条款显式 default，exercise phase 不早于相应 election/default recognized time，并形成 reserve、逐证券 cost/payable、unsettled lot、paid→delivered→sellable，subscription fee/tax 资本化且不得伪造成市场 order/fill。
- [ ] `5D-26`：批准 `DELISTING_OR_CASH_OUT` 严格执行第 5.4.2 节；强制退出为 `MANDATORY`，自愿 `ACCEPT_CASH/DECLINE` 为 `CHOICE_REQUIRED` 且 phase 不早于有效选择或显式 default 可得时点，再依次形成 gross receivable、clearing 归零、lot 五成本移除、realized、paid 与 cash-available；未知 gross/basis/时点或选择不得清仓。
- [ ] `5D-27`：批准公司行动分数股、不同证券分配、cash-in-lieu、权利交易和自愿退出的每个未覆盖分支均独立失败关闭；缺选择不得推断为 `DECLINE`，截止后只允许条款显式、版本化、内容寻址且已可得的 default，不能使用最常见市场惯例。
- [ ] `5D-28`：批准公司行动事件与 lot effect 必须绑定 action/election/deadline/source/rule/revision hashes；同 prefix 只允许一个 active election，同字节幂等、异字节冲突，只有条款允许且截止前作出的 revision 可在其可得后用 reversal + replacement 生效，不得覆盖历史、回写 phase、复写 fill 或改变其他 strategy/account ledger。
- [ ] `5D-29`：批准复权价格仅可作为独立研究交叉检查，永远不得成为 Stage 5 fill、mark、lot cost、公司行动现金流或缺失条款替代值。

### E. Mark、stale 与 NAV

- [ ] `5D-30`：批准每个 valuation point 只对该 prefix 中 `actual_quantity>0` 的证券选择 `observed_at/available_at <= valuation_at` 的最后合法未复权正价格，并要求 exact security/session/rule/source scope；零持仓 market value 为零且无需 mark，同刻不同内容为歧义失败。
- [ ] `5D-31`：批准只有有效 session state 证明持续停牌时才能沿用 stale mark，并保存 stale flag、起点、时长和来源；stale mark 永不代表 executable price。
- [ ] `5D-32`：批准 mark 先按唯一优先级分流：scope/coverage/completeness/source/PIT 缺失或冲突为 `PRECHECK_BLOCKED`，ledger 不平为 `RECONCILIATION_BLOCKED`；只有完整 coverage 中持仓证券无历史合法 observation 且 ledger 已对账时，全账户 valuation/P&L 才固定为 `ABSTAIN + incomplete_pnl`，禁止 partial NAV 和任何价格回填。
- [ ] `5D-33`：批准 `MARK_TO_MARKET` 为 typed append-only memo event，不修改现金、数量或历史成本；mark 更正只用 reversal/replacement，所有余额变动事件仍须双分录。
- [ ] `5D-34`：批准第 7 节 closed-world account-to-NAV 映射：三类 cash、trade/公司行动/other receivable-payable 各一次，加逐证券 market value；`SECURITY_COST` 由 market value 替代，clearing/control/P&L/`EXTERNAL_CAPITAL` 不直接进 NAV，caller snapshot 只能交叉核对。
- [ ] `5D-35`：批准 beginning/ending valuation 使用同一规范 journal 的两个 inclusive prefix 并覆盖账户全部证券；本期唯一为 `(beginning_at,ending_at]`，未来 scheduled event 不进入较早 prefix，任一点 `actual_quantity>0` 的证券缺合法 mark 即不得声称完整账户 NAV/P&L，已清仓证券不强制 ending mark。

### F. 二维 P&L 与全账户对账

- [ ] `5D-36`：批准第 8.2 节恰好十八格 closed-world `3 × 6` matrix 及十三个 allowed signed formulas、五个 `FORBIDDEN=0` 规则；每个 as-of 物化完整十八格，cell 是唯一可加总事实，source lineage 只通过 contribution 加总。
- [ ] `5D-37`：批准 row/column/grand-total 都只是 derived disclosure；只有十八个 cells 可加总，marginal 或 total 再加回、forbidden cell 非零、contribution 与 cell 不等均为 `RECONCILIATION_BLOCKED`。
- [ ] `5D-38`：批准第 8.1—8.2 节逐 driver 符号与公式：普通卖出 gross=`TB+TS`，公司行动 basis disposal gross=`CAD`，五个 disposed/remaining cost components各只进 price/slippage/fee/tax 一格，`corporate_action_basis_adjustment` 只进 price，corporate-action cash 始终为 gross，任何 gross/net 互换或双计禁止。
- [ ] `5D-39`：批准 period 严格为两个 inclusive prefix 的 `(beginning_at,ending_at]` 差：`period_cell=C_end-C_begin`，ending-at 事件纳入、beginning-at 事件 period contribution 为零，并与 `ending_equity-beginning_equity-net_external_cash_inflow` 精确相等；external capital 不进入 P&L。
- [ ] `5D-40`：批准先逐证券闭合第 8.2 节十八格、source contributions、cost/NAV/equity，再精确汇总到账户；只有完整 mark coverage 中缺合法 observation 且 ledger 已对账时为 `ABSTAIN/incomplete`，任一 formula/gross/basis/cash/equity/cell/matrix 不平固定为 `RECONCILIATION_BLOCKED`，不得降级或产生 complete P&L authority。

### G. Complete replay 与 audit replay

- [ ] `5D-41`：批准 complete replay 只完整到 inclusive `ending_at <= injected_clock`；内部重算 Stage 5C，并按第 4/5.4 节只接受 `effective_at<=ending_at` 且对应状态/选择/default 自身知识已可得的事件，恰好 ending-at 纳入，未来 settlement/action/election/default/payment/cash-available/delivery/sellable 仅留 plan，不能泄漏到 current state。
- [ ] `5D-42`：批准 replay envelope 使用第 9 节显式 included/excluded allowlist，绑定全部承重规则、输入、action/election/deadline/default/revision、事件、valuation、P&L、代码、配置、Decimal 和 clock，排除运行、路径、端点与 rowid 噪声。
- [ ] `5D-43`：批准 `audit_replay` 只用原输入/规则/代码/horizon 精确复现并固定 `audit_only=true`、`authority_eligible=false`；无论成功失败均严格内存零写，不得调用 5D-2、创建/更新 SQLite 或形成新的 current decision、target、approval、position、fill、NAV/P&L authority 或 head。

### H. 同库 SQLite v4

- [ ] `5D-44`：批准 5D-2 仅对 InvestSystem `var/state/invest_system.sqlite3` 执行原子 `user_version 3 → 4`，新增且仅新增 `stage5_artifacts/stage5_run_aggregates/stage5_run_artifacts/stage5_ledger_events/stage5_run_ledger_events/stage5_account_generations` 六表；一次原子组完整包含 Manifest、Stage 4/5 canonical roles、projected/accepted events、marks、valuation、P&L、replay seal/root/members 和 generation/head，原样保留 v3，禁止第二数据库和 KB 表复制。
- [ ] `5D-45`：批准同 replay/key 同 canonical bytes 幂等、同 identity 不同内容冲突；semantic config 与 SQLite path/WAL/synchronous/timeout 等 operational config 严格分离，单连接固定 `WAL + synchronous=FULL + foreign keys + bounded busy_timeout + BEGIN IMMEDIATE`，以唯一约束和 expected prior head CAS 防止 last-write-wins。
- [ ] `5D-46`：批准 5D-2 写前和六表 read-back 均使用 approved typed codec 解码、canonical 重编码并复验 schema/role/hash/order/reference/head/semantic invariants；只有 `pnl_complete=true`、已对账、无资金/持仓变化的完整业务 `BLOCKED/ABSTAIN` 可 sealed 且不推进状态，mark-missing `ABSTAIN/incomplete_pnl` 与技术、hash、并发、reconciliation、SQLite/中断/read-back 失败全部零写。

### I. Golden、回归与排除项

- [ ] `5D-47`：批准第 11 节为最低验收门，特别包括每个 exact event/phase、同刻 compound、十八格数值、closed-world NAV、mark outcome precedence、清仓 mark scope、election/default/revision 的 made/available/deadline/recognized PIT、beginning/inside/ending 边界，以及 5D-2 分流/失败注入、确定性、migration、并发和全仓回归；任一门失败不得标记 Stage 5D 完成。
- [ ] `5D-48`：批准本包不授权真实数据、真实账户、真实订单、broker、backtest/paper/shadow/live、策略收益结论、Stage 6 或跨产业/题材共享 ledger/P&L；所有未逐项定义的公司行动、mark、成本、P&L 和 persistence 行为默认失败关闭。

## 14. 批准后的唯一实施顺序

若且仅若 owner 明确批准第 13 节全部四十八项，下一步仍必须按以下顺序进行：

1. 保留本 draft 原始字节不变；
2. 形成独立 approved machine bundle、approval record、document binding 和 typed Stage 5D rules verifier；
3. 实现 5D-1 typed contracts、Ledger V2、公司行动、mark、valuation/P&L 和 complete/audit replay；
4. 完成 5D-1 专项、golden、审阅和全仓验收；
5. 另行开始 5D-2 SQLite v4 migration 与原子 persistence；
6. 完成 migration、并发、失败注入、重开 read-back 和全部 v3/v4 回归；
7. 更新 PLAN/README/验收记录，但继续保持所有真实和交易权限为 false。

任何项目未获批准、任何 identity 漂移或任何验收失败，都停留在治理/实现中状态，不得跳到 persistence、Stage 6 或真实运行。
