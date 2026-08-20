# Stage 5D Outcome-Blind 静态支持 Census v0.1

审计结论：`STATIC_CODE_SUPPORT_CENSUS_COMPLETE / REAL_CANDIDATE_COVERAGE_NOT_COMPUTABLE`

审计日期：`2026-08-21`

审计基线提交：`8ea60895f7ebc42d5e58494711365f6305864889`

机器清单：[`stage5d-outcome-blind-static-support-census-v0.1.json`](machine/stage5d-outcome-blind-static-support-census-v0.1.json)

## 1. 技术摘要

**IS 可以在 KB 继续其他工作的同时，独立完成 Stage 5D 代码支持面盘点。** 当前代码并非完全没有 SELL：source-driven Ledger V2 已验收 SELL continuation、两 lot FIFO 成本移除、卖出费用/税/滑点，以及卖出资金从应收到结算再到可用的时序；真正缺少的是把该 SELL 链接入通用 mark/NAV、十八格 P&L 和 complete replay，从而形成 Stage 6 所需的已结束交易。

本次 census 共冻结 20 项静态能力：

| 状态 | 数量 | 含义 |
|---|---:|---|
| `ACCEPTED_BOUNDED_SLICE` | 6 | 固定 ENTER/BUY 纵向切片已形成 complete replay 证据 |
| `ACCEPTED_LEDGER_ONLY` | 4 | source-driven Ledger/FIFO/结算已验收，但尚无通用 complete NAV/P&L |
| `FAILS_CLOSED` | 4 | unsupported 输入会在发布金融输出前明确阻断 |
| `NOT_IMPLEMENTED` | 4 | 当前没有可验收的业务实现 |
| `NOT_EVALUABLE_WITHOUT_HISTORICAL_CANDIDATES` | 2 | 必须等待 outcome-blind 公共候选总体，当前禁止猜测 |

这份静态 census 不关闭 Readiness `R-23—R-25`：它只纠正“SELL 完全不存在”的过度简化，证明最小 SELL complete-replay 切片可以复用现有底层。真实候选分母、总/年度 coverage、selection-bias、material-category coverage 和 completed-trade 数仍不可计算，正式 Stage 6C 继续 `NO_GO`。

## 2. 支持状态必须分层理解

定义如下：

- `ACCEPTED_BOUNDED_SLICE`：固定预注册 case 的同次 Stage 5C 重算、Ledger、估值、P&L 和 complete/audit replay 均有测试证据；不得外推到其他 case。
- `ACCEPTED_LEDGER_ONLY`：事件投影、posting、lot/FIFO、结算或 prefix replay 已通过测试，但没有通用 mark/NAV/P&L/complete replay。
- `FAILS_CLOSED`：对应输入被显式识别，并在发布 partial NAV/P&L 前停止；这证明安全边界，不等于业务支持。
- `NOT_IMPLEMENTED`：缺少实现或验收，不能通过 enum、规则文档或 P&L cell 名称冒充能力。
- `NOT_EVALUABLE_WITHOUT_HISTORICAL_CANDIDATES`：代码静态盘点不能回答，必须绑定未来冻结的候选总体后再计算。

“支持”只按公开 evaluator 路径和测试共同认定。仅存在类型、enum、私有 helper 或规则描述，不计为支持。

## 3. 静态能力矩阵

| ID | 能力 | 状态 | 已有证据 | 精确边界 |
|---|---|---|---|---|
| `S5D-01` | 同一次调用重算 Stage 5C | `ACCEPTED_BOUNDED_SLICE` | bounded replay 从 raw case 重算，不接受 caller PASS | 仅固定预注册 ENTER/BUY complete case |
| `S5D-02` | source-driven BUY trade | `ACCEPTED_BOUNDED_SLICE` | `BUY_TRADE` principal/fee/tax/slippage 与 lot 成本闭合 | 仅普通 synthetic 证券与精确规则 |
| `S5D-03` | BUY 现金与证券交收 | `ACCEPTED_BOUNDED_SLICE` | `BUY_CASH_SETTLEMENT`、`SECURITY_SETTLEMENT` | 不支持特殊结算例外 |
| `S5D-04` | T+1 可卖转换 | `ACCEPTED_BOUNDED_SLICE` | `SECURITY_SELLABLE` 且未来状态不泄漏 | 仅精确普通合成交收合同 |
| `S5D-05` | 固定 ENTER/BUY mark、NAV 与十八格 P&L | `ACCEPTED_BOUNDED_SLICE` | beginning/ending NAV `100000/99986.77`，P&L `-13.23` | 单固定 mark、单证券、固定 horizon |
| `S5D-06` | 固定 ENTER/BUY complete/audit replay | `ACCEPTED_BOUNDED_SLICE` | complete replay `f5ed17d1…9225`，audit 零权限 | 不能替代一般历史 batch replay |
| `S5D-07` | SELL continuation opening attribution | `ACCEPTED_LEDGER_ONLY` | 两 opening lots、五成本分量与 continuation basis | 未进入 bounded complete replay |
| `S5D-08` | SELL FIFO trade 与成本分量移除 | `ACCEPTED_LEDGER_ONLY` | `SELL_TRADE`、FIFO 顺序、fee/tax/slippage 负例 | 无完整 realized/unrealized P&L matrix |
| `S5D-09` | SELL 资金应收、结算与可用 | `ACCEPTED_LEDGER_ONLY` | `SELL_CASH_SETTLEMENT`、`SELL_CASH_AVAILABLE`，未来状态不泄漏 | 无 complete valuation/replay |
| `S5D-10` | 显式 rejected/no-fill source replay | `ACCEPTED_LEDGER_ONLY` | 只重放 source-bound opening，保持零成交 | bounded complete case 未一般化 |
| `S5D-11` | 通用 REDUCE/EXIT→SELL complete replay | `NOT_IMPLEMENTED` | bounded 入口对 SELL case 明确阻断 | Stage 6 不能据此形成 completed trade |
| `S5D-12` | 20/60/120-session mark 与 daily NAV | `NOT_IMPLEMENTED` | 当前仅一个固定 beginning/ending valuation | 不能生成 Stage 6 source-driven daily NAV |
| `S5D-13` | 非空公司行动 | `FAILS_CLOSED` | bounded precheck 在金融输出前阻断 | 分红、送股、拆并股、配股、退市均未实现 |
| `S5D-14` | 非空外部现金流 | `FAILS_CLOSED` | bounded precheck 阻断，当前净外部流固定为零 | 无入金/出金 P&L neutralization |
| `S5D-15` | 特殊结算例外 | `FAILS_CLOSED` | 未绑定 special exception 时明确拒绝 | 不得从普通结算推断 |
| `S5D-16` | 通用 stale/correction mark 矩阵 | `FAILS_CLOSED` | coverage 缺失、无 eligible mark、mark drift 分层失败 | 只有固定 mark，不是通用 mark engine |
| `S5D-17` | 多证券与 peer portfolio complete replay | `NOT_IMPLEMENTED` | 无正式多证券 complete NAV/P&L 验收 | Stage 6 peer return/NAV 仍缺失 |
| `S5D-18` | Stage 5D durable persistence | `NOT_IMPLEMENTED` | 当前纯内存且 `persists_state=false` | SQLite v4/migration 仍未授权 |
| `S5D-19` | 真实候选总/年度支持 coverage | `NOT_EVALUABLE_WITHOUT_HISTORICAL_CANDIDATES` | 本次未读取候选总体 | 分母和 80%/70% 门均不可计算 |
| `S5D-20` | 真实已结束交易数量 | `NOT_EVALUABLE_WITHOUT_HISTORICAL_CANDIDATES` | 本次未运行候选或读取 outcome | 不得宣称达到 30 笔或每 fold 5 笔 |

## 4. Census 范围、grain 与禁读字段

本次分析对象是**代码能力项**，grain 为 `capability_id × implementation_layer × evidence_identity`，不是历史候选。证据仅来自当前 IS 源码、测试、预注册和验收记录；没有网络请求、KB 数据读取、策略运行或持久化。

未来真实候选 census 必须另建不可变 artifact，grain 固定为：

`economic_event × listed_company × decision_time × frozen_candidate_id`

support flag 必须在任何收益、label 或表现 summary 可读之前冻结。允许用于支持判定的字段只包括：候选身份、decision time、security、目标 action/horizon、所需事件 inventory、MarketRuleSet/交易日历/证券状态身份、mark coverage、lot/settlement/公司行动/外部流场景，以及当前代码支持矩阵 hash。

支持判定阶段禁止读取或派生：

- future return、full/comparator contribution、NAV/P&L summary；
- label、是否最终退出、是否盈利、最终 champion 状态；
- holdout record、count、schema-derived cardinality 或任何 holdout bytes；
- 通过删除 `REJECT/ABSTAIN/BLOCKED/无成交/退市` 改变分母。

## 5. 当前无法计算的质量指标

由于 KB 尚未提供本任务所需的公共、内容寻址候选总体，本次以下值全部为 `null`，不是 `0`：

| 指标 | 当前值 | 所需后续证据 |
|---|---|---|
| candidate denominator | `null` | 冻结的 HistoricalDataReadinessReport/candidate inventory |
| aggregate coverage | `null` | 逐候选 support flag/reason |
| annual coverage | `null` | decision year 与完整固定分母 |
| SMD / categorical gap | `null` | outcome-blind candidate features 与 support flag |
| material-category coverage | `null` | 候选类别分布与逐项 support |
| completed trades | `null` | 一般化 source-driven EXIT/SELL complete replay |

没有这些输入，不画 coverage 图、不报告比例，也不做 80%/70%/30 笔完成门判断。

## 6. 方法与稳健性检查

本次采用四步静态审计：

1. 从 Stage 5D 公共 evaluator 和 source adapter 建立 closed-world 事件/生命周期 inventory；
2. 要求每个正向能力同时存在实现分支和对应测试，只有 enum/文档不计数；
3. 把 Ledger-only 能力与 complete replay 能力分开，避免把底层 SELL 支持夸大为 completed trade；
4. 将 unsupported 的显式失败关闭与完全未实现分开，避免把安全拒绝误写为业务能力。

稳健性结论：已有 SELL ledger golden 使“从零实现 SELL”这一判断不成立；bounded replay 的 exact case/precheck 又使“SELL 已完整支持”同样不成立。二者共同限定当前状态只能是 `ACCEPTED_LEDGER_ONLY`。

## 7. 下一条全局最优切片

建议先形成并预注册**普通 A 股、无公司行动、无外部流、无特殊结算的完整 ENTER/BUY→EXIT/SELL 生命周期切片**，复用现有 source-driven SELL/FIFO/settlement：

1. 绑定同一候选、账户、security、entry 与 exit 的精确 source lineage；
2. 生成 holding-period daily mark/NAV，至少闭合 Stage 6 主 60-session horizon；
3. 完整重放 SELL、卖出资金结算/可用和期末零仓位或精确残余仓位；
4. 形成 realized/unrealized、fee/tax/slippage 唯一归属的十八格 P&L；
5. 生成 completed-trade identity、complete/audit replay 和 unsupported reason；
6. 对公司行动、外部流、特殊结算继续失败关闭，不为追 coverage 临时扩规则。

这条切片能直接关闭 `R-23` 的核心技术缺口，并为后续真实 support coverage 提供可复用判定器。它不需要 KB 为策略定制事实；但真实命中率仍必须等待 KB 公共候选总体。

## 8. 限制与待确认问题

- 本报告是静态代码支持 census，不是 HistoricalDataReadinessReport，也不更新真实 candidate support flag。
- 未运行收益、候选、benchmark、holdout 或正式历史数据；不能证明策略有效。
- 下一切片是否要求一次全量退出，还是允许 partial REDUCE 后再 EXIT，需要在预注册时冻结；为最小 completed-trade 语义，推荐首版只允许一次全量 EXIT。
- daily mark 的公开数据粒度、历史 coverage 和 PIT 完整性仍由后续 KB 公共交付 census 提供，IS 不读取 KB 内部路径补齐。

## 9. 当前决策

`PROCEED_WITH_MINIMAL_SELL_COMPLETE_REPLAY_PREREGISTRATION`

允许形成下一条匿名合成预注册和规则内最小设计；不授权正式 Stage 6C run、真实 development/walk-forward、holdout、6D、migration、backtest、paper、shadow、live、仓位或订单。
