# Stage 6C v0.2 方法风险集中修订验收

验收状态：`passed / governance_draft_only`

验收日期：`2026-08-20`

本记录证明 Stage 6C v0.2 已在不改动 v0.1 原始字节的前提下，集中关闭 v0.1 方法复核发现的五项重大风险。它不是 owner 批准记录，不签发 capability，也不授权正式 development、walk-forward、holdout、backtest 或交易。

## 1. 冻结身份

- v0.2 specification：[Stage 6C 开发样本、Walk-Forward 与冠军挑战精确规则包 v0.2](../../产业卡点及事件驱动系统/03_规则与规格/Stage6_6C开发样本WalkForward与冠军挑战精确规则包_v0.2.md)
- specification SHA-256：`3886580f1785d4545b02d76ca81ce449577ba406cf1d829efb8b5d4f4e55d368`
- v0.2 draft raw SHA-256：`6f2663feb8b8cef5fd969d2791d2505b82e31ff42071872df0350c2196007afd`
- canonical bundle SHA-256：`a45396cde1e23ab6c05ea03111cf9f72044031a57d6a91dce554e15d6979a72c`
- canonical rules SHA-256：`c64f2b6057355c5e0bca9d597c01ed9f39ae0fd483ee469de86f7c964d8879c8`
- owner-items SHA-256：`7e3eee1c02a8d16e27ec3180379d221302ff3ca1741bb43300f145063f910bd6`
- superseded v0.1 formation commit：`72c9928ded99e0ce56e5af747557c343c93a9134`

v0.2 draft 是对精确 v0.1 字节的 versioned amendment。未来若获批准，approved bundle 必须物化完整规则；runtime 不得动态合并 v0.1/v0.2 JSON 或解析 Markdown。

## 2. 五项关闭结果

1. **Holdout 技术隔离**：6C 只取得不含 2026 记录或可推断 meta 的 development projection；holdout 只暴露 opaque commitment，并使用独立 custodian、CAS/包、OS ACL/凭据、拒绝 canary 与零读取审计。混合 artifact 不得直接进入 6C。
2. **统计门闭合**：full-vs-benchmark 与 full-vs-frozen-best-simple 必须同时通过 calendar-block、company-cluster、risk-cluster 三条 CI；五项 family 的 Holm adjusted p-value 全部 `<=0.05`。
3. **Portfolio 与抽样分层**：唯一 portfolio/NAV/P&L 由 source-driven 全链重放；主 bootstrap 只对 canonical daily excess series 做季度 block 抽样，不把 contribution 行相加冒充组合；company/risk sensitivity 使用 paired contribution-rate cluster wild bootstrap。
4. **Coverage 选择偏差门**：在任何 outcome 可见前冻结 support flag，除 80%/70% 数量门外，增加连续 SMD、类别比例差和 material-category coverage；失败只能 `INSUFFICIENT_EVIDENCE`。
5. **主估计量唯一化**：外部现金流固定为零，冻结每日 NAV/benchmark return、daily excess factor、`252/N` 年化、最短 126 sessions、benchmark 同成本/容量/无法成交/Stage 5D 支持语义。

2026 只允许称为 `locked_historical_holdout`，不冒充严格未知样本；真正未知证据仍属于 Stage 7。

## 3. 权限与当前阻塞

- 40/40 owner items 均为 `pending`；
- `allowed_run_modes=[]`，全部 `authorizes_* = false`，`authority_eligible=false`；
- 没有 approved bundle、approval record、governance capability、runtime evaluator 或 holdout unlock；
- 6B validation-only seal 仍不是正式 run authority；
- 当前受限 Stage 5D-1 仍不满足正式 6C；
- 正式 PIT data readiness、benchmark/mark/SELL/exit/公司行动支持仍待后续真实前置门。

## 4. 验证结果

- v0.2 专项治理：`7 passed`
- Stage 6A/6B/6C v0.1/v0.2 相邻治理：`43 passed`
- 全仓 pytest：`1032 passed, 4 skipped`
- Ruff check / format check：通过
- mypy：通过
- compileall：通过
- `git diff --check`：通过

下一门是 owner 对 v0.2 40 项整包原子批准或调整。在明确批准前不得形成 approved bundle 或实现 kernel。
