# Stage 6C 匿名合成 Phase Seal 第六纵向切片验收

验收状态：`completed_with_scope_limits / synthetic_kernel_complete`

验收日期：`2026-08-20`

本记录证明 Stage 6C v0.2 批准范围内的匿名合成 kernel 已通过统一 phase orchestration：一个 content-addressed source bundle 包含前五切片 raw inputs，phase evaluator 重建 peer basket set、experiment ledger 和 champion gate 后才生成 zero-authority seal。它不是正式 Stage 6C walk-forward、`READY_FOR_6D_FREEZE` 或真实 6D 请求。

## 1. Source-driven 编排

`Stage6CSyntheticPhaseSourceBundle` 精确包含：

- candidate inventory、fold plans、coverage result；
- 四个 fold TWR cases/results；
- 五个 comparison cases 与五个独立 TWR cases/results；
- friction TWR、friction/completion/audit attestations；
- champion case；
- 每个 evaluation candidate 的 raw peer snapshot；
- parent preregistration、execution start、24 registrations/outcomes；
- 全部 synthetic/validation/holdout/persistence/authority 边界。

peer snapshots、registrations 和 outcomes 规范排序；fold 与 comparison tuples 保持批准顺序。caller 不能提交 peer set、experiment ledger、champion result 或 phase PASS，三者均在 phase 调用内重算。

## 2. 状态优先级

执行顺序：

1. 重建完整 peer basket set；非法来源为 `SYNTHETIC_PHASE_PRECHECK_BLOCKED`，任一不足五 peers 为 `SYNTHETIC_PHASE_INSUFFICIENT_EVIDENCE`；
2. 重建完整 experiment ledger；缺项/post-hoc/hash 漂移为 `PRECHECK_BLOCKED`，任一 outcome 非 COMPLETED 为 `SYNTHETIC_PHASE_REVISE_REQUIRED`；
3. 同次重算 champion gate；映射其 insufficient/revise/precheck 状态；
4. 只有三者全部通过才生成 `SYNTHETIC_PHASE_SEALED`。

失败在昂贵 champion/inference 之前尽早停止，不发布不存在的 child hash。

## 3. 固定 Golden

- phase source bundle hash：`6b04d62a0dec892feb48d964c2fcc29fbb0651c52fecf45dc096bacfb72e5754`
- champion replay hash：`37ef994112a4d1d10c6621c7cabc96f5c5582198d542e3a83f154c95677cb6b9`
- peer basket set hash：`bce797bf82ab12d8d6b20431e1101208c6fb439d9d31548451abbff3ef1cb011`
- experiment ledger hash：`33c75ebd70a2f3e2ab8a9965d3a752fc335468d94269a4bad89fd49b323930b3`
- status：`SYNTHETIC_PHASE_SEALED`
- phase seal hash：`b9f8f41d9f624e2fb78be5c51b37f632c4081b90607af6d832ddfda691afbf5f`

该 seal 只证明匿名 synthetic kernel 编排和边界完整，不证明真实数据、策略有效性或 6D 资格。

## 4. 强制零权限

- `synthetic=true`
- `validation_only=true`
- `synthetic_phase_kernel_complete=true`
- `not_ready_for_6d_freeze=true`
- `not_a_real_6d_request=true`
- `real_holdout_commitment_read=false`
- `holdout_artifact_read=false`
- `formal_historical_run=false`
- `persists_state=false`
- `authority_eligible=false`

任何把 `not_ready_for_6d_freeze` 改为 false 的 seal 在构造时失败。相同 source 内容乱序必须得到相同 source bundle hash。

## 5. 失败矩阵

已覆盖 source bundle 自哈希、real holdout/authority 声明、peer 缺失/不足、experiment 缺项、failed outcome、champion source drift，以及 sealed child hash completeness。所有失败结果仍为 content-addressed、zero-write、zero-authority。

## 6. 验证结果

- Phase seal 专项：`5 passed`
- Stage 6 相邻：`125 passed`
- 全仓 pytest：`1089 passed, 4 skipped`
- Ruff check / format check：通过
- mypy：通过，`142` 个 source files 无问题
- compileall：通过
- `git diff --check`：通过

## 7. 正式 Stage 6C 仍缺少

- owner 独立授权的正式 historical execution scope；
- 正式、可重读复核的 `HistoricalRunAdmissionSeal` 与状态层 migration；
- 真实 PIT candidate/data-readiness projection；
- 真实 peer universe、historical quintiles、peer return/NAV 与 Stage 5D support；
- 真实 completed-trade/P&L/friction/experiment/bias audit sources；
- 真实 holdout custodian、独立 ACL/credential、canary 和 zero-read audit。

在这些条件关闭前，不得把 synthetic phase seal 升级为正式 `READY_FOR_6D_FREEZE`。下一步应先做正式 readiness gap audit 和授权方案，而不是继续堆 synthetic 业务功能。
