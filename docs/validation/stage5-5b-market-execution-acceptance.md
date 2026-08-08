# Stage 5B 历史市场规则与合成成交验收记录

> 验收日期：`2026-08-08`
> 状态：`completed_with_scope_limits`
> 批准范围：`stage5_synthetic_execution_validation`
> 上游规则：Stage 5A approved bundle `c69bc7170b608bc6f3e2dd4119e08b13d4f10f03730be115dbc191b47544eeb7`

## 1. 结论

Stage 5B 已完成首条市场与成交纵向切片。实现从同一运行的原始 `Stage4CompleteSyntheticCase` 和精确 `Stage4CompleteResult` 开始，校验 input/replay 绑定，然后按历史执行时点选择内容寻址的 `MarketRuleSet`、交易日历、证券会话状态、成本表和冲击曲线；只在首个满足条件的窗口生成确定性 synthetic intent/fill。

该结论只证明匿名合成 `research` validation 能失败关闭并确定性重放。它不读取 KB 内部状态，不写 SQLite，不维护组合/账本/P&L，不连接券商，也不授权 backtest、paper、shadow、live、真实账户、真实仓位或真实订单。

## 2. 已实现范围

- `ApprovedStage5MarketExecutionRules` 只能由精确 Stage 5A bundle、approval record 和批准 scope 签发；固定 `0.05` 参与率、三日入场窗口、`DAY` 和 Stage 4 Gate 4 的 `0.15/2.00` 阈值。
- 所有 5B 输入均使用 `id/version/hash/supersedes` 身份；运行时验证自排除内容哈希，拒绝篡改、历史区间重叠、规则缺口、deferred/suspended/repealed 规则和当前规则回填历史。
- `execution_eligible_from=max(decision_at,strategy_processing_completed_at,synthetic_approval_at)`；日期精度不足时移动到下一完整交易日；盘中窗口要求完整时间戳和完成后的可用性。
- 提案参考价严格位于处理完成与合成批准之间，并固定为 `not_executable_price=true`，不会进入 fill。
- 首次可成交按交易日、会话和观察时间顺序选择；停牌、一字涨停买入、一字跌停卖出、无对手流动性、零成交量和不可证明报价均不可成交。
- 日线低精度价格只能使用 `turnover/volume`，且要求批准前已具备下一完整开盘资格；不使用 OHLC 均价，也不声称盘中时点或排队顺序。
- 数量按历史有效 lot 向下取整；容量为 `floor_to_lot(window_volume*0.05)`，等号可通过；最小 lot 超过任一上限时不成交。
- 成本表按日期、场所、证券类型、方向和账户费率版本选择，分别计算交易所费、监管费、过户费、税费、佣金和最低佣金，并按明确单位向不利方向取整。
- 冲击曲线要求参与率严格递增、逆向滑点单调不减，仅线性插值且禁止外推；滑点进入 fill price，费用和税单列，避免双重计数。
- 使用原始 Stage 4 case 的估值基准冻结 E4 前公开经济预期，在当前 synthetic executable price 重新计算市场反映状态、Gate 3 和 Gate 4；`ENTER/ADD` 非 PASS 时数量归零，`REDUCE/EXIT` 的 Gate 非 PASS 不阻止降风险路径。
- synthetic order 为不可变 `DAY` intent；部分成交不超过最新容量，剩余量在窗口结束取消；事件按 `event_time/event_type_priority/stable_event_id` 排序，不含随机数或 Monte Carlo。
- Stage 5B replay 包含完整 case、Stage 4 input/result/replay、批准身份、市场/成本/冲击输入、attempt、intent、fill、事件、代码提交、配置哈希和 injected clock；排除墙钟噪声、进程和机器路径。

## 3. 验证证据

- Stage 5A/5B 专项：`19 passed`。
- 全仓 pytest：`841 passed, 4 skipped`；4 项 skip 均为当前 Windows 账户没有创建符号链接权限，不是功能失败。
- Ruff lint：通过。
- Ruff format check：通过。
- mypy：通过，`87 source files`。
- `compileall -q src tests`：通过。
- `git diff --check`：通过。

覆盖的关键负例包括：规则有效区间重叠、制品哈希漂移、缺失历史成本、非单调冲击曲线、停牌、一字涨停买入、当前价格 Gate 拒绝、三日未成交到期和日期精度不足。

## 4. 未实现与下一门

Stage 5B 没有实现 Stage 5A 完整输入合同中的 synthetic account、风险簇、市场状态、现金可负担量、公司行动、initial ledger、双分录、持仓可卖量、结算、NAV、P&L 或 durable atomic replay。它们分别属于后续 Stage 5C（组合、风险、账户、账本）和 Stage 5D（公司行动、P&L、持久化与完整 replay）并须在各自范围内验收。

Stage 6 仍不能开始：除 Stage 5C—5D 外，Stage 3C tcloud 与 Stage 3D 正式 Context Pack 策略 smoke 也尚未完成。
