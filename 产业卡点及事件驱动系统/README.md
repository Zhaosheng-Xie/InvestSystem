# 产业卡点及事件驱动系统

项目状态：`PRD v0.3 approved；Stage 1、Stage 2A、Stage 2B 已验收；Stage 3 deferred；Stage 4/4A-1 completed、4A-2 next；完整策略未实现`
PRD/需求基线日期：`2026-07-31`；工程状态更新：`2026-08-03`
市场范围：`中国 A 股`
当前已授权边界：`Stage 2B 与 Stage 4/4A-1 均仅匿名合成 research validation；完整 Stage 4 runtime capability 关闭；不授权 backtest/paper/shadow/live、仓位或订单`

## 系统一句话定义

先找到产业链中供给响应慢、替代困难且利润可能向上市公司传导的关键约束，再用可核验事件确认盈利路径、预期差和时点，最后通过组合风险预算决定是否交易、交易多少和何时退出。

## 目录

- `01_需求/`：产品需求、目标、边界、验收标准、待确认决策。
- `02_研究/`：框架审计、外部证据、来源登记与研究假设。
- `03_规则与规格/`：下一阶段的状态机、字段、信号和风险规则。
- `04_数据/`：KB Published Release 输入契约、验证 receipt、策略数据投影和运行快照；不保存 KB raw/staging。
- `05_实现/`：只读 Release 消费、策略引擎、回测和 paper/shadow 执行实现。
- `06_测试与验证/`：golden cases、回放、样本外、压力与偏差测试。
- `07_运行与复盘/`：每日/每周操作手册、决策日志和版本发布。

## 当前交付

1. [需求文档 v0.3](01_需求/产业卡点及事件驱动系统_PRD_v0.3.md)
   - 状态：`approved / 2026-07-31`；批准需求和边界，不代表规则或策略已经实现。
   - 历史基线：[需求文档 v0.2](01_需求/产业卡点及事件驱动系统_PRD_v0.2.md)、[需求文档 v0.1](01_需求/产业卡点及事件驱动系统_PRD_v0.1.md)
2. [框架审计与研究结论 v0.1](02_研究/框架审计与研究结论_v0.1.md)
3. [来源登记表 v0.1](02_研究/来源登记表_v0.1.md)
4. [Alpha 竞争假设补充研究 v0.1](02_研究/Alpha竞争假设补充研究_v0.1.md)
5. [ADR-0001：KB/InvestSystem 边界及 Release 消费政策](../docs/adr/ADR-0001-kb-investsystem-boundary.md)
6. [Stage 1 工程与机器契约骨架验收记录](../docs/validation/stage1-acceptance.md)
7. [Stage 2A 离线 Release 消费与准入内核验收记录](../docs/validation/stage2a-acceptance.md)
8. [最小订单合同纵向切片规则包 v0.1](03_规则与规格/最小订单合同纵向切片规则包_v0.1.md)
   - 状态：`approved / implemented for stage2b_synthetic_validation only`；22 项已全部确认并实现于最小合成切片，不授权 backtest、paper、shadow、live、仓位或订单。
9. [Stage 2B 正式验收记录](../docs/validation/stage2b-acceptance.md)
   - 状态：`completed`；只证明最小合成 research-validation 路径可运行、可审计和可重放，不证明策略有效。
10. [Stage 2 进入 Stage 4 复核](../docs/validation/stage2-reentry-audit.md)
    - 状态：`passed_for_stage4_entry`；Stage 3 按 owner 决定延后，不冒充完成。
11. [Stage 4 完整 P0 规则清单与批准包 v0.1](03_规则与规格/Stage4完整P0规则清单与批准包_v0.1.md)
    - 状态：`partially_approved`；4A-1 四项已批准并实现，其余 10 项仍为 `draft`，完整 Stage 4 runtime capability 关闭。
12. [Stage 4 / 4A-1 上下文与产业映射规则包 v0.1](03_规则与规格/Stage4_4A1上下文与产业映射规则包_v0.1.md)
    - 状态：`approved / implemented for stage4_synthetic_research_validation only`；覆盖上下文准入、历史防回填、产业卡点和公司受益晋级。

Stage 2A 已完成固定公共契约的离线验收：`codex/stage2` 从 KB 提交 `58ed9c5cb5302e3e719f1696bed83a03c5d6313b` 固定 20 个官方文件，并验收 provider canonical、catalog、Receipt/Observation、reference fixture 验证/窄投影、显式 Release 留存闭包，以及 SQLite v3 的持久化、run-scoped 当前状态确认、receipt-derived atomic pin 和 legacy v2 quarantine。真实 authority 仍为空，HTTP/export 都在 I/O 前失败关闭；固定 fixture 的状态摘要不能冒充完整 status-event 正文或当前授权。真实 acquisition/current status、认证 transport 和原始响应留存归入 Stage 3，策略语义属于 Stage 2B 以后。

Stage 2B 已完成并验收：精确批准规则、可信 fixture registry、E3.5/E4、四道门、利润桥、预期/估值、四类正常结果、pre-engine `BLOCKED`、DecisionRecord 和 replay 均有实现与测试。合成 `TRADE_READY` 与 `SHADOW_ONLY` 始终保持 `FLAT`、零权重、无 approver 且无仓位/订单权限；本批准不得推导为任何真实仓位或其他运行模式授权。

Stage 4 已在 `codex/stage4` 完成 4A-1：专属 `stage4_synthetic_research_validation` scope、14 项 P0 inventory、4A-1 精确 machine bundle/approval 和失败关闭 evaluator 已建立。通用 registry 仍为空；只有显式注入的精确批准可运行 4A-1。Stage 2B capability、真实 KB 输入、backtest/paper/shadow/live、仓位和订单均不能进入该切片，剩余十条未批准规则不能获得完整 capability。

## 推荐研发顺序

`需求与边界冻结 → KB 输入契约和独立工程骨架 → 最小规则包 → 合成纵向切片（已完成）→ 正式 Release 只读验收 + 完整策略规则 → 后续另行批准的历史验证 → paper/shadow → go/no-go`

首个实现切片不做全市场自动交易，分两步进入同一个 provider-neutral 策略入口：

1. `InvestSystem 合成策略 fixture → StrategyRunManifest → E3/E3.5/E4 → 产业卡点匹配 → 四道门 → 利润桥/预期/估值 → DecisionRecord + replay_hash`；
2. `精确 KB Published Release → Manifest/制品/Release 状态校验 → ArtifactConsumptionReceipt + ArtifactFetchObservation + ReleaseStatusObservation → 同一策略入口 → 真实 smoke（允许 ABSTAIN）`。

完整组合、首次可成交和 paper 回放属于后续阶段；它们可基于 provider-neutral 输入开发，不等待 KB 部署，但正式历史验证必须等真实 Release E2E 完成。

产业事实与证据由独立的 `InvestmentResearchKB` 生产和发布。本项目不得读取其 SQLite、`raw/`、`staging/` 或内部实现，也不得把策略逻辑写回 KB。首版每次 run 只允许一个精确 `strategy_input_ref`，正式输入只经只读 HTTP API 或不可变导出包进入 `var/cache/kb-releases/`；撤回阻断新 run，历史材料仅供审计重放。策略正例使用本项目明确标记的合成 fixture；不得要求 KB 为策略结果定制事实。
