# Stage 5D 普通证券完整生命周期与全量 EXIT 回放预注册 v0.1

状态：`frozen_for_input_materialization_review`

形成日期：`2026-08-21`

形成基线：`39db014cf90b5ed351c915fa23b3fc2c7cf441eb`

机器预注册：[`normal-lifecycle-exit-replay-preregistration.v0.1.0.json`](../../tests/fixtures/stage5d/normal-lifecycle-exit-replay-preregistration.v0.1.0.json)

输入物化授权：`false`

Evaluator 实施授权：`false`

## 1. 结论先行

下一条全局最优切片不是“再写一个固定 SELL 结果”，而是建立一个可复用的**完整持仓生命周期 + session-by-session valuation** 接口，并以一个普通规则、单证券、一次全量 EXIT 的匿名合成案例作为第一条 golden。

现有 SELL Ledger/FIFO/结算可以复用，但现有 SELL fixture 不能复用为 completed trade：它从 300 股 opening 只卖出 200 股，结束仍有 100 股；现有 BUY fixture 则是独立的 200 股单 lot。把二者拼接会伪造 entry→exit lineage。

本预注册因此要求新切片从已经验收的 BUY source lineage 连续向前重放，在同一 canonical journal 上生成持有期 valuation path、全量 SELL、结算尾部、十八格 P&L 和 completed-trade identity。预注册只冻结输入语义、数值和完成门，不冻结尚未由实现产生的 case/result/event/replay 哈希。

## 2. 全局路径比较

| 路径 | 能推进的主阻塞 | 主要风险 | 裁决 |
|---|---|---|---|
| 只补固定 SELL complete result | `R-23` 的局部 | 后续仍需重写 daily NAV 与 peer 接口 | 拒绝 |
| 先做全功能 mark/NAV/公司行动平台 | `R-19/R-29` 的远期部分 | KB 数据 census 未完成，容易过早固化错误抽象 | 拒绝 |
| 先做正式 admission/migration | `R-10—R-13` | 会持久化一个仍不能形成 completed trade 的流程，并与 Stage 5D v4 竞争版本 | 后置 |
| 完整普通生命周期 + 最小 valuation seam | `R-23` 核心，并为 `R-19/R-25/R-29` 提供公共接缝 | 需严格限制为单证券和已批准普通规则 | 选择 |

该选择不关闭任何 Readiness 项。只有实现和独立验收后，才可认为 `R-23` 的技术核心被关闭；真实 30 笔交易、coverage 和 peer portfolio 仍等待公共历史候选 census。

## 3. 范围和不可扩张边界

本预注册唯一业务范围为：

- 一个匿名合成候选；
- 一个普通 A 股语义的 synthetic security/account；
- 一个已验收的 ENTER/BUY source lineage；
- 普通 T+1、普通卖出资金结算；
- 60-session 主 horizon 上一次全量 EXIT；
- 零公司行动、零外部现金流、零特殊结算；
- 纯内存、匿名合成 `research` validation。

公共 lifecycle/valuation 接口必须证券中立，不得在实现中硬编码 `600000.SH`、固定价格或日期。固定 ticker、金额和 synthetic dates 只属于 golden fixture。

本切片不实现：partial REDUCE、多次加减仓、多证券账户、peer basket 编排、公司行动、外部流、特殊结算、20/120-session 稳健性、正式历史 run、SQLite migration 或任何交易权限。

## 4. 精确上游 lineage

Entry 必须精确引用现有第一条回放，而不是重新制造另一份 opening：

| 身份 | 冻结值 |
|---|---|
| first BUY prereg canonical hash | `f7042c49f72b693d1c9ae5892b1d454be07cf6ad0851c499b47b2fead55492bc` |
| Stage 5C BUY case hash | `06a9eaac57fec706b7bda7566494256cd0df045e1bdab2d826a1a85066a1ee62` |
| Stage 5C BUY result hash | `daf123cd8ad8418a5794c5aa86f08b66d6c18e3aebd1cdef58cae1b0d88dab59` |
| BUY fill id | `synthetic_fill_b11033004c59d2aaef7256e0` |
| BUY fill hash | `18b198a25001a41dc9a566f236d37234469a8725edc9f2f63473bcdf372af020` |
| BUY complete replay hash | `f5ed17d1bf9944d35b7a5afa36e68df0fc40d12c277874ea01d02d1e0bd59225` |
| BUY ending journal head | `e375af373c99b84dac549ddbcb0d8b21ba861931aedeb8a6353c999991a3a836`，只作旧 source replay anchor |

进入 full EXIT 前的唯一 lot 固定为 200 股、全部可卖；lot ID 为 `stage5d_v2_lot:synthetic_fill_b11033004c59d2aaef7256e0`，`acquired_at=2025-01-20T02:31:00Z`，source fill hash 为 `18b198a2…020`，derived lot canonical hash 为 `5f24ef77c4594d4aef340c21fc3bed1144b3aaf26efa013386578fd528ce0233`。五成本分量为：principal `1600`、fee `5.23`、tax `0`、slippage `8`、basis adjustment `0`，full cost `1613.23`。

旧 BUY ending head 不能成为新 full-lifecycle journal 的 prefix head。59 个 `MARK_TO_MARKET` memo events 将按时点插入 BUY 与 SELL 事件之间并改变所有后续 event/head hashes；实现只能把旧 head 作为 source replay anchor，随后从 BUY raw source 重新物化新的连续 journal。

现有 partial SELL 的 result/replay/head 哈希只能作为回归证据，必须标记 `must_not_be_reused_as_completed_trade=true`。新实现不得通过修改旧 fixture 或旧 hash 把 partial SELL 变成 full EXIT。

## 5. 60-session valuation path

Stage 6 主 horizon 已批准为“首次合法可成交后的第 60 个交易日收盘，提前 approved exit 按真实时点结束”。本次 EXIT 的 origin 固定为 `STAGE6C_VALIDATION_HORIZON_LIQUIDATION`，只用于 Stage 6 验证期固定清仓 golden，不是 Stage 4 `FR-EXIT-001` 的 evidence/risk/time/value exit，也不证明真实策略退出规则。本 synthetic golden 冻结以下 off-by-one 语义：

- baseline valuation point：entry session 开盘前，NAV `100000`；
- entry session ordinal：`1`；
- scheduled full EXIT session ordinal：`60`；
- valuation points：baseline + 60 个 session close，共 `61` 点；
- daily returns：相邻 valuation points，共 `60` 个；
- 持仓 mark：session `1—59`，共 `59` 个；
- session `60` 在 close valuation 前完成全量 SELL，因此零仓位，无 ending mark 要求；
- SELL settlement/availability 位于 session `61` tail，不增加第 61 个 horizon return。

机器 fixture 使用 `2025-01-20` 起的 60 个 Monday—Friday synthetic sessions，只用于确定性测试，明确不是 SSE 真实交易日历或 KB Published Release。正式执行必须换成经过验证、内容寻址的历史交易日历，不能复用 synthetic calendar。该 calendar、59 条 mark observation、coverage set 与 full-EXIT raw Stage 5C case 都是 evaluator 的承重输入，必须先在独立 input-materialization step 中物化并冻结 canonical hashes；在这些 hash 仍为 `null` 时禁止实现 evaluator。

所有持仓 mark 价格固定为 `8`，用于隔离价格变动并验证 acquisition/sell cost 各计一次。mark ordinal `001—059` 分别绑定对应 synthetic session；每条 `observed_at=07:00Z`、`available_at=valuation_at=07:01Z`，并必须具有独立 mark/source/coverage identity。每个 valuation point 必须绑定同一 journal 的 exact inclusive prefix、对应 mark-set identity 和 P&L matrix identity；不得接受 caller-supplied NAV。

Entry 只允许使用 `available_at <= entry_decision_at` 的输入；EXIT 只允许使用 `available_at <= exit_decision_at` 的输入。EXIT input bytes、marks 或后续状态不得反向改变 entry 重算。EXIT raw case 必须精确绑定 validation-horizon exit mandate、historical MarketRuleSet、calendar、CostSchedule、ImpactCurve 和 Stage 5C account/risk/settlement inputs；这些身份在 input materialization 前不得由 evaluator猜测。

## 6. 完整事件 inventory

规范 balance/security 事件顺序恰好为：

1. `OPENING_BALANCE`
2. `BUY_TRADE`
3. `BUY_CASH_SETTLEMENT`
4. `SECURITY_SETTLEMENT`
5. `SECURITY_SELLABLE`
6. `SELL_TRADE`
7. `SELL_CASH_SETTLEMENT`
8. `SELL_CASH_AVAILABLE`

另有恰好 59 个 `MARK_TO_MARKET` append-only memo events；它们不修改金融余额，但属于 canonical journal，effective time 为 `max(observed_at, available_at)`。完整 projected inventory 因此为 `8 + 59 = 67` 个 events，并按 effective time/priority 形成唯一 full prefix。整个生命周期只能有一个 opening；EXIT 阶段不得重新加入 `OPENING_POSITION` 或从独立 SELL snapshot 重开账。

`position_closed_at` 固定为 full SELL fill 被接受的时点；`ledger_settled_at` 固定为卖出资金可用且全部应收/clearing 对账完成的时点。`completed_trade_id` 只有在后者之后、十八格 P&L 和 complete replay 全部闭合时才可签发。

## 7. 会计 golden

Entry 沿用现有 BUY golden：

| 项目 | 值 |
|---|---:|
| opening cash/NAV | `100000` |
| BUY quantity | `200` |
| BUY benchmark/fill | `8 / 8.04` |
| BUY principal/fee/tax/slippage | `1600 / 5.23 / 0 / 8` |
| post-BUY cash | `98386.77` |
| holding NAV at flat mark | `99986.77` |

Full EXIT 冻结为：

| 项目 | 值 |
|---|---:|
| SELL quantity | `200`，必须等于 exit 前 actual/sellable quantity |
| SELL benchmark/fill | `8 / 7.96` |
| SELL gross execution proceeds | `1592` |
| SELL fee/tax/slippage | `5.22 / 1.60 / 8` |
| net receivable/cash proceeds | `1585.18` |
| ending quantity/sellable/lots | `0 / 0 / 0` |
| ending cash/NAV | `99971.95` |

Lifetime 十八格累计非零值恰好为：

- realized price：`0`；
- realized slippage：`-16`；
- realized fee：`-10.45`；
- realized tax：`-1.60`；
- 其他 14 格：`0`；
- lifetime total P&L：`-28.05`。

仅 EXIT period 固定为 `(session 59 close 2025-04-10T07:01Z, session 60 close 2025-04-11T07:01Z]`，P&L 为 `-14.82`。beginning matrix 只有 unrealized slippage `-8`、unrealized fee `-5.23` 非零；ending matrix 只有 realized slippage `-16`、realized fee `-10.45`、realized tax `-1.60` 非零；period matrix 对应 realized 三格为 `-16/-10.45/-1.60`，unrealized slippage/fee 为 `+8/+5.23`，其余十三格均为零。正号 reversal 只完成 realized/unrealized 重分类，不得再次收费；ending unrealized row 必须全零。Apr 14 settlement tail 只改变 cash bucket，不产生 return 或 P&L。

## 8. 可复用公共接缝

未来实现至少应产生以下证券中立对象；名称可由实现确定，但语义不得缩窄：

- `LifecycleReplayCase`：entry raw case、由同一 journal prefix 派生并交叉核对的 exit raw case、规则/能力、calendar、mark coverage 和 source lineage；exit account snapshot 不是第二 opening authority；
- `SessionValuationPoint`：session identity、valuation time、journal prefix hash、mark-set hash、`cash_available/cash_reserved/cash_settled_unavailable/cash_receivable/cash_payable`、按证券 market value、quantity、NAV 与 cumulative P&L hash；
- `SessionValuationSeries`：严格连续的 61 点、60 returns、同一账户/日历和 deterministic series hash；
- `CompletedTradeRecord`：entry/exit fill identities、full quantity、position/settlement times、journal root、十八格 P&L 和 reconciliation；
- `LifecycleReplayResult`：complete/audit replay、支持状态、失败 reasons 和全部零权限字段。

该 valuation seam 将来必须原样用于 target 和 peer security，禁止 benchmark 专用无摩擦收益路径。本切片不编排 5-member peer basket，也不声称产生组合 NAV；那是 Stage 6 的独立后续集成门。

## 9. 失败关闭矩阵

以下任一情况不得发布 completed trade、partial NAV/P&L 或 success replay：

- entry lineage、BUY fill、BUY ending head 或规则 hash 漂移；
- EXIT quantity 不等于当前 actual/sellable quantity；
- partial fill、余量未取消闭合或期末仍有 lot；
- EXIT 在 session 60 不可成交；不得用 mark 冒充 fill，也不得自创 retry window；
- session/mark 缺失、重复、未来可得、PIT/coverage 不完整或 stale 未证明；
- journal prefix 不连续、未来 settlement 泄漏或新 opening 被插入；
- 公司行动、外部现金流、特殊结算或非普通 security 输入；
- realized/unrealized 重分类、gross/net、fee/tax/slippage、NAV/equity 任一不平；
- caller 提供 NAV、P&L、completed flag、PASS 或 outcome-derived support decision；
- 任何 authority、persistence、broker 或 KB 内部访问字段为 true。

EXIT 不可成交的 fixture 只允许输出 fail-closed 状态，并保持 `completed_trade_id=null`。是否在真实 Stage 6 中启用独立 retry window，必须另行版本化批准，不能由本预注册推断。

## 10. 实现前不得伪造的身份

以下承重输入必须先通过独立 input-materialization step 形成 canonical bytes 并回填非空 hash；在此之前 evaluator 实施保持禁止：

- full-EXIT raw Stage 5C case；
- 60-session synthetic calendar；
- 59 条 mark observation set 与 coverage set；
- validation-horizon exit mandate、exit MarketRuleSet/CostSchedule/ImpactCurve/settlement input closure。

只有下列结果值属于 evaluator 实现后派生，本预注册固定为 `null`：

- 新 full-EXIT Stage 5C result/order/fill hash；
- SELL event hashes、完整 journal head；
- 61 个 valuation hashes、series hash；
- ending P&L、completed-trade、complete/audit replay hash；
- implementation code/config hash。

实现不得为了匹配预期数字手写这些 hash，也不得回改本预注册。派生结果与数值/公式不一致时只能失败关闭。

## 11. 完成门与非目标

若后续先获得 owner 输入物化授权，必须只生成上述 raw input fixtures 和 canonical hashes，不得运行 lifecycle evaluator。只有输入制品再次冻结并经 owner 独立授权后，最小实现验收才必须同时证明：

1. entry 与 EXIT 均从 raw source 同次重算，且只有一个连续 journal；
2. 61 个 valuation points 全部从 exact prefix 和合法 mark 派生；
3. session 60 全量 EXIT，session 61 settlement tail 完整闭合；
4. lifetime/EXIT-period 十八格、NAV、cash、quantity 与 P&L 恒等式全部成立；
5. completed-trade 只在 position closed、ledger settled、P&L complete 后形成；
6. 公共接口不硬编码 fixture security，且同输入 deterministic；
7. 全部失败关闭 negative cases 和 audit replay 零权限；
8. 既有 bounded BUY、partial SELL、Stage 5C 和 Stage 6 synthetic 基线不漂移。

预注册形成不等于实现授权，不关闭 `R-23`，不提供真实 candidate coverage、30 笔完成交易、peer benchmark、正式 Stage 6C、6D 或任何交易能力。

## 12. Owner 待确认

建议 owner 先原子确认以下输入物化范围，不直接授权 evaluator：

> 批准只物化本预注册的匿名合成承重输入：full-EXIT raw Stage 5C case、60-session synthetic calendar、59 条 mark/coverage、validation-horizon exit mandate 与 exit rule/cost/impact/settlement closure；不得实现或调用 lifecycle evaluator。输入 hashes 冻结并复核后，再单独决定是否授权单证券、60-session valuation path、一次全量 EXIT 的 evaluator 实现。全程仅限 `stage5_synthetic_execution_validation`，不授权真实历史 run、coverage、peer basket、migration、backtest、paper、shadow、live、仓位或订单。
