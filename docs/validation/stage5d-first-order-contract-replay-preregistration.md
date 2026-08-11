# Stage 5D 第一条订单/合同历史回放预注册

状态：`frozen_for_implementation`

冻结日期：`2026-08-12`

基线提交：`4c1cd4d0d1986e32d78e32063163fe4a0b7523af`

机器预注册：[`first-order-contract-replay-preregistration.v0.1.0.json`](../../tests/fixtures/stage5d/first-order-contract-replay-preregistration.v0.1.0.json)

机器预注册 canonical SHA-256：`f7042c49f72b693d1c9ae5892b1d454be07cf6ad0851c499b47b2fead55492bc`

## 1. 冻结目的

本记录把 Stage 5D 当前工程门限定为第一条匿名合成“订单/合同事件”历史回放，防止实现过程中根据结果更换案例、窗口、mark 或会计范围。它是实施前预注册，不是 Stage 5D 验收，不证明策略有效，也不提供任何运行或交易权限。

Stage 5D 的 48 项 approved 规则继续作为长期治理上限，原规则、draft、approved bundle 和 approval record 均不修改。当前纵向切片只实现本记录明确列出的事件；其他场景必须失败关闭，而不是为了追求全覆盖继续扩张 contracts。

## 2. 案例身份

| 字段 | 冻结值 |
|---|---|
| `case_id` | `stage4_4a4_case_001` |
| `strategy_id` | `industrial_bottleneck_event` |
| `security_id` | `600000.SH` |
| `account_fixture_id` | `anonymous_account_001` |
| `action_intent` | `ENTER` |
| `stage5c_case_sha256` | `06a9eaac57fec706b7bda7566494256cd0df045e1bdab2d826a1a85066a1ee62` |
| `stage5c_result_sha256` | `daf123cd8ad8418a5794c5aa86f08b66d6c18e3aebd1cdef58cae1b0d88dab59` |

业务语义锚点是已有匿名合成高速光互连订单/合同 fixture。该 JSON 只提供业务语义追溯，不是 Stage 5D runtime 输入，不得冒充 KB Published Release 或真实策略证据。可执行案例仍由固定 Stage 4/5 合成输入物化，并以内容哈希闭合。

## 3. 回放时间范围

时间统一使用 UTC，期间语义为 `(beginning_at, ending_at]`。

| 时点 | 冻结值 | 含义 |
|---|---|---|
| `knowledge_cutoff` | `2025-01-16T00:00:00Z` | 策略知识截止 |
| `decision_at` | `2025-01-17T00:00:00Z` | 策略决定时点 |
| `beginning_at` | `2025-01-20T02:10:00Z` | 交易会话开盘；只含期初现金 |
| `fill_at` | `2025-01-20T02:31:00Z` | 合成买入成交 |
| `security_settlement_at` | `2025-01-21T02:10:00Z` | 证券交收 |
| `security_sellable_at` | `2025-01-21T02:10:00Z` | T+1 可卖 |
| `ending_mark_observed_at` | `2025-01-21T07:00:00Z` | 合成收盘 mark |
| `ending_at` | `2025-01-21T07:01:00Z` | mark 可得后的期末前缀 |

现有 partial Ledger V2 把 opening 与 fill 放在同一 effective time；完整回放必须把 source-driven opening snapshot 重新物化到冻结的 `beginning_at`，而不是修改 Stage 5C 历史字节或把成交前状态回填到成交后。

## 4. 精确事件 inventory

唯一允许的金融事件序列为：

1. `OPENING_BALANCE`
2. `BUY_TRADE`
3. `BUY_CASH_SETTLEMENT`
4. `SECURITY_SETTLEMENT`
5. `SECURITY_SELLABLE`

本切片不包含 SELL、现金分红、送股、拆并股、配股、退市/现金退出、外部现金流、correction 或 replacement。若输入中出现这些事件，必须在发布 NAV/P&L 前返回 `PRECHECK_BLOCKED`；不得静默忽略。完整 mark coverage 已证明但没有合法期末 mark 时，允许返回 `ABSTAIN_INCOMPLETE_PNL`。

## 5. 会计 golden

案例故意固定为价格不变的控制样本，以验证费用和滑点只计一次：

| 项目 | 冻结值 |
|---|---:|
| 期初现金 / NAV | `100000` |
| 买入数量 | `200` |
| principal cost | `1600` |
| fee | `5.23` |
| tax | `0` |
| slippage | `8` |
| 成交现金流 | `-1613.23` |
| 期末可用现金 | `98386.77` |
| 期末实际/可卖数量 | `200 / 200` |
| 期末 mark | `8` |
| 期末市值 | `1600` |
| 期末 NAV | `99986.77` |
| 总 P&L | `-13.23` |

必须满足 `ending_nav - opening_nav - external_cash_flow = total_pnl`。价格贡献为零，fee 贡献 `-5.23`，slippage 贡献 `-8`；不得再把这些成本与 full-cost unrealized P&L 重复相加。

## 6. 完成门与明确未做

本预注册之后的最小实现必须：

- 在同一次调用内重算精确 Stage 5C 输入和结果；
- 从 source-driven ledger 生成完整有序前缀；
- 计算 beginning/ending NAV、受限 P&L 和 deterministic complete replay；
- 为支持矩阵外输入提供失败关闭负例；
- 保持所有 authority、broker、KB write 和 persistence 字段为 false。

本记录不要求 SQLite、durable persistence、多证券账户、完整公司行动或全证券会计覆盖；也不授权 Stage 6 历史验证、backtest、paper、shadow 或 live。

## 7. 冻结验证

- 预注册合同与现有 source-driven Ledger 切片：`13 passed`；
- Stage 5D 预注册、source-driven Ledger、规则治理与批准治理合计：`32 passed`；
- 全仓：`955 passed, 4 skipped`；4 个 skip 均为 Windows 当前账户不具备测试 symlink 创建权限；
- Ruff check、Ruff format check、mypy、compileall 与 `git diff --check` 全部通过。

这些结果只证明预注册字节、既有 source-driven 基线和零权限边界相互一致。opening rematerialization、mark/NAV、P&L 与 complete replay 仍是下一实现切片。
