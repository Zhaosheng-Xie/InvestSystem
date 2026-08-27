# 产业 PRD v0.4 边界修订批准验收

验收日期：`2026-08-28`

结论：`PASS / OWNER_APPROVED_GOVERNANCE_ONLY / ZERO_RUNTIME_AUTHORITY`

## 批准材料身份

- PRD v0.3 raw SHA-256：`0f7e6489ee0c5c17d638534337a73c389e70794cf41b821eec7cc92a242c6b03`
- v0.4 pending document raw SHA-256：`3587f49786cd3425f5a9dc5dd9df1af364963a7369cb38b8c40511ce00501d36`
- v0.4 pending machine raw SHA-256：`f6dcef60682a2eaf7824fc9039e048e5f1730c0ffd27db55ebaf3a72fc77b79b`
- canonical addendum SHA-256：`da32630be2b2ca9d44a68b7dba5a23fcc92ed4223adc00b7e448e7f541a092c4`
- [批准文档](../../产业卡点及事件驱动系统/01_需求/产业卡点及事件驱动系统_PRD_v0.4边界修订批准记录.md) raw SHA-256：`ec575435f91e56c271d38f1cf0219537633504faaae1a6ac55f0aee390ef93fa`
- [machine approval record](machine/industrial-event-prd-v0.4-boundary-addendum-approval.json) raw SHA-256：`697736a5a50f9efc64b2961947d0d50f2845b774a974685e4cb9bd0abe1cc234`
- canonical approval record SHA-256：`f2afa2d4199fd80e81906242a2a021b1f3e2fdb04186419551421ef8bd7c0465`
- approved decisions SHA-256：`497e915cb09330fbb1fa7dd5a1c25a1b33e115239020bc7c709d2def9003f1fa`

## 验收结论

1. PRD v0.3 与 v0.4 pending draft 原始字节保持不变。
2. Owner 条件授权正文被精确保存，风险条件已满足。
3. `PRD04-BND-01—08` 与 pending draft 决定正文一致并原子批准。
4. 生效需求基线为 v0.3 主体加 v0.4 窄边界补充；补充只在四个列明冲突点优先。
5. `StrategyInputRef` 由 IS 从验证后的 KB ReleaseReference 构造，Manifest 验证先于投影。
6. C1a draft compatibility 已完成，C1b Published Release consumption 未开始。
7. 策略数值规则、PIT、单 root、撤回阻断和运行对象未被改写。
8. Stage 6B 重构、spike 清理、数据、repin、handoff 和全部运行/交易权限保持 false。

## 实测质量门

- v0.4 draft + approval 专项：`13 passed`
- 全仓 pytest：`1192 passed, 4 skipped`
- Ruff check：`PASS`
- Ruff format check：`165 files already formatted`
- mypy：`Success: no issues found in 160 source files`
- compileall：`PASS`
- `git diff --check`：`PASS`

四项 skip 均来自当前 Windows 账户缺少 symlink 权限，与本次批准无关。

## 下一门

本批准只消除 PRD 内部边界矛盾。IS 继续等待 KB 数据来源、许可、historical PIT 和 raw basis 结论；任何 KB backfill/Release、IS repin/handoff、historical run、holdout 或交易仍须独立授权。
