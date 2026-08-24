# Stage 6 KB 历史公共数据 Handoff 验收 Runbook v0.1

状态：`prepared_for_future_handoff / no_kb_data_consumed`

形成日期：`2026-08-24`

形成基线：`8146c1ec076cbc76914692bd9320a7f466adca2c`

## 1. 目的和边界

本 runbook 规定 InvestSystem 收到 KB 2019—2025 历史公共数据 handoff 后的只读验收顺序、失败条件和输出。它不假设 KB 尚未发布的新 Schema，不读取 KB 内部目录，不创建策略候选、coverage、收益或历史 run。

本轮适用范围只包含 `2019-01-01 <= decision/data date <= 2025-12-31`。2026 是冻结 holdout；验收输入不得包含或泄露 2026 record、count、summary、Schema-derived cardinality、文件大小分布或表现代理。

固定 transport 基线：

- KB transport source commit：`aab36fe229104779b50ec71e2dc37a9fad81d285`
- IS snapshot lock：`02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169`

只有真实只读 HTTPS Published Release 或授权 immutable export package 可以成为证据。KB SQLite、`raw/`、`staging/`、`published/` 工作树、内部 Python 包、tmp 目录、mock 或 TestClient 均不接受。

## 2. Handoff 前置材料

开始验收前必须由 owner 显式提供：

1. machine-readable handoff JSON 的绝对路径和 raw SHA-256；
2. producer validation report 的绝对路径和 raw SHA-256；
3. 人读 census/report；
4. 精确 Release/Manifest/artifact/Schema identity 清单；
5. transport source commit 与 snapshot lock；
6. 若使用 HTTPS，进程内读取的短期只读 env 文件路径、scope 和 expiry；
7. producer 声明的 2019—2025 数据域、时间范围、grain、keys、PIT 与修订 lineage；
8. 明确的 missing/unrecoverable/unsupported 域。

在 KB 尚未冻结新 handoff Schema 前，IS 不发明字段、默认值或 parser。新 Schema 到达后必须先形成版本化 provider adapter/contract snapshot，再执行制品下载。

## 3. 验收顺序

### Gate A：交付身份与安全边界

- 重算 handoff、producer report 和公开 Schema 的 raw SHA-256；
- 校验 transport commit/snapshot lock；
- 禁止 `latest`、相对路径、KB 内部路径或 sibling import；
- Token 只能在进程内读取，不打印、不复制、不提交、不持久化；
- Token scope 必须是完成验收所需的最小只读集合；
- handoff 不得携带 2026 holdout 内容或代理。

Gate A 失败时网络请求、candidate projector 和任何运行调用均为零。

### Gate B：Published Release 与 artifact 闭包

逐个 Release 获取并验证：

- Release、Manifest、Status 必须来自真实 HTTPS 或不可变 export；
- 当前状态必须为 `published`；
- Release/Manifest/Status identity 与 hash chain 闭合；
- artifact ID、item type、SHA-256、size、Content-Type、Content-Length、ETag 和强制响应头一致；
- Schema/version 必须在 IS 明确支持集合内；
- source Release、Schema artifact 和完整依赖闭包均可取得；
- unknown field 不得静默忽略。

任一 artifact 失败时整个 handoff 不进入数据质量计算。

### Gate C：数据域、grain 与引用完整性

至少逐域验证：

1. Document/Span/Fact/CandidateEvent/EvidenceLink/EvidenceRef；
2. Company/Security 历史映射、上市、退市、ST/*ST；
3. 交易日历与历史 MarketRuleSet；
4. 停牌、复牌、涨跌停及 SecuritySessionState；
5. 未复权 daily mark/market data；
6. 现金分红、送股、拆并股、配股、退市/现金退出；
7. PIT 一级行业、流通市值；
8. 20-session ADV 所需源字段；
9. 120-session Beta 所需源字段或通用 Beta artifact；
10. revision/correction/withdrawal/supersedes lineage；
11. delisted、failed、missing 和不可恢复记录。

每个 artifact 保存 grain、candidate/business keys、date range、record count、required-null 情况、duplicate keys、orphan refs、PIT 字段和 revision policy。只有制品实际提供的 profile 才能报告数量或比例；未知值保持 `null`，不得写成零。

### Gate D：PIT、修订与时间顺序

至少验证：

- `economic_at/observed_at <= available_at <= knowledge_cutoff`；
- decision-time 投影不得读取后续 revision；
- correction/withdrawal/supersedes 保留历史可见版本；
- mark 的 session/observed/available 顺序合法；
- calendar、MarketRuleSet、SecuritySessionState 与 mark 可按 PIT join；
- 公司行动 recognition/payment/delivery/sellable 时点分离；
- delisted、failed、suspended 和 missing 不得被静默删除。

PIT 或 lineage 不能证明时只能 `PARTIALLY_READY` 或 `BLOCKED`，不得以当前最新值回填。

### Gate E：Holdout 与 outcome-blind 边界

Handoff 和数据 profile 禁止包含：

- 2026 holdout record/count/summary；
- future return、NAV、P&L、winner/loser、label；
- 实际退出类型/价格、completed-trade flag；
- champion、p-value、Holm 或策略状态；
- 为提高 coverage 而删除的 REJECT/ABSTAIN/BLOCKED/no-fill/delisted 样本。

Gate E 失败时整份交付 `BLOCKED`，不能通过字段丢弃后继续。

## 4. 结果状态

验收结果 closed world：

- `HANDOFF_ACCEPTED_FOR_IS_CENSUS`：公共交付与 PIT 数据质量足以进入 IS outcome-blind candidate/readiness census；不授权历史运行。
- `PARTIALLY_READY`：部分数据域可用，但存在明确缺口；保存逐域 blocker，不生成策略 coverage。
- `BLOCKED`：身份、安全、holdout、PIT、引用或发布状态 P0 失败；任何 downstream projector 调用为零。

即使为 `HANDOFF_ACCEPTED_FOR_IS_CENSUS`，也只允许下一步生成 IS 自有 `HistoricalDataReadinessReport` 和冻结候选全集。不得签发正式 Stage 6C、6D、backtest、paper、shadow、live、仓位或订单权限。

## 5. Failure reason closed world

- `HANDOFF_IDENTITY_MISMATCH`
- `PRODUCER_VALIDATION_MISMATCH`
- `TRANSPORT_LOCK_MISMATCH`
- `TOKEN_SCOPE_EXCESS`
- `KB_INTERNAL_PATH_DEPENDENCY`
- `HOLDOUT_BOUNDARY_VIOLATION`
- `RELEASE_NOT_PUBLISHED`
- `MANIFEST_OR_STATUS_CHAIN_INVALID`
- `ARTIFACT_IDENTITY_OR_HEADER_MISMATCH`
- `SCHEMA_UNSUPPORTED_OR_UNKNOWN_FIELD`
- `DATE_RANGE_INCOMPLETE`
- `GRAIN_OR_KEY_UNPROVEN`
- `REQUIRED_FIELD_PROFILE_MISSING`
- `REFERENCE_CLOSURE_BROKEN`
- `PIT_FIELDS_MISSING`
- `PIT_ORDER_INVALID`
- `REVISION_LINEAGE_MISSING`
- `SURVIVOR_ONLY_OR_DELISTED_MISSING`
- `CALENDAR_RULE_STATE_JOIN_INCOMPLETE`
- `MARK_COVERAGE_OR_TIME_INVALID`
- `CORPORATE_ACTION_TIME_OR_LINEAGE_INVALID`
- `PEER_REFERENCE_FEATURE_INPUT_MISSING`
- `OUTCOME_FIELD_PRESENT`
- `UNRECOVERABLE_GAP_NOT_DECLARED`

未知失败不能映射为 success；应升级 runbook/contract 版本后重新验收。

## 6. IS 输出与职责

IS 验收完成后保存：

- handoff/producer report/Schema raw hashes；
- Release/Manifest/Status/artifact transport observations；
- provider-neutral artifact profile；
- 引用/PIT/lineage 质量结果；
- accepted/missing/blocker domain matrix；
- runbook version、代码提交、配置 hash 和 injected clock；
- `HANDOFF_ACCEPTED_FOR_IS_CENSUS | PARTIALLY_READY | BLOCKED`；
- Token 撤销通知。

KB 不生成策略候选或 support flag。只有 IS 在交付通过后，才以 `economic_event × listed_company × decision_time` 形成候选全集，并在读取任何 outcome 前绑定 Stage 5D support profile。

## 7. 当前明确未做

本 runbook 没有消费任何 KB handoff、Token、Release 或 artifact；没有网络 I/O、parser、candidate inventory、coverage 或 historical evaluator。文件存在不代表 KB 历史数据已 ready，也不改变 Stage 6 正式 `NO_GO` 结论。
