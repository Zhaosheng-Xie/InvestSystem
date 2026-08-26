# Stage 6 提供方/消费者边界草案形成验收

验收日期：`2026-08-26`

结论：`PASS_DRAFT_FORMATION_ONLY / PENDING_OWNER / ZERO_RUNTIME_AUTHORITY`

形成基线：`b56e78636c461e3e87820647c17c4bb4e9073f42`

## 验收对象

- [ADR-0002 提议](../adr/ADR-0002-kb-provider-contract-consumer-profile-boundary.md)
  - raw SHA-256：`e18e91423066589b636edd0ca793e6949f45dcf272ce0f81661aa33c3982f22e`
- [Stage 6 历史公共数据消费与验收 Profile v0.3 草案](stage6-historical-public-data-consumer-profile-v0.3-draft.md)
  - raw SHA-256：`79abfe814577dd2da644f5a59310021e6151e1c3a585cc6fa69aa69424e6bbad`
- [v0.3 machine draft](machine/stage6-historical-public-data-consumer-profile-v0.3.0-draft.json)
  - raw SHA-256：`2ea49cf7cd2cd100ecf6fde345b431a75a3f03c226d79fa4689cb0799fce8f6d`
  - canonical profile SHA-256：`76c8d8eceab4c012dc957ac40edfd7d013a7d2a27a8b4edb997815ce81e3ebc0`

## 结论

1. v0.1/v0.2 文档、机器契约和 approval record 原始字节未改变。
2. `S6DATA-01—10` 的 ID、状态、值和 decisions hash 全部保持一致，没有撤销或重写。
3. KB 通用 provider contract 与 IS Consumer Profile 使用独立所有权集合。
4. IS 从通用 root Release identity 构造 `StrategyInputRef`；KB 新核心 Schema 不需要输出该对象。
5. H00985、ADV20/Beta120、单 root、holdout、candidate/coverage 和 authority 均明确归入 IS 消费/运行层。
6. legacy `strategy-input-ref.v1` 和 Stage 3D/6B handoff 继续只读兼容，不原地破坏。
7. `S6BOUND-01—10` 全部保持 pending；没有 approval record 或运行 capability。
8. 本轮没有 KB 数据、网络、Token、holdout、parser、repin、handoff、运行或持久化动作。
9. KB 独立只读审计得到相同职责结论，并补充确认 benchmark 常量、封闭五类公司行动和封闭一级行业需要通用化；这些意见已纳入本草案。

## 实测质量门

- Stage 6 治理专项：`23 passed`
- 全仓 pytest：`1158 passed, 4 skipped`
- Ruff check：`PASS`
- Ruff format check：`157 files already formatted`
- mypy：`Success: no issues found in 153 source files`
- compileall：`PASS`
- `git diff --check`：`PASS`

四项 skip 均来自当前 Windows 账户缺少 symlink 权限，与本草案无关。

## 未关闭门

- KB Stage 7 CI 稳定性修复 PR #9 尚未合入 `main` 并完成合并后主干验收；
- owner 尚未批准 ADR-0002 `S6BOUND-01—10` 和 v0.3 Profile。

上述两项关闭前不得把本草案改为 approved、要求 KB 实现通用 Schema、实现 IS Adapter、repin 或启动数据/策略运行。
