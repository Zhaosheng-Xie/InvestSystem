# 实现

需求与边界已于 Stage 0 冻结；Stage 1 的工程与机器契约骨架、Stage 2A 的离线 Release 消费与准入内核，以及 Stage 2B 的最小合成策略纵向切片均已通过根级正式验收。owner 于 `2026-08-08` 恢复 Stage 3：3A 已完成 HTTP Client、immutable export 和官方 fixture 离线验收；3B 已重固定 KB `aab36fe` 公共传输契约，并通过独立 KB RC 进程与只读凭据的本机 HTTP 兼容验收，但尚无真实 run authority。Stage 4 的 4A-1 已实现上下文、历史语义、产业卡点与受益公司映射；4A-2 已实现事件状态、E4、主体/PIT 与审计分层；4A-3 已实现 Gate 1—2、利润分母和四情景；4A-4 已实现 Gate 3—4、估值和退出；4B 已实现从四批原始输入重新计算的完整合成编排。Stage 4 批准自身不授权 backtest、paper、shadow、live、仓位、组合、成交、P&L 或订单；Stage 5 只在下述精确匿名合成范围内扩展验证能力。

Stage 5A 的[精确规则包](../03_规则与规格/Stage5_5A成交组合账本与确定性回放精确规则包_v0.1.md)四十项已全部批准，原 draft 保持不变，另建 approved bundle、approval record 和 `stage5_governance.py` 精确 capability verifier。Stage 5B 已在 `stage5_market_execution.py` 实现历史有效 `MarketRuleSet`、交易日历、证券会话状态、首次可成交、日线 VWAP、lot/tick/5% 容量、历史成本、单调冲击、当前价 Gate 3/4 重算、三日入场到期、`DAY` synthetic intent/fill/cancel 和 deterministic replay；正式证据见[Stage 5B 验收记录](../../docs/validation/stage5-5b-market-execution-acceptance.md)。

Stage 5C 已新增 `stage5_execution_contracts.py`、`stage5_portfolio_risk.py`、`stage5_portfolio_ledger_engine.py`、`stage5_fill_projection.py`、`stage5_ledger.py` 与固定 Decimal context。它使用 candidate → reduction-only constraint → finalize 两阶段接缝，在首次可成交窗口按组合批准、风险、现金、成本准备金、容量与可卖量只减不增地重算数量；分离 target/approved/submitted/filled/actual，并以截至 injected clock 的内存 append-only 双分录/FIFO journal 投影结算与证券可用状态。正式证据见[Stage 5C 验收记录](../../docs/validation/stage5-5c-portfolio-ledger-acceptance.md)。非空公司行动、marks、NAV/P&L、外部现金流、SQLite 表/migration、durable atomic persistence 和完整 Stage 5 replay 仍属于 5D，不能由预留 enum、scheduled future event 或 partial replay 冒充。

Stage 5D 当前处于精确规则治理，只有[48 项待批准草案](../03_规则与规格/Stage5_5D公司行动估值P&L完整回放与原子持久化精确规则包_v0.1.md)和零权限 machine proposal。拟议顺序为 `5D-1` 纯函数 Ledger V2/公司行动/mark/NAV/二维 P&L/complete replay，验收后再做 `5D-2` SQLite v4 原子持久化。批准前不得新增 5D evaluator、数据库表或 migration，也不得改变 Stage 5C 的 scope-limited 契约。

Stage 2B 的实际交付、验证锚点和未授权范围见根级 [Stage 2B 正式验收记录](../../docs/validation/stage2b-acceptance.md)。

Stage 3A 的固定字节、Client/export 能力、失败语义和后续联调门见根级 [Stage 3A 离线传输消费者验收](../../docs/validation/stage3a-acceptance.md)。合成 transport fixture 固定 `authority_eligible=false`，不能为新 run 提供当前状态权威。

Stage 3B 的精确重固定、独立进程 HTTP 输出和脱敏验证证据见根级 [Stage 3B 正式跨仓只读 HTTP 验收](../../docs/validation/stage3b-http-acceptance.md)。该验收只关闭本机 RC transport compatibility；不代替 tcloud、Context Pack 策略 smoke、CAS/Observation 持久化或 run-scoped authority。

Stage 4 当前交付见[开发状态](../../docs/validation/stage4-development-status.md)和[4B 验收记录](../../docs/validation/stage4-4b-acceptance.md)：完整 14 项 P0 inventory 均已批准。`stage4_context_industry.py`、`stage4_event_semantics.py`、`stage4_gate_profit_scenarios.py` 与 `stage4_expectation_valuation_exit.py` 分别只接受精确 4A-1/4A-2/4A-3/4A-4 approved capability；`stage4_complete_engine.py` 还要求独立精确 4B capability，并从原始 typed case 固定执行 4A-1 → 4A-2 → 4A-3 → 4A-4 → 退出汇总。调用方不能注入局部结果；跨 case/cutoff/身份/经济口径、真实价格或 KB 内部依赖均在局部计算前失败关闭。完整输出仅为匿名合成 research-validation 结论，正式 `StrategyRunManifest` 和全部真实/交易权限恒为空或 false。

Stage 2B runner 只能从精确 canonical [machine rule bundle](../03_规则与规格/机器制品/industrial_event_minimum_order_contract_slice_v0.1.0.rule-bundle.json) 与对应 [RuleApprovalRecord](../03_规则与规格/机器制品/industrial_event_minimum_order_contract_slice_v0.1.0.approval.json) 获取 capability；Markdown 只供审阅与追踪，运行时不得解析。strategy/bundle/version/hash/scope、SyntheticValidationInput flags、四类输入 hash、fixture registry pin 或 `run_mode=research` 任一不匹配都必须在 evaluator 前失败关闭。`SHADOW_ONLY` 是合成结果标签，不构成 shadow 运行授权。

- 已完成的最小策略轨：`合成策略 fixture → provider-neutral DTO → StrategyRunManifest → E3.5/E4 → 四道门 → 利润桥/预期/估值 → DecisionRecord + replay_hash`；
- 已完成契约轨：`KB 官方 fixture → 离线 validator/projector → ArtifactConsumptionReceipt + Observations + ReleaseRetentionClosure → provider-neutral DTO`；Stage 3A 已完成只读 Client/export 的离线契约能力，Stage 3B 已完成独立进程本机 HTTP 兼容验收；CAS/Observation 持久化、正式 acquisition 和真实 authority 仍未完成；
- 正式传输核验：`精确 market-daily Published Release → Manifest/制品/状态/权限/Receipt 验证`，不生成订单/合同策略结论；
- 汇合：`精确 Context Pack Published Release → 同一策略入口 → 真实只读 smoke（允许 ABSTAIN）`。

完整策略、TargetPortfolio 和 paper 成交回放在后续阶段开发，可与正式 Release E2E 并行；正式历史验证须在两支都完成后开始。

Stage 2A 已从固定 KB 公共契约提交 `58ed9c5cb5302e3e719f1696bed83a03c5d6313b` 按原始字节引入 20 个官方文件，并验收 provider canonical、契约 catalog、消费 Receipt/Observation、官方 reference fixture 验证/窄投影，以及 SQLite v3 的正式持久化、传递 source Release 留存闭包、run-scoped 当前状态确认、receipt-derived atomic pin 和 legacy v2 quarantine。该历史提交没有公共 transport 契约，所以 Stage 2A 无参数能力门继续在 I/O 前失败关闭。Stage 3A 曾以 `2c84277` 扩展快照启用 HTTP/export 协议实现，Stage 3B 已将其重固定到 `aab36fe` 并完成独立本机 HTTP 兼容验收；所有结果仍无 authority，认证 acquisition 持久化、当前状态权威和正式策略 smoke 仍在后续 3C—3D 范围。

根级采用 `src/` 包布局、GitHub Actions 和规范 JSON。本地实现使用工作站级 `E:\Conda\envs\Data_Analysis`（Python 3.12）作为共享开发解释器，但 InvestSystem 必须独立维护 `pyproject.toml`、`requirements-build.in`、带哈希的 runtime/dev lock、TOML 配置、`var/cache/kb-releases/`、`var/state/invest_system.sqlite3` 和运行目录。项目只以 editable `--no-deps --no-build-isolation` 注册；缺包安装前后保存环境基线并运行 `pip check`，不得未经确认改变既有共享包。CI 和可复现验收必须从 InvestSystem lock 创建干净环境。

禁止通过 KB SQLite、`raw/`、`staging/`、兄弟目录 `PYTHONPATH`、KB editable 包、submodule、符号链接或内部 Python import 获取输入；禁止共享 KB 数据库、缓存、迁移和部署 volume。

KB Adapter 只面向已发布公共契约并使用只读权限。版本化 HTTP API 与不可变导出包是两个传输入口，但必须汇入相同的 Release validator、确定性 receipt 和 provider-neutral DTO。首版每个 run 只接受一个 `strategy_input_ref`。Manifest、制品哈希、Schema、撤回状态或知识截止时间任一不合格时，新 run 必须失败关闭为 `BLOCKED`。正式运行禁止解析 `latest`。

Release 撤回后保留固定历史材料，只允许走独立的 `audit_replay` 路径；该路径不得创建新的当前 DecisionRecord、仓位、批准或订单。SQLite 只保存 InvestSystem 消费、运行和审计索引，不保存 KB 内部事实表。

Stage 1 已实现的根级工程能力包括：

- `Clock`、`SystemClock` 与 `FixedClock`，所有运行时间必须显式读取并校验为 UTC；
- provider-neutral draft DTO、规范 JSON、SHA-256 和固定 Manifest golden；
- SQLite `user_version=1` 的本项目状态层，以及 SHA-256 内容寻址缓存；
- 原子缓存写入、读回重验、幂等 artifact 映射、20 GiB 软阈值报告和零自动删除；
- 原子核对最新 provider 状态与本地准入后，按 run 固定精确 artifact 子集；撤回后阻止普通读取和新 pin，只允许通过独立 `AuditReplayRequest` 读取既有 pin 的审计上下文；
- pytest、Ruff、mypy、双平台 GitHub Actions 和跨仓隔离测试。

Stage 2A 本轮在该骨架上新增：

- `ReleaseRetentionClosure` 机器契约，显式保存根 Release 到 source Release 的传递依赖，不从 fixture 中“出现过的全部 Release”猜测闭包；
- 完整 sealed Manifest 文档快照、物理文档哈希/大小与 provider 的 self-excluding `manifest_hash` 分开保存，并共同进入闭包身份；
- 三类 Observation 的完整 canonical bytes、从 sequence 1 开始的连续 provider status previous-hash 链、线性 `supersedes` 与不可回拨当前 head；
- `pin_run(manifest, confirmation)` 只从持久 Receipt/闭包推导 root、source Manifest 和制品 pin，并要求受信、未过期、run-scoped 的确认精确覆盖全部闭包 Release；默认 authority 集合为空，所以未固定真实传输契约时所有新 run 失败关闭；
- Receipt/closure canonical aggregate、关系索引、CAS 字节与 `persisted_at <= run.created_at <= pin clock` 在 pin/read 时重核；撤回或无法确认后阻止新 pin 和普通读取，既有完整闭包只供显式 `audit_replay`。
- 非空 SQLite v2 无损迁移时为全部旧 pin 写入不可变 quarantine；直接注入 confirmation/binding 也不能把旧 run 恢复为普通运行。

缓存和状态层的行为边界见根级 [存储与 Release 缓存说明](../../docs/storage-and-cache.md)。这些能力仍不包含 HTTP/export transport、真实 Release 当前状态获取或任何策略规则语义。

策略内核只依赖 provider-neutral DTO。E0—E7、四道门、利润桥、预期、估值、Decision、组合、执行和 P&L 全部属于 InvestSystem，不能回写 KB。

研究、风险和执行必须分层；任何研究 Agent 都不得访问交易凭证或直接提交订单。

Stage 2B 已用 InvestSystem 自有、明确标记的合成策略 fixture 打通最小链路；真实 KB Context Pack 仍只做后续只读 smoke/E2E，允许正确结果为 `ABSTAIN`，不得要求 KB 为正例定制事实。当前 runner 只返回不可变审计对象，不写 SQLite；durable persistence 需在后续以独立契约和失败语义批准。

