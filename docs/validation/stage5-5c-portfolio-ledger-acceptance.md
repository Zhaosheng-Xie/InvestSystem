# Stage 5C 合成组合与内存账本验收记录

> 验收日期：`2026-08-09`
> 状态：`completed_with_scope_limits`
> 批准范围：`stage5_synthetic_execution_validation`
> 上游规则：Stage 5A approved bundle `c69bc7170b608bc6f3e2dd4119e08b13d4f10f03730be115dbc191b47544eeb7`

## 1. 结论

Stage 5C 已完成 synthetic account、组合风险、五层数量、提交前约束、结算/可卖投影与内存 append-only 双分录账本的最小纵向切片。完整编排从原始 Stage 5B case/result/input/replay 重新校验身份和内容绑定，在历史候选窗口按匿名合成账户、组合风险和批准上限生成只减不增 constraint，再由 Stage 5B 市场执行内核重新计算成本、冲击和 Gate 后形成 synthetic fill。

该结论只证明精确批准的匿名合成 `research` validation 能失败关闭并确定性重放。它不读取或修改 KB，不写 InvestSystem SQLite，不处理真实账户、真实仓位或真实订单，也不授权 backtest、paper、shadow、live、券商连接或资金部署。

## 2. 已实现范围

- `ApprovedStage5PortfolioLedgerRules` 只能从精确 Stage 5A approved bundle、approval record、Stage 5B capability 与批准 scope 签发；错误身份、hash、scope 或权限扩张均在业务计算前失败关闭。
- 内容寻址的 synthetic account、position/lot、风险簇、市场状态、stress、sizing、组合批准、settlement terms、initial ledger 与显式空 corporate-action set 均带精确身份、时点和 source hash。target、approval 与 constraint 继续绑定完整 risk evaluation、取整规则和 approved bundle，承重来源漂移会沿 replay 链传播。
- `SyntheticRecoveryRecord` 绑定 prior STOPPED event/head、恢复事件/current head、归因、规则检查和 owner approval；旧的裸 hash/bool 不能恢复风险额度。
- risk evaluator 固定 stress floor、NORMAL/DEFENSIVE/CRISIS、8/12/15/20% drawdown 档、初始/单票/每簇/组合 planned-loss 与 market-value 硬上限；所有 assigned cluster 都必须通过，`REDUCE/EXIT` 保留降险路径。
- target、approved、submitted、filled、actual 五层数量分离。portfolio 未批准或未提交的数量记录为 `unsubmitted`，不会冒充已提交 DAY 订单的取消量。
- Stage 5B standalone v0.1 路径保持独立；Stage 5C 使用 candidate → reduction-only constraint → finalize 两阶段接缝。受约束 evaluator 在历史窗口按最终数量重算 capacity、cost、impact、Gate 3/4，且 candidate、账户/账本 head、风险与批准 source 任一漂移均失败关闭。
- BUY 在提交前同时满足 approved notional/planned-loss、available cash 与 worst applicable transaction-cost reserve；SELL 同时满足 approved notional 与 sellable quantity。任何上限只能缩量或拒绝，不能放大 Stage 4/5B 数量。
- settlement/availability schedule 绑定已选 `MarketRuleSet` 与 `TradingCalendar`，验证 cycle、交易日、PIT、会话和 same-day sellability；当前不存在版本化的市场规则例外契约，任何非空 `special_exception_id` 都失败关闭。该 schedule 只作为内容寻址的 Stage 5C 投影输入，不冒充 KB 或券商状态。
- journal 仅在内存中 append-only 运行，采用双分录、事件级 posting/effect schema、策略/账户隔离、唯一事件、单一 opening、FIFO lot、负现金/超卖防线和一对一 reversal/replacement 校验。
- ledger replay 明确按 `injected_clock` 截止；未来 settlement/availability 仍可作为 scheduled projection 保留，但不会进入当前 cash、position 或 sellable derived state。
- 规范 JSON、SHA-256、稳定事件排序和固定 Decimal context 共同保证同输入的 target、constraint、fill、journal 与 replay hash 可重复。

## 3. 验证证据

- Stage 5A—5C 专项：`93 passed`。
- 全仓 pytest：`915 passed, 4 skipped`；4 项 skip 均为当前 Windows 账户没有创建符号链接权限，不是功能失败。
- Ruff lint：通过。
- Ruff format check：通过，`99 files already formatted`。
- mypy：通过，`98 source files`。
- `compileall -q src tests`：通过。
- `git diff --check`：通过。

关键正反例覆盖：各批准上限独立缩量/归零、worst-cost reserve、SELL notional、缩量后首个候选变化、candidate 漂移、五层数量、市场状态/回撤/公司/多簇/组合硬边界、typed recovery、批准/候选/fill/recovery 各时点的未来 cutoff、sizing source 漂移全链传播、未绑定结算例外、跨策略/账户污染、重复事件、非平衡/非法 posting、负现金、FIFO、超卖、revision chain、幂等与 deterministic partial replay。

## 4. 未实现与下一门

Stage 5C 只接受显式空的 corporate-action set。`CASH_DIVIDEND`、`SHARE_DISTRIBUTION`、`SPLIT_OR_CONSOLIDATION`、`RIGHTS_OR_ALLOTMENT`、`DELISTING_OR_CASH_OUT`、`MARK_TO_MARKET` 和 `EXTERNAL_CASH_FLOW` 仅保留失败关闭的事件边界，不存在业务处理。

marks、NAV、realized/unrealized/period P&L、外部现金流、全局费用资本化 lot-cost 对账、SQLite migration、durable atomic persistence、完整 Stage 5 aggregate replay 与 golden matrix 属于 Stage 5D。当前结果明确标记为 partial/as-of in-memory replay，不得冒充完整 Stage 5 replay。

Stage 6 仍不能开始：除 Stage 5D 外，Stage 3C tcloud 与 Stage 3D 精确正式 Context Pack 策略 smoke 也尚未完成。
