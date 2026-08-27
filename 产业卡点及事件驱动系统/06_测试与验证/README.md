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

## Stage 6A 历史验证治理批准

[Stage 6 / 6A 历史验证预注册与准入精确规则包](../03_规则与规格/Stage6_6A历史验证预注册与准入精确规则包_v0.1.md)35 项已获 owner 原子批准。[正式治理验收](../../docs/validation/stage6a-historical-validation-governance-acceptance.md)固定了原 specification/draft、独立批准文档、approved bundle、approval record 和 fail-closed verifier；PRD 中所有数值通过线仍保持 `hypothesis`。

6A capability 只允许形成 6B 待审批草案，不执行历史数据、不打开 holdout、不签发 `RunReleaseStatusConfirmation`，也不授权 backtest/paper/shadow/live。批准专项 `38 passed`、治理相邻 `195 passed`、全仓 `978 passed, 4 skipped`，Ruff/format/mypy/compileall/diff-check 全部通过。这些结果只证明治理身份和权限边界，不能解释为策略有效性或 Stage 6 已完成。

## Stage 6B 准入与原子留存治理

[Stage 6 / 6B 历史准入、状态确认与原子留存精确规则包](../03_规则与规格/Stage6_6B历史准入状态确认与原子留存精确规则包_v0.1.md)32 项已由 owner 原子批准；原 specification/draft 保持不变，独立 approved bundle、approval record 和 fail-closed validation capability 已形成。[6B 治理批准验收记录](../../docs/validation/stage6b-historical-admission-governance-acceptance.md)验证 exact lineage、部分批准拒绝、scope 隔离、正式历史/migration/交易权限扩张失败关闭。

[6B 离线实现验收](../../docs/validation/stage6b-historical-admission-offline-acceptance.md)已闭合纯 contracts/issuer、KB provider status adapter、根级 HTTP/封存编排、隔离 validation state/cache、完整闭包原子 seal、失败零写、并发幂等和架构隔离；全仓 `1014 passed, 4 skipped`。旧 Stage 3 Token 已撤销，尚未形成本轮真实 HTTPS validation-only confirmation/seal，因此 6B 仍是 `in_progress`，不授权 evaluator、正式 migration、6C/6D 或任何交易模式。

`TRADE_READY`、`SHADOW_ONLY`、`REJECT`、`ABSTAIN` 和 `BLOCKED` 案例必须共同入库；`BLOCKED` 使用独立失败 fixture，任何 `TRADE_READY` 合成正例必须先有对应 `approved` 规则，且不代表 paper/live 授权。

## Stage 6 最小历史公共数据消费契约治理

[Stage 6 最小历史公共数据消费契约 v0.2](../../docs/validation/stage6-minimum-public-data-consumption-contract-v0.2.md)已原子批准 `S6DATA-01—10`，Beta benchmark 固定为 CSI `H00985` 且禁止 fallback。[治理验收](../../docs/validation/stage6-minimum-public-data-consumption-contract-v0.2-acceptance.md)中的机器契约和独立 approval record 固定 v0.1 lineage、十项决定、三 source families + 单一 root、SSE/SZSE universe、ADV20/Beta120、五类公司行动、100% identity hard gates、transport v1 与 repin 顺序。

该治理批准没有读取 KB 数据，也不授权真实 handoff、backfill、parser、candidate、coverage、historical run、migration 或 holdout。专项测试必须同时验证 v0.1 字节未变、v0.2 canonical/raw identity、十项原子批准、H00985 无 fallback 和所有权限为 false。

## Stage 6 提供方/消费者边界草案

[ADR-0002 提议](../../docs/adr/ADR-0002-kb-provider-contract-consumer-profile-boundary.md)与 [Stage 6 消费与验收 Profile v0.3 草案](../../docs/validation/stage6-historical-public-data-consumer-profile-v0.3-draft.md)在草案形成时只包含待批准职责边界：KB 保持通用，IS 通过 Adapter 构造 `StrategyInputRef` 并持有 H00985/ADV/Beta、holdout、candidate/coverage 和 authority。[草案形成验收](../../docs/validation/stage6-consumer-boundary-draft-acceptance.md)固定 v0.2 字节与十项批准、验证十项 `S6BOUND` 全部 pending，并要求所有数据/运行权限为 false。

[Stage 6 提供方/消费者边界批准记录](../../docs/validation/stage6-provider-consumer-boundary-approval-v0.1.md)在两仓独立审计一致和 KB 修复后主干全绿的前提下原子批准 `S6BOUND-01—10`。[治理批准验收](../../docs/validation/stage6-consumer-boundary-governance-acceptance.md)证明 pending draft 字节保持不变，独立 machine approval record 固定条件授权；KB Schema 实现、IS Adapter/repin、数据和运行权限仍全部为 false。

[Stage 6 通用 KB 契约离线 Adapter 正式验收](../../docs/validation/stage6-generic-kb-offline-adapter-acceptance.md)固定 `snapshot-lock.json` 的 19 个 provider blobs，验证 16 个 active Schema、registry 和九类 synthetic examples；同时验证 root identity、四依赖 closure、客观 incomplete profile、H00985 无 fallback/许可阻塞、ADV20 complete hash-basis-only、Beta120 118-session incomplete，以及纯 Decimal 20/120 window 重算。未知字段、文件篡改、非规范 Decimal、负成交额、窗口不足和零方差均失败关闭；真实 Release、transport、candidate、coverage、holdout 和交易仍不在测试范围。

[产业 PRD v0.4 边界修订补充草案形成验收](../../docs/validation/industrial-event-prd-v0.4-boundary-addendum-draft-acceptance.md)固定 v0.3 原始 SHA-256、v0.4 文档/机器草案身份、四个 replacement、C1a/C1b 分离和八项 pending owner decision；同时证明补充不批准 Stage 6B 重构、spike 清理、数据、repin、handoff 或任何运行模式。

[产业 PRD v0.4 边界修订批准记录](../01_需求/产业卡点及事件驱动系统_PRD_v0.4边界修订批准记录.md)按 owner 条件授权，在风险复核无阻塞 P0/P1 后原子批准 `PRD04-BND-01—08`。[治理批准验收](../../docs/validation/industrial-event-prd-v0.4-boundary-addendum-governance-acceptance.md)证明 pending draft 字节保持不变，独立 machine approval record 固定批准；Stage 6B 重构、spike 清理、数据、repin、handoff 和运行权限仍全部为 false。

## Stage 6C 正式执行 Readiness 审计

[Stage 6C 正式执行 Readiness 审计 v0.1](../../docs/validation/stage6c-formal-execution-readiness-audit-v0.1.md)在匿名 synthetic phase seal 后检查 34 个正式前置门，结论为 `NO_GO_FOR_FORMAL_STAGE6C_EXECUTION`。其中 `9 READY / 22 MISSING / 1 BLOCKED / 2 NOT_REQUIRED_WITH_JUSTIFICATION`；现有证据只能支持继续做只读 census 和方案设计，不能启动 development/walk-forward、读取 holdout、签发 6D 或创建正式 migration。

审计没有实际历史数据 profile，因此不报告虚构的行数、缺失率或 coverage。下一次 readiness 更新必须由 KB 公共交付 census 与 IS outcome-blind Stage 5D support census 提供真实、内容寻址的证据。

[IS Stage 5D outcome-blind 静态支持 census](../../docs/validation/stage5d-outcome-blind-static-support-census-v0.1.md)现已完成代码支持面盘点：20 项分为 `6 bounded complete / 4 ledger-only / 4 fail-closed / 4 not implemented / 2 not evaluable`。它确认 SELL/FIFO/卖出资金结算已有底层验收，但没有一般化 EXIT complete replay、daily NAV 或完整 P&L；候选分母、coverage、selection-bias 和 completed-trade 数全部保持 `null`。该 census 不读取收益、label、holdout 或 KB 内部数据，也不授予正式 Stage 6C 权限。

[Stage 5D 普通证券完整生命周期与全量 EXIT 回放预注册](../../docs/validation/stage5d-normal-lifecycle-exit-replay-preregistration-v0.1.md)已冻结连续 BUY lineage、全量 EXIT、61 点 valuation path、60 returns、59 个 canonical mark memo events、结算尾部和完整 P&L 重分类 golden。它明确禁止把既有 partial SELL fixture 冒充 completed trade，并要求 target/peer 将来复用同一证券中立 valuation seam。当前状态为 `frozen_for_input_materialization_review`：必须先物化并冻结 exit/calendar/mark/rule inputs，复核后才可另行批准 evaluator。

[Stage 5D full-EXIT 承重输入物化验收](../../docs/validation/stage5d-normal-lifecycle-input-materialization-acceptance.md)现已固定六个输入 component hashes 与总 input-set `60cad843…9e30`；现有 Stage 5C 只用于证明 raw input 可完成 `SELL 200` 并归零持仓。新增合同没有 `evaluate_*`、I/O 或持久化入口，全部 result/replay hashes 仍为 `null`。专项 `14 passed`、Stage 5C/5D 相邻 `94 passed`、全仓 `1120 passed, 4 skipped`。

[Stage 5D 普通证券完整生命周期 evaluator 验收](../../docs/validation/stage5d-normal-lifecycle-evaluator-acceptance.md)已完成精确 input-set gated 的同次 entry/EXIT 重算、8-event financial V2、59 mark memo、61-point valuation、十八格 P&L、synthetic completed-trade 与 audit replay。机器 complete replay 为 `277181e9…79ba`；专项 `9 passed`、相邻 `133 passed`、全仓 `1129 passed, 4 skipped`。它不读取真实候选或 KB 内部数据，不授权 formal Stage 6C 或交易。

[Stage 6 KB 历史公共数据 handoff 验收 runbook](../../docs/validation/stage6-kb-historical-handoff-acceptance-runbook-v0.1.md)已固定交付身份、真实 Published Release、数据域/引用、PIT/lineage 和 holdout/outcome 五道门；当前所有 observed-input 和 authority 字段均为 false。Windows CI 的 `Asia/Shanghai` 时区数据已加入直接 hash-locked `tzdata` runtime dependency，避免依赖 runner 系统数据库。

[Stage 6 最小历史公共数据消费契约草案](../../docs/validation/stage6-minimum-public-data-consumption-contract-draft-v0.1.md)现已把 KB NOT_READY 声明转成 provider-neutral P0/P1 需求、ADV20/Beta120 推荐口径、universe/coverage 门、单 root Release 和 Schema/repin 方案。草案未读取 KB 数据，十项 owner decision 全部 pending，不构成 handoff、candidate 或 coverage capability。

## Stage 3D 已验收证据

[Stage 3D 真实公网 Context Pack 验收](../../docs/validation/stage3d-context-pack-http-acceptance.md)固定了正式 Context Pack/Evidence Release、两份主制品和两份公开 Schema，并验证：

- 真实公网 Release/Manifest/完整 Status 与 `published` 状态；
- artifact 字节、响应头、Context Pack 查询/下载等值和固定 transport snapshot；
- Document/Span/Fact/CandidateEvent/EvidenceLink/EvidenceRef、node/edge/source/company mapping 引用闭包和 PIT；
- provider-neutral 输入、四制品消费 Receipt、三类 validation-only Observation 和 StrategyRunManifest；
- missing/conflict/counterexample/unrecoverable 信息不丢失，材料不足时正确 `ABSTAIN`；
- `authority_eligible=false`、无确认、零持久化、零运行或交易权限。

Stage 3D 专项为 `18 passed`，全仓为 `951 passed, 4 skipped`。owner 已按这一只读 mapping/smoke 边界关闭 Stage 3；该结论不证明策略有效，也不打开新 run authority。historical-validation admission 属于 Stage 6，当前 shadow/paper admission 属于 Stage 7。

## Stage 2B 已验收证据

Stage 2B 的[正式验收记录](../../docs/validation/stage2b-acceptance.md)固定：

- 24 个正常策略向量和 10 个独立 admission failure 向量；
- 四类正常结果及 pre-engine `BLOCKED`；
- Gate 等号、略低、超过 100 位精度、PIT、证据独立、三值逻辑和短路边界；
- 24 个正常向量 evaluator 恰好调用一次，所有输入/治理错配 evaluator 调用为零；
- 真实 runner 的 StrategyRunManifest、DecisionRecord、Replay 与 JSON Schema 闭合；
- 全仓 `617 passed, 4 skipped`，两轮独立审阅 `P0=0 / P1=0`。

这些证据只适用于匿名合成 `research` validation。历史回测、paper、shadow、live、仓位、订单及策略有效性仍没有授权或验证结论。

## Stage 4 当前测试边界

Stage 4 的 4A governance、4A-1—4A-4 局部合成执行、既有 draft 谱系和 4B 完整合成编排测试验证：

- 14 项 Stage-4-owned P0 requirement 完整且不重复；
- 未批准项不能声明 approval ID 或 runtime machine rule；
- 完整 capability 要求每项正例、反例、边界例和 `ABSTAIN` 测试引用；
- Stage 2B scope、inventory hash 漂移、权限漂移、rule-module 缺失和默认空 registry 均失败关闭；
- 4A-1 的 `FR-CTX-001/002`、`FR-IND-001/002` 各自具有正例、反例、边界例和 `ABSTAIN`；
- PIT/历史半开区间、十域覆盖、至少两个独立证据组、晋级前置条件和跨规则短路均为确定性语义；
- 当前 inventory 的 14 项、四个局部批次和独立 4B bundle 均为精确 `approved`，且零 backtest/paper/shadow/live/仓位/组合/成交/P&L/订单权限；
- 4A-2 原 draft 精确绑定文字规格、canonical bundle/rules hash 和 16 项 `pending` owner 决策并保持不变；
- 新 approved bundle/approval record 精确绑定 owner 对全部 16 项的 scope-limited 批准；默认 registry、伪造 approval、语义漂移、错误 scope 与权限漂移均失败关闭；
- `FR-EVT-001—004` 各自具有正例、反例、边界例和 `ABSTAIN`，覆盖事件护照、E3.5/E4、终态、重复观测、显式降级、规则迁移、主体/PIT、知识依赖 DAG 与人工覆盖批准。
- 4A-3 原 draft 精确绑定文字规格、canonical bundle/rules hash、已批准 4A-1/4A-2 bundle 和 20 项 `pending` 决策，并保持不可执行；
- 新 approved bundle/approval record 精确绑定 owner 对 20 项的 scope-limited 批准；默认/伪造 registry、语义漂移、错误 scope 和权限漂移均失败关闭；
- `FR-GATE-001—003` 覆盖 Gate 1 短路、E3.5 标签、PIT/外汇/哈希、反事实利润桥与区间、`standard/fragile` 轨、事件利润/FCF、四情景、概率和版本语义；Gate 3—4 固定未评估。
- 4A-4 原 draft 精确绑定文字规格、三批上游 hash 和 24 项 `pending` 决策并保持不可执行；approved artifacts 精确绑定 owner 批准，默认/伪造 registry、语义和权限漂移均失败关闭；
- `FR-GATE-004/005` 覆盖公开预期与市场定价区间、基础/事件 FCF 分离、防重复计价、合成价格、`0.15/2.00/120` 边界、零 downside loss、PIT 和 deterministic replay；
- `FR-EXIT-001` 覆盖六类 evidence exit、risk/time/value 等号边界、unknown/confirmed 优先级、E5/E6 重新承保、无持仓和跨规则/估值 holding 防伪；退出输入自身失败不改写 Gate 结果；
- 4B 原 draft machine proposal 精确绑定完整 inventory 与四批 approved hash，16 项决定全为 `pending`、运行模式为空且保持不变；
- approved 4B artifacts 精确绑定 owner 对 16 项的 scope-limited 批准；五层 capability 任一身份、hash、scope 或权限漂移均失败关闭；
- `Stage4CompleteSyntheticCase` 没有局部结果注入字段；完整编排从原始输入重跑四批，固定单 case/cutoff/公司/节点/事件/主体/经济口径与 E4 时间；
- 完整验收覆盖四门 PASS、`0.10/0.15/2.00/120` 等号边界、各层失败短路、`ABSTAIN/SHADOW_ONLY`、退出隔离、跨批增量利润/FCF 绑定、防伪和 deterministic replay。

这些测试只证明 4A-1—4A-4 和完整 4B 能在各自精确批准的匿名合成 research-validation scope 内执行；不证明历史有效性、正式 KB 策略 smoke、生产运行或任何交易能力已经实现。

## Stage 5A—5D 当前测试边界

[Stage 5A 精确规则包](../03_规则与规格/Stage5_5A成交组合账本与确定性回放精确规则包_v0.1.md)四十项已获 owner 批准。原 draft machine proposal 保持 40 项 `pending`、运行模式为空和零权限；独立 approved bundle、approval record 与治理 verifier 精确固定批准谱系和 `stage5_synthetic_execution_validation` scope。

Stage 5A 治理专项验证：规格/draft/批准文档/approved bundle/approval record 的精确 hash；40 项 ID 顺序与批准状态；Stage 4B 上游 pin；draft 不可签发 capability；错误 scope、批准记录漂移、规则漂移、上游漂移和权限扩张均失败关闭。

Stage 5B 业务专项验证：同一运行 Stage 4 case/result/replay 绑定；历史有效规则与交易日历选择；规则区间重叠和 hash 漂移失败关闭；日期精度与日线 `turnover/volume`；停牌和一字涨停；lot/tick/5% 容量；历史费用和最低佣金；冲击曲线单调性、插值和禁止外推；当前 synthetic executable price 的 Gate 3/4 重算；三日入场到期；确定性 full/partial fill、余量取消、事件排序和 replay。Stage 5A/5B 当时专项为 `19 passed`，全仓为 `841 passed, 4 skipped`。

Stage 5C 业务专项验证：typed recovery record 与多风险簇；NORMAL/DEFENSIVE/CRISIS、8/12/15/20% 回撤及单票/簇/组合等号边界；quantity/notional/planned-loss、现金、worst-cost reserve、容量与可卖量的提交前只减不增约束；缩量后首个可成交候选重算与精确绑定；五层数量和未提交/取消语义；批准/候选/fill/recovery 的 PIT 上界、sizing source 漂移全链传播、未绑定 settlement exception 失败关闭，以及未来事件不进入当前状态；append-only 双分录、事件 schema、账户/策略隔离、FIFO、负现金/超卖、revision chain、幂等/conflict 与 deterministic partial replay。Stage 5A—5C 专项为 `93 passed`，全仓为 `915 passed, 4 skipped`。

所有 backtest/paper/shadow/live/真实账户/仓位/订单/券商/KB 写权限保持 false。Stage 5D 当前验收范围限定为第一条预注册订单/合同历史 replay：固定 case/horizon、五事件 inventory 和支持矩阵，准确覆盖同次 Stage 5C 重算、source-driven ledger、结算/可用性、mark/NAV、十八格 P&L 与 complete/audit replay。未支持事件必须保留为 `BLOCKED/ABSTAIN`，不能静默剔除、近似入账或发布 partial NAV/P&L；全量证券会计边角和 SQLite durable persistence 不属于本受限 5D-1 完成门。

Stage 5D 治理测试继续固定原文与 draft machine proposal 的 SHA-256、48 项完整正文 hash、精确 Stage 5A/5C 上游、零 draft 权限、Ledger V2 exact event map、状态独立 PIT、十八格 P&L、`(beginning_at,ending_at]` 和 SQLite v4 原子聚合语义；这证明治理上限，不等于当前实现覆盖全部 48 项。受限 5D-1 的[业务验收](../../docs/validation/stage5d-first-order-contract-replay-acceptance.md)另以预注册 golden 证明：同一输入逐字节确定，opening 在期初重物化，NAV/P&L 所有金额可追溯，禁止格保持零，未支持事件 fail closed，audit replay 零权限且无 selection-by-outcome。新 bounded replay 专项为 `9 passed`，Stage 5D 相邻套件为 `41 passed`，全仓为 `964 passed, 4 skipped`。

[首条回放预注册](../../docs/validation/stage5d-first-order-contract-replay-preregistration.md)现已把匿名合成 ENTER/BUY case、时间范围、五事件 closed world、期末 mark `8`、NAV `99986.77` 和 P&L `-13.23` 固定为 machine-readable fixture；四项预注册合同测试与九项已有 source-driven Ledger 测试合跑为 `13 passed`，全部 Stage 5D 相邻测试为 `32 passed`，全仓为 `955 passed, 4 skipped`。这只证明实施输入已冻结，不代表 mark/NAV/P&L 或 complete replay 已实现。

正式结果见[Stage 5A 规则治理批准验收记录](../../docs/validation/stage5-5a-governance-acceptance.md)、[Stage 5B 历史市场规则与合成成交验收记录](../../docs/validation/stage5-5b-market-execution-acceptance.md)和[Stage 5C 合成组合与内存账本验收记录](../../docs/validation/stage5-5c-portfolio-ledger-acceptance.md)。
