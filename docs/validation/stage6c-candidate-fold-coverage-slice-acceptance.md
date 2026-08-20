# Stage 6C Candidate / Fold / Coverage 第二纵向切片验收

验收状态：`completed_with_scope_limits`

验收日期：`2026-08-20`

本记录证明 Stage 6C v0.2 的第二条匿名合成切片已经实现：outcome-blind candidate inventory、2022—2025 时间 fold planner、120-session label/purge、20-session embargo、coverage 数量门及可观察 selection-bias audit。它不读取收益、NAV/P&L、真实数据或 holdout，不执行 bootstrap/Holm/champion，也不产生正式历史结论。

## 1. 实现范围

- `Stage6CSyntheticCandidate`：固定 `economic_event × company × decision_time` 研究单位、Asia/Shanghai 年份、synthetic session index、最长 120-session label、PIT 可得特征、disposition、support flag/reason；类型不包含 return、NAV、P&L 或 label outcome；
- `Stage6CCandidateInventory`：规范排序、候选 ID 与研究单位去重、逐候选 hash 与完整 inventory hash，holdout/performance 字段为 false；
- `plan_stage6c_synthetic_folds`：固定 `WF-2022`—`WF-2025`，训练 label 必须在 `fold_start-20` 之前结束，caller 不能自选训练集；
- 2025 候选的 label 若进入 session `1764` 及之后，仍保留在 inventory/coverage 分母，但不进入 evaluation，避免读取 holdout；
- `evaluate_stage6c_synthetic_coverage`：重算 fold plan，计算总体/年度 coverage、连续特征 SMD、material category coverage 和 supported/unsupported 类别比例差；
- 所有结果 content-addressed、append-only 语义、零 I/O、零 authority。

## 2. 固定 Golden

- candidate count：`40`
- supported / unsupported：`32 / 8`
- aggregate coverage：`0.8`
- 2022—2025 coverage：`0.75 / 0.75 / 0.75 / 0.75`
- continuous SMD：市值、ADV、Beta 均为 `0`
- material category coverage：`0.8`
- material category proportion difference：`0`
- status：`COVERAGE_READY`
- mandatory caveat：`UNSUPPORTED_COUNT_LT_15_NO_PROOF_OF_NO_SELECTION_BIAS`
- inventory hash：`1b9d1e11440731054798fccd217478635f844250626f18380941e7890918a591`
- fold plan set hash：`ee2022abd6dbfe99097aa67c36d9890029319fa0e0a47a1feef0197a042c78d0`
- coverage replay hash：`09ad4af76177ac2bf9330c434a3ff2b8e712d3b87354df3397124ddc0ff87202`

这些是匿名合成 coverage 公式与边界 golden，不是实际样本覆盖证明。

## 3. 失败关闭

已覆盖：

- 总 coverage `<0.80`；
- 任一 walk-forward 年 coverage `<0.70` 或分母为空；
- continuous SMD `>0.10`；
- material category coverage `<0.60`；
- material category supported/unsupported 比例差 `>0.10`；
- label 超过 120 sessions、purge/embargo 边界不满足；
- decision year 与 synthetic session range 不一致；
- holdout decision、holdout label 泄漏、outcome field、重复 candidate/research unit；
- fold plan 与 inventory hash 或确定性重算不一致。

失败结果为 `INSUFFICIENT_EVIDENCE` 或 `PRECHECK_BLOCKED`，候选不得从分母静默删除。

## 4. 权限边界

- `outcome_fields_read=false`
- `synthetic=true`
- `validation_only=true`
- `not_a_complete_stage6c_walk_forward=true`
- `holdout_artifact_read=false`
- `persists_state=false`
- `authority_eligible=false`

当前未实现：真实 candidate discovery、正式 PIT readiness、peer benchmark、已结束交易/30-trade gate、calendar bootstrap、company/risk wild bootstrap、Holm、TWR 与 coverage 联合 orchestrator、消融/压力、champion freeze 或 6D handoff。

## 5. 验证结果

- Candidate/fold/coverage 专项：`11 passed`
- Stage 6 相邻：`96 passed`
- 全仓 pytest：`1060 passed, 4 skipped`
- Ruff check / format check：通过
- mypy：通过，`134` 个 source files 无问题
- compileall：通过
- `git diff --check`：通过

下一条最小切片应实现匿名合成 calendar-block bootstrap、company/risk cluster sensitivity 与 Holm adjusted inference，仍不得打开真实数据或 holdout。
