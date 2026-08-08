# Stage 5 / 5A 规则治理批准验收记录

> 验收日期：`2026-08-08`
>
> 验收状态：`completed_with_scope_limits / governance_only`
>
> 验收分支：`codex/stage5a-rules`
>
> 授权范围：`stage5_synthetic_execution_validation`
>
> 不包含：Stage 5B—5D 业务 evaluator、backtest、paper、shadow、live、真实账户/仓位/订单或券商接入

## 1. 验收结论

owner 已批准《Stage 5 / 5A 成交、组合、账本与确定性回放精确规则包 v0.1》第 13 节全部 40 项。仓库保留原 owner-review 规格与零权限 draft machine proposal 不变，另建批准记录、approved machine bundle 和 approval record；通用 `RuleApprovalScope` 增加精确 `stage5_synthetic_execution_validation`，专用治理 verifier 只有在 bundle、rules、approval、scope、Stage 4B 上游和权限字段全部匹配时才签发 capability。

本验收只证明规则身份和权限边界已由 owner 精确批准并可失败关闭。它没有实现或验证历史市场规则表、交易日历、首次可成交价格、fill、组合风险、五层仓位、PositionLedger、公司行动、P&L、deterministic replay、SQLite migration 或持久化。

## 2. 精确批准身份

| 项目 | SHA-256 |
|---|---|
| 原 owner-review 规格文件 | `df866949bdfcc8eb52451b38155080551291d7539f17b730a01a233cf60a5740` |
| 原 draft canonical bundle | `d0664b6b371ad042218f5d3c6caac9b9f1d1edd3ff475a5f7b36e401ca3d02db` |
| 原 draft canonical rules | `ecc61a4ee3eb3a7e4dea7238c027aca2ac3c2ce145eb40f0fa80bb34085463f5` |
| owner 批准记录文件 | `4862d0c8add5d28db8f24432d4d3958c9de6f73bf74ae7d4754e0290916cbf02` |
| approved canonical bundle | `c69bc7170b608bc6f3e2dd4119e08b13d4f10f03730be115dbc191b47544eeb7` |
| approved canonical rules | `bb7ef84b1287be1111fe95571efa58cd268a65d862b7d235508fc31ccbaf0c69` |
| approval record canonical hash | `5b9536f546337ba38408d255b3fbad68fbbdf6d9ccba9af79b10b6e04ca8cd78` |

精确上游仍为 Stage 4B bundle `ba8886cf85beef084c2a2d3b83446b499c7786fbc3f0e56066fb8cedc8e27e77`、rules `3477d237523ce84239ca1363ad1c8d2e467528ec90acb0034193aeb320740019`、approval record `d809394ef00beab2053795779878025fb1b3b0cd2a49da76302e500ef7f4b2fe` 和 P0 inventory `fc07b10bb17d91b3447504fe7f5b2e346023fd98bb14da991e1a1dd85381bf53`。任一身份漂移均必须形成新版本和新 owner 批准。

## 3. 已实现的治理行为

- 原 draft 保持 `bundle_version=0.1.0-draft`、`declared_status=draft`、40 项 `pending`、空运行模式、无 capability 和全部权限 false。
- approved bundle 使用独立 `bundle_version=0.1.0`，40 项均 `approved`，只允许匿名合成 `research` validation。
- approval record 精确绑定 approved canonical bundle hash、owner、批准时间、scope 和当前 Codex task 来源。
- 通用 approval-record Schema 与 Python `RuleApprovalScope` 同步增加 Stage 5A scope；Stage 4 inventory 的固定 scope 未变化。
- `stage5_governance.py` 检查 bundle/rules/approval canonical hash、40 项顺序、Stage 4B 上游、批准来源和零真实权限。
- 原 draft、错误 scope、错误批准记录、规则语义漂移、上游漂移或任何权限扩张均不能签发 capability。
- 默认 registry 继续为空；只有调用方显式注入精确 approval record 才能请求 capability。

## 4. 专项与全仓验证

Stage 5A 治理专项覆盖：

- checked-in spec、draft、批准文档、approved bundle 和 approval record 的精确 hash；
- 40 项 owner decision 完整、顺序固定且 approved；
- approved boundary 仅有 `research`，所有 `authorizes_*` 均为 false；
- draft 拒绝、paper 权限扩张拒绝、`5% → 6%` 语义漂移拒绝、Stage 4B hash 漂移拒绝；
- Stage 4 scope 与批准来源漂移均拒绝。

最终检查：

- Stage 5A 专项：`7 passed`；
- approval scope Schema 同步专项：`1 passed`；
- 全仓 pytest：`829 passed, 4 skipped`；
- Ruff check、Ruff format、mypy 和 compileall：全部通过；
- 四项 skip 均为当前 Windows 账户无法创建测试 symlink/junction 的既有平台限制，不是 Stage 5A 逻辑跳过。

## 5. 结仓边界与下一步

Stage 5A 只按“精确规则和 capability 治理已完成”结仓，Stage 5 整体仍为 `in_progress`。下一步应按顺序执行：

1. Stage 5B：历史有效 `MarketRuleSet`、交易日历、首次可成交、成本/冲击和合成 fill；
2. Stage 5C：组合风险、五层仓位和 append-only 双分录账本；
3. Stage 5D：公司行动、估值、P&L、deterministic replay 和完整合成验收。

以上后续工作仍只允许精确 `stage5_synthetic_execution_validation`。Stage 5 全部完成前不得进入 Stage 6 backtest；paper、shadow、live、真实账户、真实订单、券商连接和资金部署均须后续独立批准。
