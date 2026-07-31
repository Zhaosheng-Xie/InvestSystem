# 测试与验证

测试输入必须分为三类并保持物理与语义隔离：

1. **KB 公共契约 fixture**：由 KB 公共契约提供或按其锁定原始字节保存，仅验证 Schema、精确 ID 下载、Manifest/制品哈希、published 状态、游标和幂等；不承担撤回负例或完整策略事实，也不预设策略结论。
2. **InvestSystem 自有完整策略 fixture**：明确标记为 synthetic，包含最小纵向切片所需的 provider-neutral 事实投影，用于验证 E3.5/E4、四道门、利润桥、预期、估值、Decision 和重放，包括获批规则下的 `TRADE_READY` 路径。它不得冒充 KB 正式 Release 或 live 授权。
3. **失败 fixture**：对确定输入注入 Manifest/制品篡改、撤回、不兼容 Schema、缺失制品和未来信息，验证新运行严格 `BLOCKED`，且历史 run 不被改写。

真实 KB Published Release/Context Pack 只用于只读 smoke/E2E。它按事实自然产生结论，允许且在字段不足时应输出 `ABSTAIN`；不得要求 KB 修改事实或专门生产策略正例。

至少包含：

- 五字段 `strategy_input_ref`、确定性 receipt、append-only `ArtifactFetchObservation` / `ReleaseStatusObservation` 和 StrategyRunManifest 契约测试
- 禁止 `latest`、KB 内部路径/import 和共享数据库的隔离测试
- PIT 泄漏测试
- E3.5/E4 与四道门 golden set
- 重复公告和多源冲突测试
- T+1、涨跌停、停牌、一字板和盘后公告成交测试
- 公司行动与历史规则切换测试
- 时间顺序 walk-forward、冻结 holdout、消融和参数邻域测试
- 成本、容量、跳空、相关性与回撤压力测试
- 决策可重放与运行哈希一致性测试

`TRADE_READY`、`SHADOW_ONLY`、`REJECT`、`ABSTAIN` 和 `BLOCKED` 案例必须共同入库；`BLOCKED` 使用独立失败 fixture，任何 `TRADE_READY` 合成正例必须先有对应 `approved` 规则，且不代表 paper/live 授权。

