# 数据

本目录只承接 InvestSystem 消费侧的数据契约、验证规则、策略投影和运行快照说明，不承担信息采集或基础事实生产。

`InvestmentResearchKB` 独立负责采集、`raw`、`staging`、PIT、Document、Evidence、Fact、CandidateEvent、审核、Context Pack、Published Release、Release Manifest 和修订血缘。InvestSystem 只能通过正式发布面按精确 `dataset_release_id` 只读消费，不得读取 KB SQLite、内部目录、缓存或 Python 实现，也不得向 KB 写入策略结果。

首版每次正式运行必须且只能保存一个完整五字段 `strategy_input_ref`；多 Release 聚合需要新的 ADR 和契约版本：

~~~text
schema_version
dataset_release_id
knowledge_cutoff
release_manifest_schema_version
manifest_hash = {algorithm: "sha256", value: "<64 lowercase hex>"}
~~~

`dataset_release_id` 禁止使用 `latest`，`manifest_hash` 是对象而不是裸字符串。正式输入可以来自版本化只读 HTTP API 或授权的不可变导出包；二者必须经过相同的 Release 身份、Manifest Schema/语义哈希、精确制品哈希和当前状态校验，再把已验证字节存入 `var/cache/kb-releases/` 内容寻址缓存。

缓存软上限为 `20 GiB`。达到或越过上限时报告超限并进入容量复核，不得自动删除被历史 receipt、Manifest、run 或审计记录引用的制品；未引用内容的 GC 宽限期与操作流程尚待规格化，在此之前不自动清理。InvestSystem 自有 `var/state/invest_system.sqlite3` 只保存消费索引、Observation、run/decision 和审计元数据，不复制 KB 数据库、表结构或事实权威。

`ArtifactConsumptionReceipt` 是确定性内容回执：固定 consumer contract 版本、五字段输入引用，以及按 `artifact_id` 排序的 `{artifact_id, item_type, artifact_hash, size_bytes, record_count}`，并计算规范 `receipt_hash`。获取时间、端点、HTTP response 或 sealed export 的可选物理字节哈希、当前 Release 状态及授权结果另存为 append-only `ArtifactFetchObservation` / `ReleaseStatusObservation`，不得进入 receipt identity。HTTP API envelope 不得冒充 sealed `manifest.json` 原始字节，任何物理传输哈希也不得冒充语义 `manifest_hash`。失败或撤回时新运行必须 `BLOCKED`；历史材料保留且只允许明确标记的 `audit_replay`，不得形成新的当前决策、仓位或订单；不得为继续运行而回退到 KB 内部数据。

第一批需要定义的对象：

- `StrategyInputRef`（严格服从 KB 公共 Schema）
- `ArtifactConsumptionReceipt`
- `ArtifactFetchObservation / ReleaseStatusObservation`
- `StrategyRunManifest`
- provider-neutral `IndustryContextView / StrategyFactProjection`
- `StrategyEvent / GateResult / ProfitBridge / ScenarioValuation`
- `DecisionRecord / TargetPortfolio / ApprovalRecord`
- `SecurityStatus / MarketRule / FeeSchedule`
- `ExecutionReplay / PositionLedger / P&L`

KB 对象在本项目中只保存发布 ID、字段投影和引用，不重新定义权威事实。策略判断和运行结果通过新 run 或 `supersedes` 留痕，不覆盖历史输入与旧判断。

测试数据必须区分 KB 公共契约 fixture、InvestSystem 自有合成策略 fixture 和失败注入 fixture；任何合成数据都不得冒充 KB 正式 Release。

