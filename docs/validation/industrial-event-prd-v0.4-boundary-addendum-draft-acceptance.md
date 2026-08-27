# 产业 PRD v0.4 边界修订补充草案形成验收

验收日期：`2026-08-28`

结论：`PASS_DRAFT_FORMATION_ONLY / PENDING_OWNER / ZERO_RUNTIME_AUTHORITY`

## 精确身份

- PRD v0.3 raw SHA-256：`0f7e6489ee0c5c17d638534337a73c389e70794cf41b821eec7cc92a242c6b03`
- [PRD v0.4 边界修订补充草案](../../产业卡点及事件驱动系统/01_需求/产业卡点及事件驱动系统_PRD_v0.4边界修订补充.md) raw SHA-256：`3587f49786cd3425f5a9dc5dd9df1af364963a7369cb38b8c40511ce00501d36`
- [机器草案](machine/industrial-event-prd-v0.4-boundary-addendum-draft.json) raw SHA-256：`f6dcef60682a2eaf7824fc9039e048e5f1730c0ffd27db55ebaf3a72fc77b79b`
- canonical addendum SHA-256：`da32630be2b2ca9d44a68b7dba5a23fcc92ed4223adc00b7e448e7f541a092c4`

## 验收结论

1. 已批准 PRD v0.3 原始字节保持不变。
2. v0.4 是窄边界补充，不复制或重写完整 PRD。
3. 只替换四处冲突：§5.1、§5.3 第 3 步、§18.1 对象所有权行和 §22 C1 完成门。
4. `StrategyInputRef` 改为 IS 从已验证 KB ReleaseReference 确定性构造；KB legacy v1 只兼容读取。
5. Manifest 必须先独立验证，再投影 IS 输入引用，禁止反向自证。
6. C1a draft contract compatibility 已完成；C1b Published Release consumption 未开始。
7. StrategyRunManifest/Receipt/Observation/Decision 中保存输入引用、PIT、单 root 和撤回阻断等 v0.3 正确语义继续有效。
8. `PRD04-BND-01—08` 全部 pending，没有批准记录或 capability。
9. Stage 6B 重构、根 spike 清理、KB 数据、repin、handoff 和全部运行权限均不在本草案范围。

## 实测质量门

- v0.4 专项：`7 passed`
- Stage 6 边界相邻：`29 passed`
- 全仓 pytest：`1186 passed, 4 skipped`
- Ruff check：`PASS`
- Ruff format check：`164 files already formatted`
- mypy：`Success: no issues found in 159 source files`
- compileall：`PASS`
- `git diff --check`：`PASS`

四项 skip 均来自当前 Windows 账户缺少 symlink 权限，与本草案无关。

## 下一门

Owner 必须原子批准 `PRD04-BND-01—08` 后，本补充才生效。批准也只更新产品需求边界，不授权 Stage 6B 重构、spike 清理、KB 数据源/backfill、Published Release、IS handoff、historical run、holdout 或交易。
