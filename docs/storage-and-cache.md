# InvestSystem 状态库与 Release 缓存

本文说明 Stage 1 已实现的本项目状态与缓存边界。它不是 KB Adapter、KB Schema 副本、正式 `ArtifactConsumptionReceipt` 或策略运行器。

## 所有权与路径

- SQLite 默认位于 `var/state/invest_system.sqlite3`，只保存 InvestSystem 自有的状态/准入观察、缓存对象、artifact 映射、run pin 和审计元数据。
- 内容寻址缓存默认位于 `var/cache/kb-releases/sha256/<前两位>/<完整摘要>`。
- 两者均由 InvestSystem 独立持有；实现不读取 KB SQLite、`raw/`、`staging/`、`published/`、工作树或 Python 包。

SQLite 使用 `PRAGMA user_version=1`。初始化在 `BEGIN IMMEDIATE` 内串行完成；未知版本、未版本化的非空数据库、未知表/索引/view/trigger、列/主键/唯一约束/外键/检查约束不一致、`quick_check` 或 `foreign_key_check` 失败都会拒绝打开，不自动猜测或收养外部表结构。

## 状态与准入

提供方生命周期与 InvestSystem 本地准入分成两个不可混用的轴：

- provider status 只表示 `published` 或终态 `withdrawn`；每次观察绑定完整五字段 `StrategyInputRef`，同一 `dataset_release_id` 的身份不得漂移。
- local admission 表示 `authorized`、`unconfirmed` 或 `denied`，并且只能引用该 Release 最新的 provider status observation。
- 新的 provider observation 会令此前 admission 失效；旧的 `published` 或 `authorized` 观察不能被复用来绕过更新的状态。
- `withdrawn` 不可逆；状态无法确认或授权失败时也不能准入新 run。

`StrategyRunManifest` 同时固定 `release_status_observation_id` 和 `release_admission_observation_id`。`pin_run()` 在同一个 `BEGIN IMMEDIATE` 事务内重核最新 provider 状态、完整输入身份和本地授权，避免“先检查、后撤回、再落 run”的竞态。

## 写入、pin 与完整性

`ReleaseCacheStore` 只接收调用方已经取得的 `bytes`、精确 `release_id`、`artifact_id` 和预期 SHA-256：

1. 写入前验证摘要格式和实际字节哈希。
2. 使用同目录临时文件、`flush`、`fsync` 与 `os.replace` 原子落盘。
3. 写入、重复写、读取和 pin 时都重新验证大小与 SHA-256。
4. 同一 `release_id + artifact_id` 不得重映射到其他字节；相同内容重试保持幂等。
5. 符号链接、junction 或多硬链接对象不被当作本项目独占缓存收养。
6. 每个 run 只 pin 调用方明确声明、按 `artifact_id` 规范排序的精确制品子集；保存原 Manifest canonical bytes、SHA-256、canonical profile 版本和每个制品的 SHA-256/大小。

一个 run 的 pin 不冻结整个 Release。后续 run 可以在同一 Release 中消费另一精确子集；旧 run 的审计读取仍只能看到它自己的固定快照。Stage 1 尚不生成正式 receipt，因此本阶段由调用方声明 `artifact_ids`；Stage 2A 必须把该集合与已验证的 `ArtifactConsumptionReceipt` 逐项核对后才能准入。

文件成功落盘而 SQLite 事务未完成时可能留下未登记的内容寻址孤立文件。后续收养仍须重新验证；软容量阈值既不是准入上限，也不是跳过完整性检查的理由。

## 容量与留存

- 默认运营软阈值为 `20 GiB`，由 `DEFAULT_CACHE_SOFT_LIMIT_BYTES` 与 TOML 配置共同表达。
- `quota_report()` 报告实际物理缓存、已登记对象、未登记孤立文件和被历史 pin 覆盖的唯一字节。
- 报告会显式列出 missing、corrupt、metadata、scan failure 异常，并标明扫描是否完整；快速容量盘点可以不重哈希内容，但不能静默隐藏缺失或扫描失败。
- 超过软阈值时只通过 `over_limit` 告警并进入人工容量复核，不硬拒绝写入，也不授权删除；实际磁盘写满仍会使事务失败并回滚元数据。
- Stage 1 不提供自动 GC 或删除 API。未来若设计未引用对象 GC，必须另立规格，并且任何历史 pin 引用的制品都不得自动删除。

## 普通读取与审计重放

- 普通读取必须来自已经原子准入并 pin 的 source run，并使用 `RunPurpose.NEW_RUN`；每次读取仍要求当前 provider/admission 与该 pin 一致且保持授权。
- 撤回、状态无法确认、授权失效或观察被替换后，普通读取失败关闭。
- 审计使用独立 `AuditReplayRequest`，以 `source_run_id + source_manifest_hash` 绑定原 Manifest；原 Manifest 的普通 `run_mode`、canonical bytes 和哈希不会为重放而改写。
- 审计只能读取 source run 的精确 pin 集。返回的 `ArtifactRead` 明示 `purpose=audit_replay`、原 run/Manifest/观察身份以及当前 provider/admission 状态，因此撤回不会被缓存伪装成新的 Published Release。
- 审计读取仍重验路径、大小和哈希。该只读能力不提供创建新 pin、当前 DecisionRecord、目标仓位、批准或订单的接口。

## 阶段边界

Stage 1 只证明 provider-neutral 本地状态、准入和缓存骨架。以下内容留在后续阶段：

- Stage 2A：只读 HTTP/export Adapter、KB 官方契约固定、正式 Receipt 与公共 Observation 映射；
- Stage 2B：获批的最小策略规则和合成纵向切片；
- Stage 3：正式 Published Release 传输与策略 smoke。
