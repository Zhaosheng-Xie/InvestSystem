# Stage 6C 匿名合成 Champion Gate 第四纵向切片验收

验收状态：`completed_with_scope_limits`

验收日期：`2026-08-20`

本记录证明 Stage 6C v0.2 的第四条匿名合成切片已经实现：前三切片同次重算、明确 trade-completion/friction/audit attestations、30-trade/per-fold、fold 稳定性、material increment、drawdown、largest winner、1.5× friction、Holm 与 P0 审计门。结果只是公式 kernel 验收，不是完整 6C phase outcome、真实 champion 或 6D 请求。

## 1. 实现范围

- `Stage6CFoldTwrBinding`：精确绑定 `WF-2022`—`WF-2025` 与各自 TWR case/replay，禁止 tuple 重排改变年份归属；
- `Stage6CSyntheticCompletionAttestation`：显式列出匿名 synthetic 已结束候选，`TRADE_READY` 不再自动等于完成交易；
- `Stage6CSyntheticFrictionAttestation`：精确绑定 `1.5×`、TWR case/replay 和测试报告，并标记 `not_a_real_friction_replay=true`；
- `Stage6CSyntheticAuditAttestation`：只承载 synthetic P0 bias/reconciliation failure count，不能冒充真实偏差审计；
- `Stage6CSyntheticChampionCase`：绑定 inventory/folds/coverage、四 fold TWR、五 comparison/TWR sources、friction/completion/audit；
- evaluator 同次重算 fold/coverage、四 fold TWR、五项 inference/Holm 与 friction TWR；
- completed IDs 必须是 evaluation 中 supported `TRADE_READY` 的子集，非 completed 候选 contribution 必须为零；
- no-trade paired contributions 是 total profit/largest-winner 的唯一来源。

## 2. 精确完成门

匿名公式 gate 同时检查：

- completed trades `>=30`；
- 每 fold completed trades `>=5`；
- 至少 `3/4` folds 净超额为正；
- worst fold `>=-10` percentage points；
- full net benchmark excess `>0`；
- full-vs-best-simple increment `>=2` percentage points；
- maximum drawdown `<=0.15`；
- total net profit `>0`；
- largest winner share `<=0.25`；
- `1.5×` friction net excess `>=0`；
- Holm `ADJUSTED_INFERENCE_READY`；
- P0 bias/reconciliation failures 均为零。

sample 门失败输出 `INSUFFICIENT_EVIDENCE`；表现、风险、摩擦、Holm 或审计门失败输出 `REVISE_REQUIRED`；source/hash/attestation 漂移输出 `PRECHECK_BLOCKED`。

## 3. 固定 Golden

- champion case hash：`5ad40ca789cff6f91098cd8b3def8a007147ef968554b5d506a66040c91cc9cd`
- completion attestation hash：`50d40337f4eb62354531f3c664876c0a3bcd7b92255b4e2d882ff0164111d747`
- friction attestation hash：`a310ee98665583aa79112004f904393b7ab84db668caec3bcd1c45a6eaae6cd0`
- completed trades：`32`
- per fold：`8 / 8 / 8 / 8`
- fold net excess：`5 / 4 / 3 / -5`
- maximum drawdown：`0.05`
- total net profit：`3200`
- largest winner share：`0.03125`
- friction `1.5×` net excess：`1`
- Holm replay hash：`6d1cba706daca4e88b156879805e0ddc0f5280179a9520dee07672385cbeea25`
- status：`GATE_FORMULA_PASSED`
- champion replay hash：`37ef994112a4d1d10c6621c7cabc96f5c5582198d542e3a83f154c95677cb6b9`

这些数字仅验证匿名 synthetic gate 公式；不代表真实样本、收益、显著性或 6D 资格。

## 4. 失败矩阵

已验证：

- inventory/fold/coverage/TWR/inference/friction/audit/completion hash 漂移；
- fold binding 重排；
- 不足 30 笔或任一 fold 少于 5 笔；
- positive folds、worst fold、drawdown 和 friction 失败；
- largest winner/total profit/material increment/full excess/Holm 门；
- P0 bias 或 reconciliation failure 非零；
- 非 completed 或非 evaluation 候选出现非零 contribution；
- friction multiplier 非 `1.5` 或 attestation 冒充真实成本重放；
- completion/audit attestation 冒充真实记录。

## 5. 权限与剩余范围

- `synthetic=true`
- `validation_only=true`
- `not_a_real_6d_request=true`
- `not_a_complete_stage6c_walk_forward=true`
- `formal_historical_run=false`
- `holdout_artifact_read=false`
- `persists_state=false`
- `authority_eligible=false`

当前仍未实现：真实 PIT readiness、peer benchmark construction、真实 Stage 5D completed-trade/P&L/friction sources、参数/experiment ledger、完整消融/延迟/容量/mark 压力、原子 fold seal、正式 `READY_FOR_6D_FREEZE` phase result 或 6D handoff。

## 6. 验证结果

- Champion gate 专项：`7 passed`
- Inference + Champion：`15 passed`
- Stage 6 相邻：`111 passed`
- 全仓 pytest：`1075 passed, 4 skipped`
- Ruff check / format check：通过
- mypy：通过，`138` 个 source files 无问题
- compileall：通过
- `git diff --check`：通过

下一条切片应补匿名 synthetic peer-benchmark construction、experiment/ablation/stress ledger 与统一 phase seal；仍不接真实数据或 holdout。
