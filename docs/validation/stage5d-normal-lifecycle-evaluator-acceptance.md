# Stage 5D 普通证券完整生命周期 Evaluator 验收

## 验收结论

状态：`completed_with_scope_limits / anonymous_synthetic_only`

输入锁：`60cad84334d110e910be897179bf76409f59c59b3bcd45fd733d29cf67829e30`

Evaluator 源码 SHA-256：`e0a48f0c92df73eb35bb1746e7c8c4cbfd5d21b1ed4106ad8e27ffb195050449`

机器 golden：[`normal-lifecycle-evaluator-golden.v0.1.0.json`](../../tests/fixtures/stage5d/normal-lifecycle-evaluator-golden.v0.1.0.json)，raw SHA-256 `59219933c28c9552dc434a8a5a79525aa49f23bafdac65c2701922b498034225`

本验收只关闭一个匿名合成、单证券、普通规则、无公司行动/外部流/特殊结算的 ENTER/BUY→60-session full EXIT 生命周期。它不证明真实历史 coverage、30 笔完成交易、peer benchmark、组合 NAV 或正式 Stage 6C 已就绪。

## 完整编排

公共入口 `evaluate_stage5d_normal_lifecycle` 只接受精确 input-set，并在同一次调用内：

1. 通过已有 bounded BUY evaluator 从 raw entry case 重算原 complete replay；
2. 通过已有 Stage 5C/Stage 5D source adapter 重算 full-EXIT raw case；
3. 保留旧 BUY 五事件字节不变，只把 SELL 三事件重新绑定到同一 financial prefix；
4. 以 entry lot 的真实 source fill lineage 替换独立 SELL opening snapshot lineage，禁止第二 opening；
5. 形成 8-event financial V2 replay，并验证 session 60 清仓、session 61 资金可用；
6. 把 59 个 `MARK_TO_MARKET` memo events 纳入完整 67-entry canonical wrapper journal；
7. 从每个 exact financial/journal prefix 派生 baseline + 60 sessions 的 61 点 valuation series；
8. 物化完整十八格 lifetime/EXIT-period P&L、completed-trade record 和 complete replay；
9. audit replay 必须绑定精确 source complete replay hash，且继续零副作用。

没有 caller-supplied NAV、P&L、completed flag 或 partial PASS 注入字段。

## 会计与时间 Golden

| 项目 | 固定值 |
|---|---:|
| baseline NAV | `100000` |
| session 1—59 NAV | `99986.77` |
| session 60 NAV | `99971.95` |
| session 60 available / receivable | `98386.77 / 1585.18` |
| settlement-tail available cash | `99971.95` |
| ending quantity / lots | `0 / 0` |
| lifetime P&L | `-28.05` |
| EXIT-period P&L | `-14.82` |
| position closed | `2025-04-11T02:31:00Z` |
| ledger settled | `2025-04-14T02:11:00Z` |

每个 valuation point 验证：

`NAV = cash_available + cash_reserved + cash_settled_unavailable + cash_receivable - cash_payable + security_market_value`

60 个 daily return factors 必须逐项等于相邻 NAV 比值。session 60 的应收不得提前成为可用现金；settlement tail 不增加 horizon return 或 P&L。

## 确定性身份

| 制品 | SHA-256 |
|---|---|
| case | `dd632889fa2758d528882007028f9e7790677df293c79a6c247df13faceba53d` |
| exit Stage 5C result | `eaaa6fd52cf8afc483192a4eadf9cd8504c614c8f0e10294abfd1884ad8158e0` |
| exit source slice | `2b1a0c5f8f93f659a4664543a158f14fc4192cbc97eb1c4f8d42d38f5ab8e30a` |
| financial replay | `a1acee56e4c2a01f829968929d0758a3c05fa9477b3b8c185b8ddb32a5704957` |
| full journal head | `255c184be2d8603980f177e759430fc3e7b0697e2068a12e72000ef3657850a7` |
| valuation series | `4ca978ac6ad020eca50035631c244027fc525ad254231dae516d01634c4d57cc` |
| P&L | `62485e7160bc60314733157c856978b6b885dc842dadc785f151f95c61555549` |
| completed trade | `a5707fa08d6da2a20ef9540bd5c6b0fc20373d5534c7f72f5f63b116f895b07b` |
| complete replay | `277181e9bc406de860e8d98dd23cc27be74f950d3b170bdc5e199f661c5f79ba` |

## 失败关闭与权限

验收覆盖：

- 非精确 input-set 在构造/执行前拒绝；
- entry/EXIT 同次重算或 lineage/hash 漂移失败关闭；
- financial replay、FIFO、cash settlement、67-entry prefix 或 61-point series 不平时不发布 partial NAV/P&L；
- daily factor、十八格 period difference 或 contribution 汇总漂移不能构造 `COMPLETE`；
- audit source hash 错误不发布 replay；
- ambient Decimal context 不影响结果。

所有输出固定：`authority_eligible=false`、`external_state_mutated=false`、`persists_state=false`，且不授权 backtest、paper、shadow、live、真实账户/仓位/订单、broker、KB 内部读取/写入或 migration。

## 验证结果

- 新 lifecycle evaluator 专项：`9 passed`
- Stage 5C/5D、输入物化、规则治理与 Stage 6 synthetic 相邻：`133 passed`
- 全仓 pytest：`1129 passed, 4 skipped`
- Ruff check：通过
- Ruff format check：通过
- mypy：`149 source files` 通过
- compileall：通过
- `git diff --check`：通过

四个 skip 均为当前 Windows 账户缺少测试 symlink privilege 的既有平台 skip。

## 仍未关闭的正式门

本结果中的 `completed_trade_count=1` 明确标记为 `not_a_real_completed_trade=true`，不得进入 Stage 6 的真实 30 笔门。下一步应等待 KB 公共候选总体并形成 outcome-blind candidate support census，或先形成同一 valuation seam 的 peer 复用设计；不得直接启动正式 Stage 6C、migration 或 holdout。
