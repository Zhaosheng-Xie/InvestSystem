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

## Stage 6B 准入与原子留存草案

[Stage 6 / 6B 历史准入、状态确认与原子留存精确规则包](../03_规则与规格/Stage6_6B历史准入状态确认与原子留存精确规则包_v0.1.md)及 machine draft 已形成，32 项仍全部 `pending`。治理测试只验证规则身份、零权限、authority profile、闭包、confirmation、seal、原子事务、撤回/audit 与 failure matrix 的机器表达；没有实际网络、状态写入、confirmation 签发、seal 或 evaluator。[6B 草案验收记录](../../docs/validation/stage6b-historical-admission-draft-acceptance.md)固定专项 `8 passed`、Stage 6 相邻 `46 passed`、全仓 `986 passed, 4 skipped` 及完整静态质量门。

`TRADE_READY`、`SHADOW_ONLY`、`REJECT`、`ABSTAIN` 和 `BLOCKED` 案例必须共同入库；`BLOCKED` 使用独立失败 fixture，任何 `TRADE_READY` 合成正例必须先有对应 `approved` 规则，且不代表 paper/live 授权。

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
