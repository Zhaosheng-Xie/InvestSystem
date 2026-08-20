# Stage 6C Peer Benchmark / Experiment Ledger 第五纵向切片验收

验收状态：`completed_with_scope_limits`

验收日期：`2026-08-20`

本记录证明 Stage 6C v0.2 的第五条匿名合成切片已经实现：PIT peer snapshot、三层 peer fallback、target exclusion、最少五个 peer、精确 `1/N` rational 权重，以及 outcome 前注册的 ablation/stress/exploratory ledger。它不计算真实 peer returns，不执行真实消融或压力，不接 holdout，也不签发 Stage 6C phase seal。

## 1. Peer Benchmark Kernel

- 每个 peer member 固定 security、一级行业、市值/Beta 五分位、`available_at`、eligibility、Stage 5D support 和 outcome-blind 边界；
- snapshot 精确绑定 candidate hash/ID/target/decision time/industry 与目标五分位；
- target security 永远排除；未来可得、不可用或 Stage 5D unsupported member 不进入 basket；
- fallback 顺序固定为：
  1. same industry + size quintile + beta quintile；
  2. same size + beta across A-share；
  3. same size across A-share；
- 选择第一个 peer count `>=5` 的层级，使用全部该层合法 peers；
- 权重固定为 exact `1/N` rational，不用浮点近似；
- 不足五个返回 `INSUFFICIENT_EVIDENCE` 且不发布 partial peers；
- basket set 必须覆盖每个 2022—2025 evaluation candidate，不能删除 benchmark 困难样本。

## 2. Experiment Ledger Kernel

required closed world：

- `8` 个 ablation：event semantics、industry/company mapping、gates、profit bridge、valuation、exit、portfolio risk、execution；
- `16` 个 stress：friction 1/1.5/2、delay 0/1/2、NAV 100k/300k、gap/suspension/price-limit/no-liquidity/half-capacity、mark missing/stale/conflict；
- 每项必须在 `execution_started_at` 之前注册，绑定 parent preregistration；
- 每个 registration 恰好一个 outcome，outcome 绑定 registration/source replay/result summary；
- required scenario 各恰好一次，不能用重复 scenario/不同 experiment ID 冒充完整；
- exploratory scenario 可追加，但不能复用 required ID，且永远 `may_enter_current_champion=false`；
- failed/blocked outcome 仍保留，不影响 ledger completeness。

## 3. 固定 Golden

- evaluation candidates：`32`
- ready peer baskets：`32`
- first basket hash：`350c63f6ba28a71249868a2ee68cab056119ce4836c7fd0e66e9dd970e2a4ab0`
- basket set hash：`bce797bf82ab12d8d6b20431e1101208c6fb439d9d31548451abbff3ef1cb011`
- required registrations：`24`
- outcomes：`24`
- experiment ledger hash：`33c75ebd70a2f3e2ab8a9965d3a752fc335468d94269a4bad89fd49b323930b3`

以上均为匿名 synthetic contract golden，不证明真实 peer 数据或压力结果。

## 4. 失败关闭与权限

已验证 target exclusion、三层 fallback、future/outcome member、低于五 peers、snapshot coverage 缺失、注册/结果缺失、post-hoc registration、required scenario 漏项/重复和 exploratory champion 越权。

所有结果保持：

- `synthetic=true`
- `validation_only=true`
- `holdout_artifact_read=false`
- `persists_state=false`
- `authority_eligible=false`

当前未实现真实 quintile/peer universe 构造、peer return/NAV、真实 Stage 5D benchmark support、真实 experiment execution、原子 phase seal 或 `READY_FOR_6D_FREEZE`。

## 5. 验证结果

- Peer/experiment 专项：`9 passed`
- Stage 6 相邻：`120 passed`
- 全仓 pytest：`1084 passed, 4 skipped`
- Ruff check / format check：通过
- mypy：通过，`140` 个 source files 无问题
- compileall：通过
- `git diff --check`：通过

下一切片应从 raw synthetic sources 同次重算前五切片，形成不可注入的统一 Stage 6C synthetic phase seal；仍不得签发真实 `READY_FOR_6D_FREEZE` 或访问 holdout。
