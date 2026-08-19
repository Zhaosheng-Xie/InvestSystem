# Stage 5D 第一条订单/合同历史回放验收

## 验收结论

状态：`completed_with_scope_limits`

第一条预注册匿名合成 `ENTER/BUY` 历史回放已形成纯内存闭环：同次重算 Stage 5C，按预注册期初重物化 source-driven Ledger V2 opening，重放五个金融事件，计算 beginning/ending NAV、十八格二维 P&L 和 deterministic complete replay。该结论只适用于固定 case、horizon、security/account、mark 和支持矩阵，不证明全量 Stage 5D 证券会计能力或策略收益有效。

## 固定输入与身份

- 分支：`codex/stage5d-bounded-replay`
- 实现父提交：`6c0858a038eda05d65703055a3da420da7063a19`
- 预注册 canonical SHA-256：`f7042c49f72b693d1c9ae5892b1d454be07cf6ad0851c499b47b2fead55492bc`
- Stage 5C case SHA-256：`06a9eaac57fec706b7bda7566494256cd0df045e1bdab2d826a1a85066a1ee62`
- 同次重算 Stage 5C result SHA-256：`daf123cd8ad8418a5794c5aa86f08b66d6c18e3aebd1cdef58cae1b0d88dab59`
- source-driven slice SHA-256：`7872330b5e3a93047e305ada37b07dc5aaa946ffbef40b6ca8c0e5dbc2cddc3f`
- exact event semantic map SHA-256：`5c7eee2e0f53a0c53a37fdce39d5096458a9d010ff081b1da1e328fce72ddcb3`
- exact P&L formula map SHA-256：`00b0576d2a0e040fa33d143a50235ab86db26ecdfdf4897b31b7cf017a2ffd88`

## 实现闭环

公共入口 `evaluate_stage5d_bounded_complete_replay` 只接受冻结的第一条 case，并完成：

1. 通过 exact Stage 5A/5D capability，从 raw `Stage5PortfolioLedgerCase` 同次重算 Stage 5C；不接受 caller-supplied Stage 5C PASS/result。
2. 复核固定 fill、五事件 inventory 与 source slice hash，把原 source opening 从成交时点重物化到 `2025-01-20T02:10:00Z`，随后重新建立完整有序 prior-hash prefix。
3. 从同一规范 journal 分别重放 `J(beginning_at)` 与 `J(ending_at)`；期初只接受 opening，期末接受 opening、BUY、现金结算、证券交收和可卖五事件，未来事件不得进入当前结果。
4. 使用固定、不可执行的 synthetic closing mark 计算 NAV；mark 不是成交价，也不授予任何下单能力。
5. 按批准的 `realization × driver` 十八格公式物化全部原子 cell。当前 case 的唯一非零贡献为 `RS=-8` 与 `RF=-5.23`；`MV=1600` 与 `RB=-1600` 在 price cell 抵消，避免 full cost、fee 和 slippage 重复计价。
6. 把输入、规则/批准身份、同次 Stage 5C 结果、重物化事件、两个 valuation、P&L、状态和零权限字段共同纳入 complete replay hash；相同输入重复执行得到相同字节身份。

## 经济与重放 golden

| 项目 | 固定值 |
|---|---:|
| opening NAV | `100000` |
| ending available cash | `98386.77` |
| ending quantity / sellable | `200 / 200` |
| ending mark / market value | `8 / 1600` |
| ending NAV | `99986.77` |
| price / slippage / fee / tax | `0 / -8 / -5.23 / 0` |
| total P&L | `-13.23` |
| complete replay SHA-256 | `f5ed17d1bf9944d35b7a5afa36e68df0fc40d12c277874ea01d02d1e0bd59225` |
| rematerialized V2 replay SHA-256 | `6bf96f43bdbd1aa8deabd922362241ad628f12f8a74325af7ada4e8973d40127` |
| ending journal head SHA-256 | `e375af373c99b84dac549ddbcb0d8b21ba861931aedeb8a6353c999991a3a836` |
| beginning valuation SHA-256 | `c2172191fdb12693d62e904e2906c489e4ee2aa0d2a26fedfab6f13cca763a2f` |
| ending valuation SHA-256 | `3147da9fb4dd710f91f0c4735eec374d83eadbaab3bc1b9239706aa1d4dc11b9` |
| P&L SHA-256 | `379579fe80bda776fea99c3d9df841395a390178a4067111a2a941c75c637680` |

## 失败关闭与权限

- `SELL`、非空公司行动和非空外部现金流在金融输出前 `PRECHECK_BLOCKED`。
- mark coverage 缺失或不可验证时不发布 journal/NAV/P&L；coverage 完整但没有 eligible ending mark 时保留已完成的 ledger replay，并返回 `ABSTAIN_INCOMPLETE_PNL`，不发布 partial NAV/P&L。
- mark 内容、horizon、case 或固定 fill 任一漂移均失败关闭。
- audit replay 必须引用精确 source complete replay hash；它重算相同经济结果，但 `audit_only=true` 且仍为零外部副作用。
- `authority_eligible=false` 的实质边界保持不变：无 backtest/paper/shadow/live、真实账户/仓位/订单、券商连接、KB 内部读取/写入、SQLite migration 或 durable persistence。

## 验证结果

- 新 bounded replay 专项：`9 passed`
- Stage 5D governance/source slice/preregistration/bounded replay 相邻套件：`41 passed`
- 全仓 pytest：`964 passed, 4 skipped`
- Ruff check：通过
- Ruff format check：通过
- mypy：`110 source files` 通过
- compileall：通过
- `git diff --check`：通过

四个 skip 均为当前 Windows 账户无 symlink privilege 的既有平台 skip，不是本切片失败。

## 未实现与下一门

以下能力继续显式不属于本验收：SELL 的 complete P&L、非空公司行动、外部现金流、多证券/多 lot 会计边角、mark stale/correction 全矩阵、SQLite schema v4、migration、原子 durable commit、正式历史验证以及任何真实交易模式。Stage 5D 的 48 项规则继续作为长期治理上限，但目录或规则存在不得冒充这些能力已经实现。

`5D-2` 仍为 `currently_authorized=false`。后续如需持久化，必须单独形成授权、迁移、崩溃/并发/幂等失败矩阵和独立验收，不能复用本次纯内存 capability 自动开门。
