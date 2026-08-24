# 产业卡点及事件驱动系统

项目状态：`PRD v0.3 approved；Stage 1、Stage 2A、Stage 2B 已验收；Stage 3—4 completed_with_scope_limits；Stage 5A governance approved；Stage 5B—5D-1 completed_with_scope_limits；Stage 6B completed_with_scope_limits；Stage 6C v0.2 anonymous synthetic kernel completed_with_scope_limits / formal execution not authorized；完整生产策略未实现`
PRD/需求基线日期：`2026-07-31`；工程状态更新：`2026-08-20`
市场范围：`中国 A 股`
当前已授权边界：`Stage 2B、Stage 4/4B 与 Stage 5A—5D 均仅在各自精确批准范围内进行匿名合成 research validation；Stage 3D 不签发 KB current-status authority 或 RunReleaseStatusConfirmation；Stage 5D 当前只覆盖第一条预注册 ENTER/BUY bounded replay；Stage 6B capability 仅授权隔离临时库 admission 实现、只读 HTTPS status validation 与 validation-only confirmation/seal。正式 historical run、策略 evaluator、正式 migration、6C/6D、backtest/paper/shadow/live、真实仓位、账户、订单或券商接入仍未授权`

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
- 状态：`passed_for_stage4_entry`；这是 Stage 4 开工证据，Stage 3 后续已独立完成 3A—3D 并按 scope-limited 边界关闭。
11. [Stage 4 完整 P0 规则清单与批准包 v0.1](03_规则与规格/Stage4完整P0规则清单与批准包_v0.1.md)
    - 状态：`all_14_p0_rules_approved`；4A-1—4A-4 均已批准并实现局部 evaluator，完整编排另由精确 4B capability 授权。
12. [Stage 4 / 4A-1 上下文与产业映射规则包 v0.1](03_规则与规格/Stage4_4A1上下文与产业映射规则包_v0.1.md)
    - 状态：`approved / implemented for stage4_synthetic_research_validation only`；覆盖上下文准入、历史防回填、产业卡点和公司受益晋级。
13. [Stage 4 / 4A-2 事件状态与审计分层规则包 v0.1](03_规则与规格/Stage4_4A2事件状态与审计分层规则包_v0.1.md)
    - 原提案状态：`draft_for_owner_approval`；其原始字节和 draft machine proposal 保留用于批准谱系。
14. [Stage 4 / 4A-2 事件状态与审计分层批准记录 v0.1](03_规则与规格/Stage4_4A2事件状态与审计分层批准记录_v0.1.md)
    - 状态：`approved / implemented for stage4_synthetic_research_validation only`；16 项全部批准，覆盖 E0—E7/E3.5、E4、主体/PIT 与审计分层，不授权任何交易能力。
15. [Stage 4 / 4A-3 四道门、利润分母与情景规则包 v0.1](03_规则与规格/Stage4_4A3四道门利润分母与情景规则包_v0.1.md)
    - 原提案状态：`draft_for_owner_approval`；其原始字节和 draft machine proposal 保留用于批准谱系。
16. [Stage 4 / 4A-3 四道门、利润分母与情景批准记录 v0.1](03_规则与规格/Stage4_4A3四道门利润分母与情景批准记录_v0.1.md)
    - 状态：`approved / implemented for stage4_synthetic_research_validation only`；20 项全部批准，覆盖 Gate 1—2、反事实 NTM 利润分母和四情景，不授权完整 Stage 4 或任何交易能力。
17. [Stage 4 / 4A-4 市场预期、估值与退出规则包 v0.1](03_规则与规格/Stage4_4A4市场预期估值与退出规则包_v0.1.md)
    - 原提案状态：`draft_for_owner_approval`；其原始字节和 draft machine proposal 保留用于批准谱系。
18. [Stage 4 / 4A-4 市场预期、估值与退出批准记录 v0.1](03_规则与规格/Stage4_4A4市场预期估值与退出批准记录_v0.1.md)
    - 状态：`approved / implemented for stage4_synthetic_research_validation only`；24 项全部批准，覆盖 Gate 3—4、估值和退出，不授权完整 Stage 4 或任何交易能力。
19. [Stage 4 / 4B 完整引擎集成与合成验收规则包 v0.1](03_规则与规格/Stage4_4B完整引擎集成与合成验收规则包_v0.1.md)
    - 原提案状态：`draft_for_owner_approval`；其原始字节和 draft machine proposal 保留用于批准谱系。
20. [Stage 4 / 4B 完整引擎集成与合成验收批准记录 v0.1](03_规则与规格/Stage4_4B完整引擎集成与合成验收批准记录_v0.1.md)
    - 状态：`approved / implemented for stage4_synthetic_research_validation only`；16 项全部批准，完整编排和 replay 已实现，不授权任何真实/交易能力。
21. [Stage 4 / 4A-4 合成研究验收记录](../docs/validation/stage4-4a4-acceptance.md)
    - 状态：`completed_with_scope_limits`；只证明 4A-4 局部规则与治理实现通过，不证明完整策略或收益有效。
22. [Stage 4 / 4B 完整引擎集成与合成验收记录](../docs/validation/stage4-4b-acceptance.md)
    - 状态：`completed_with_scope_limits`；只证明完整匿名合成 research-validation 引擎可失败关闭和重放，不证明历史有效性或任何真实交易能力。
23. [Stage 5 / 5A 成交、组合、账本与确定性回放精确规则包 v0.1](03_规则与规格/Stage5_5A成交组合账本与确定性回放精确规则包_v0.1.md)
    - 原提案状态：`draft_for_owner_approval`；原始字节和 [draft machine proposal](03_规则与规格/机器制品/industrial_event_stage5_5a_execution_portfolio_ledger_replay_v0.1.0-draft.rule-bundle.json) 保持不变，用于批准谱系。
24. [Stage 5 / 5A 成交、组合、账本与确定性回放批准记录 v0.1](03_规则与规格/Stage5_5A成交组合账本与确定性回放批准记录_v0.1.md)
    - 状态：`approved for stage5_synthetic_execution_validation only`；四十项全部批准，已形成独立 approved bundle、approval record 和治理 verifier，但没有 Stage 5B—5D 业务 evaluator 或任何真实/交易权限。
25. [Stage 5 / 5A 规则治理批准验收记录](../docs/validation/stage5-5a-governance-acceptance.md)
    - 状态：`completed_with_scope_limits / governance_only`；证明精确批准谱系和失败关闭 capability guard，不证明成交、组合、账本、P&L 或 replay 已实现。
26. [Stage 5 / 5B 历史市场规则与合成成交验收记录](../docs/validation/stage5-5b-market-execution-acceptance.md)
    - 状态：`completed_with_scope_limits`；已实现历史规则、日历、首次可成交、成本/冲击、当前价 Gate 重算及 deterministic synthetic fill，但不含组合、账本、P&L、持久化或真实交易权限。
27. [Stage 5 / 5C 合成组合与内存账本验收记录](../docs/validation/stage5-5c-portfolio-ledger-acceptance.md)
    - 状态：`completed_with_scope_limits`；已实现合成组合风险、五层数量、提交前现金/成本准备金/可卖量、结算投影和截至时点的内存双分录账本，但不含 5D 公司行动、NAV/P&L、持久化或真实交易权限。
28. [Stage 5 / 5D 公司行动、估值、P&L、完整回放与原子持久化精确规则包 v0.1](03_规则与规格/Stage5_5D公司行动估值P&L完整回放与原子持久化精确规则包_v0.1.md)
    - 状态：原 `draft_for_owner_approval` 字节保持不变；48 项已被 owner 整包原子批准，另建[批准记录](03_规则与规格/Stage5_5D公司行动估值P&L完整回放与原子持久化批准记录_v0.1.md)、[approved machine bundle](03_规则与规格/机器制品/industrial_event_stage5_5d_corporate_action_pnl_replay_persistence_v0.1.0.rule-bundle.json)和 [approval record](03_规则与规格/机器制品/industrial_event_stage5_5d_corporate_action_pnl_replay_persistence_v0.1.0.approval.json)。治理 capability 仍只有匿名合成 `research` 权限，不是 5D 业务实现或 SQLite migration。
29. [Stage 5 / 5D 第一条订单/合同历史回放验收](../docs/validation/stage5d-first-order-contract-replay-acceptance.md)
    - 状态：`completed_with_scope_limits`；固定 ENTER/BUY case 已完成同次 Stage 5C 重算、期初 opening 重物化、五事件 Ledger V2、mark/NAV、十八格 P&L 与 deterministic complete/audit replay。SELL、非空公司行动、外部现金流、持久化和真实交易均未授权或实现。
30. [Stage 6 / 6B 真实 HTTPS validation-only seal 验收](../docs/validation/stage6b-live-https-acceptance.md)
    - 状态：`completed_with_scope_limits`；完整根/Source Release 闭包已通过真实 HTTPS 和隔离 confirmation/seal 验收，但没有正式 historical run、evaluator、migration 或交易权限。
31. [Stage 6 / 6C 开发样本、Walk-Forward 与冠军挑战精确规则包 v0.1](03_规则与规格/Stage6_6C开发样本WalkForward与冠军挑战精确规则包_v0.1.md)
    - 状态：`superseded_by_v0.2 / traceability_only`；初始 40 项草案及[草案形成验收](../docs/validation/stage6c-development-walk-forward-draft-acceptance.md)保留原始字节，不再作为待批准目标。
32. [Stage 6 / 6C 开发样本、Walk-Forward 与冠军挑战精确规则包 v0.2](03_规则与规格/Stage6_6C开发样本WalkForward与冠军挑战精确规则包_v0.2.md)
    - 状态：`approved / anonymous synthetic kernel implementation only`；40 项已整包原子批准，集中关闭 holdout 技术隔离、adjusted inference、portfolio/bootstrap、coverage selection bias 和 TWR/benchmark 五项方法风险。独立[批准记录](03_规则与规格/Stage6_6C开发样本WalkForward与冠军挑战批准记录_v0.2.md)和[治理验收](../docs/validation/stage6c-v02-governance-acceptance.md)已形成；正式 run、holdout 和交易仍未授权。
33. [Stage 6 / 6C 匿名合成 Kernel 第一纵向切片验收](../docs/validation/stage6c-synthetic-kernel-slice-acceptance.md)
    - 状态：`completed_with_scope_limits`；实现 typed development projection、opaque holdout commitment、隔离 precheck、零 external flow、exact TWR/benchmark 与 deterministic replay。candidate/fold/coverage/bootstrap/Holm/champion 尚未实现，正式数据与 holdout 权限仍为零。
34. [Stage 6 / 6C Candidate、Fold 与 Coverage 第二纵向切片验收](../docs/validation/stage6c-candidate-fold-coverage-slice-acceptance.md)
    - 状态：`completed_with_scope_limits`；实现 outcome-blind 候选全集、2022—2025 folds、purge/embargo、数量 coverage、SMD 和类别选择偏差门；不读取收益或 holdout。bootstrap/Holm/champion 尚未实现。
35. [Stage 6 / 6C Bootstrap、Cluster 与 Holm 第三纵向切片验收](../docs/validation/stage6c-inference-holm-slice-acceptance.md)
    - 状态：`completed_with_scope_limits`；实现 source-recomputed calendar-quarter bootstrap、company/risk paired-contribution sensitivity 与五项 Holm family。sample/material/drawdown/winner/friction champion gate 尚未实现，正式权限仍为零。
36. [Stage 6 / 6C 匿名合成 Champion Gate 第四纵向切片验收](../docs/validation/stage6c-synthetic-champion-gate-acceptance.md)
    - 状态：`completed_with_scope_limits`；统一前三切片并实现 completed trade/fold/material increment/drawdown/winner/friction/Holm/P0 audit 公式门；明确 `GATE_FORMULA_PASSED` 不是真实 6D 资格。
37. [Stage 6 / 6C Peer Benchmark 与 Experiment Ledger 第五纵向切片验收](../docs/validation/stage6c-peer-experiment-ledger-slice-acceptance.md)
    - 状态：`completed_with_scope_limits`；实现 PIT peer snapshot、三层 fallback、target exclusion、最少五 peers、exact 1/N 权重及 8 ablation + 16 stress 预注册台账。真实 peer returns/experiment 和 phase seal 未实现。
38. [Stage 6 / 6C 匿名合成 Phase Seal 第六纵向切片验收](../docs/validation/stage6c-synthetic-phase-seal-acceptance.md)
    - 状态：`completed_with_scope_limits / synthetic_kernel_complete`；从 raw synthetic sources 同次重算 peer、experiment 和 champion，生成强制 `not_ready_for_6d_freeze=true` 的 zero-authority seal。正式 6C 与 6D 未授权。
39. [Stage 6 / 6C 正式执行 Readiness 审计 v0.1](../docs/validation/stage6c-formal-execution-readiness-audit-v0.1.md)
    - 状态：`BLOCKED_FOR_FORMAL_STAGE6C_EXECUTION`；34 项为 `9 READY / 22 MISSING / 1 BLOCKED / 2 NOT_REQUIRED_WITH_JUSTIFICATION`。下一动作只允许 KB 公共交付 census、IS outcome-blind Stage 5D support census 和 owner 架构决定，不授权正式历史运行、holdout 或 6D。
40. [Stage 5D Outcome-Blind 静态支持 Census v0.1](../docs/validation/stage5d-outcome-blind-static-support-census-v0.1.md)
    - 状态：`STATIC_CODE_SUPPORT_CENSUS_COMPLETE / REAL_CANDIDATE_COVERAGE_NOT_COMPUTABLE`；固定 BUY complete replay 已验收，SELL continuation/FIFO/结算只到 Ledger 层。真实候选 coverage/completed trades 仍为未知，下一最小门是一次全量 EXIT complete replay 预注册。
41. [Stage 5D 普通证券完整生命周期与全量 EXIT 回放预注册 v0.1](../docs/validation/stage5d-normal-lifecycle-exit-replay-preregistration-v0.1.md)
    - 状态：`frozen_for_input_materialization_review`；输入物化与 evaluator 均未授权。冻结连续 BUY→SELL journal、59 个 mark memo events、61 点 session valuation、全量 EXIT、结算尾部和完整三套十八格 P&L golden；必须先物化 exit/calendar/mark/rule input hashes，再另行审阅实现。
42. [Stage 5D 普通证券完整生命周期承重输入物化验收](../docs/validation/stage5d-normal-lifecycle-input-materialization-acceptance.md)
    - 状态：`completed_with_scope_limits / lifecycle_evaluator_unauthorized`；full-EXIT raw Stage 5C case、60-session calendar、59 marks/coverage、exit mandate 和 rule closure 已物化为 input-set `60cad843…9e30`。只验证输入可全量卖出，不包含 lifecycle journal、daily NAV/P&L 或 completed trade。

Stage 2A 已完成固定公共契约的离线验收：`codex/stage2` 从 KB 提交 `58ed9c5cb5302e3e719f1696bed83a03c5d6313b` 固定 20 个官方文件，并验收 provider canonical、catalog、Receipt/Observation、reference fixture 验证/窄投影、显式 Release 留存闭包，以及 SQLite v3 的持久化、run-scoped 当前状态确认、receipt-derived atomic pin 和 legacy v2 quarantine。真实 authority 仍为空；固定 fixture 的状态摘要不能冒充完整 status-event 正文或当前授权。真实只读 acquisition/transport 已由 Stage 3 关闭，原始响应持久化和 run admission 移交 Stage 6/7，策略语义属于 Stage 2B 以后。

Stage 2B 已完成并验收：精确批准规则、可信 fixture registry、E3.5/E4、四道门、利润桥、预期/估值、四类正常结果、pre-engine `BLOCKED`、DecisionRecord 和 replay 均有实现与测试。合成 `TRADE_READY` 与 `SHADOW_ONLY` 始终保持 `FLAT`、零权重、无 approver 且无仓位/订单权限；本批准不得推导为任何真实仓位或其他运行模式授权。

Stage 4 已在 `codex/stage4b` 完成 scope-limited 结仓：14 项 P0 inventory、四个局部批次和独立 4B machine bundle/approval 均精确批准；完整编排器从原始 typed case 重新运行 4A-1—4A-4，禁止注入局部 PASS，并输出统一 Gate/退出视图、局部结果 hash 和 deterministic replay。原 draft proposal 均作为不可变谱系保留。Stage 2B capability、真实 KB 输入、backtest/paper/shadow/live、仓位、组合、成交、P&L 和订单均不能进入该切片；真实首次可成交价、市场规则、交易日历、风险预算和账户账本仍属于待另行授权的 Stage 5。

Stage 5A rule governance 已完成精确批准登记：四十项规则区分 `ENTER/ADD` 与 `REDUCE/EXIT`，固定历史有效市场规则、首次可成交、费用/冲击、容量、风险预算、五层仓位、append-only 双分录账本、公司行动、P&L 和 replay 的合成验证语义。当前 capability 只证明精确规则获准用于未来匿名合成 `research` 验证，不证明相应业务 evaluator 已实现，也不得外推到 backtest、paper、shadow、live、真实账户/仓位/订单。

Stage 5B 已完成市场与成交纵向切片：从同一运行的原始 Stage 4 case/result/replay 出发，按历史时点选择内容寻址规则、交易日历、成本表和冲击曲线，确定首个可成交窗口，重跑当前价 Gate 3/4，并生成内存内 deterministic synthetic fill。该阶段自身不证明组合或账本已经实现。

Stage 5C 已完成组合与账本纵向切片：先在历史候选窗口按 portfolio/risk/account 约束重新计算，再绑定只减不增 constraint 完成 synthetic fill；随后按 injected clock 投影现金、证券、FIFO lot、结算与可卖状态，并写入内存 append-only 双分录 journal。非空公司行动、marks、NAV/P&L、SQLite、durable atomic persistence 和完整 Stage 5 replay 仍属于 5D。

Stage 5D 的 48 项规则继续作为长期治理上限。[第一条订单/合同历史回放](../docs/validation/stage5d-first-order-contract-replay-preregistration.md)现已按[受限验收](../docs/validation/stage5d-first-order-contract-replay-acceptance.md)完成固定 ENTER/BUY case 的 source-driven Ledger V2、mark/NAV、十八格 P&L 与 complete/audit replay；`5D-1` 不追求一次覆盖五类公司行动和全部多证券会计边角。支持矩阵外输入继续在 partial NAV/P&L 前失败关闭。`5D-2` SQLite v4 仍未获执行授权。

## 推荐研发顺序

`需求与边界冻结 → KB 输入契约和独立工程骨架 → 最小规则包 → 合成纵向切片（已完成）→ 正式 Release 只读验收 + 完整策略规则 → 后续另行批准的历史验证 → paper/shadow → go/no-go`

首个实现切片不做全市场自动交易，分两步进入同一个 provider-neutral 策略入口：

1. `InvestSystem 合成策略 fixture → StrategyRunManifest → E3/E3.5/E4 → 产业卡点匹配 → 四道门 → 利润桥/预期/估值 → DecisionRecord + replay_hash`；
2. `精确 KB Published Release → Manifest/制品/Release 状态校验 → ArtifactConsumptionReceipt + ArtifactFetchObservation + ReleaseStatusObservation → 同一策略入口 → 真实 smoke（允许 ABSTAIN）`。

完整组合、首次可成交和 paper 回放属于后续阶段；它们可基于 provider-neutral 输入开发，不等待 KB 部署，但正式历史验证必须等真实 Release E2E 完成。

产业事实与证据由独立的 `InvestmentResearchKB` 生产和发布。本项目不得读取其 SQLite、`raw/`、`staging/` 或内部实现，也不得把策略逻辑写回 KB。首版每次 run 只允许一个精确 `strategy_input_ref`，正式输入只经只读 HTTP API 或不可变导出包进入 `var/cache/kb-releases/`；撤回阻断新 run，历史材料仅供审计重放。策略正例使用本项目明确标记的合成 fixture；不得要求 KB 为策略结果定制事实。
