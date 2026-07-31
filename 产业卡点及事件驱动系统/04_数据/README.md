# 数据

本目录只承接 InvestSystem 消费侧的数据契约、验证规则、策略投影和运行快照说明，不承担信息采集或基础事实生产。

`InvestmentResearchKB` 独立负责采集、`raw`、`staging`、PIT、Document、Evidence、Fact、CandidateEvent、审核、Context Pack、Published Release、Release Manifest 和修订血缘。InvestSystem 只能通过正式发布面按精确 `dataset_release_id` 只读消费，不得读取 KB SQLite、内部目录、缓存或 Python 实现，也不得向 KB 写入策略结果。

每次正式运行必须保存完整五字段 `strategy_input_ref`：

~~~text
schema_version
dataset_release_id
knowledge_cutoff
release_manifest_schema_version
manifest_hash = {algorithm: "sha256", value: "<64 lowercase hex>"}
~~~

`dataset_release_id` 禁止使用 `latest`，`manifest_hash` 是对象而不是裸字符串。消费者按 KB 公共契约验证 Manifest Schema，并对排除 `manifest_hash` 字段自身后的规范化 Manifest 重算语义哈希；随后校验精确制品、Schema、制品哈希和 Release 当前状态，再把已验证字节存入 InvestSystem 自有内容寻址缓存。

`ArtifactConsumptionReceipt` 是确定性内容回执：固定 consumer contract 版本、五字段输入引用，以及按 `artifact_id` 排序的 `{artifact_id, item_type, artifact_hash, size_bytes, record_count}`，并计算规范 `receipt_hash`。获取时间、端点、HTTP response 或 sealed export 的可选物理字节哈希、当前 Release 状态及授权结果另存为 append-only `ArtifactFetchObservation` / `ReleaseStatusObservation`，不得进入 receipt identity。HTTP API envelope 不得冒充 sealed `manifest.json` 原始字节，任何物理传输哈希也不得冒充语义 `manifest_hash`。失败时新运行必须 `BLOCKED`；不得为继续运行而回退到 KB 内部数据。

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

