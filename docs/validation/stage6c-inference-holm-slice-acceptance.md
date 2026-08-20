# Stage 6C Bootstrap / Cluster / Holm 第三纵向切片验收

验收状态：`completed_with_scope_limits`

验收日期：`2026-08-20`

本记录证明 Stage 6C v0.2 的第三条匿名合成切片已经实现：source-driven 来源重算、calendar-quarter block bootstrap、company/risk paired contribution cluster sensitivity 和固定五项 Holm-Bonferroni family。它不运行真实数据，不打开 holdout，不执行 champion 完成门，也不产生正式显著性或策略有效结论。

## 1. 实现范围

- `Stage6CInferenceCase`：精确绑定 candidate inventory、fold plans、coverage replay、TWR case/result、fold beginning NAV、两模型 ending P&L、全候选 paired contributions 和三组固定 seed；
- 每条 inference 在同一次调用内重算 fold、coverage 与 TWR，caller 不能注入 result/PASS；
- contribution candidate set 必须与 inventory 完全相等，非 `TRADE_READY` 候选两模型 contribution 必须为零；
- `sum(full contribution - comparator contribution)` 必须等于两模型 ending P&L 差；
- calendar path 对 canonical daily excess factors 按自然季度 block 有放回抽样，保持 block 内顺序，拼接至原 session count 并确定性截断；
- company/risk paths 对 paired contribution rate 做 centered Rademacher cluster wild bootstrap；
- 三条路径均为 `10,000` draws，seed 分别为 `20260820/21/22`；
- Holm 公共入口接收五个 raw inference cases，并内部重算全部 inference 后执行固定 family，拒绝 caller-supplied inference results。

## 2. 固定 Golden

- comparison：`full_vs_market_or_industry_matched`
- inference case hash：`7bf31962d8757fe1a1351fa40cd32b1c7ba884bd08ec9036c12156722b6ebd9e`
- inference replay hash：`49306ecc9b78b4d3e33da72b843773bf3562f9556837a7e9252e645fff24866a`
- calendar raw p-value：`0.0000999900009999000099990000999900009999000099990001`
- company CI lower：`0.00068`
- risk CI lower：`0.0006`
- Holm status：`ADJUSTED_INFERENCE_READY`
- 每项 adjusted p-value：`0.0004999500049995000499950004999500049995000499950005`
- Holm replay hash：`807c717389f5d8540a2577dd87605c09b1c33851bc3288418fef17f72fc0a643`

这些数字只验证匿名合成 resampling/Holm 公式，不是任何真实 Alpha 或显著性证据。

## 3. 失败关闭

已覆盖：

- fold/coverage/TWR source 或 hash 漂移；
- coverage 非 `COVERAGE_READY`、TWR 非 `TWR_RECONCILED`；
- contribution candidate set、company identity 或 P&L 对账不闭合；
- 非交易候选出现非零 contribution；
- NaN、Infinity、指数或其他非规范 decimal；
- Holm family 缺项、重复或包含 blocked inference；
- raw CI 无正证据时 adjusted family 与 primary three-path 同时失败；
- input/contribution 漂移必须改变 replay identity。

失败不得发布 partial paths；所有结果保持 zero authority、zero persistence 和 zero holdout read。

## 4. 权限与未完成项

- `synthetic=true`
- `validation_only=true`
- `not_a_complete_stage6c_walk_forward=true`
- `holdout_artifact_read=false`
- `persists_state=false`
- `authority_eligible=false`

当前未实现：真实 data readiness、peer benchmark construction、30-trade/sample gate、四 fold 稳定性、2 percentage-point material increment、drawdown、largest-winner、1.5× friction、消融/压力、champion freeze、原子 Stage 6C phase result 或 6D handoff。

## 5. 验证结果

- Inference/Holm 专项：`8 passed`
- Stage 6 相邻：`104 passed`
- 全仓 pytest：`1068 passed, 4 skipped`
- Ruff check / format check：通过
- mypy：通过，`136` 个 source files 无问题
- compileall：通过
- `git diff --check`：通过

下一条最小切片应完成匿名合成 sample/fold/material-increment/drawdown/winner/friction champion gate，并统一前三切片为一个仍然 zero-authority 的 Stage 6C phase result。
