# InvestSystem SQLite v3 与 Release 缓存

本文记录 Stage 2A 已实现的本地存储纵向切片：正式 `ArtifactConsumptionReceipt`、三类消费观察、Release 留存闭包、run-scoped 当前状态确认、由 Receipt 派生的原子 run pin，以及内容寻址缓存的读取和容量报告。这些是 InvestSystem 自有能力，不是 KB 的存储副本。

当前仍未实现 KB 只读 HTTP API 适配器、不可变导出包适配器和真实 provider current status 的获取或订阅。`ReleaseCacheStore` 只接收由边界 Adapter 已验证的 InvestSystem 中立合同和精确字节；本地 current head 只表示已持久化的最新观察，不应冒充 KB 的实时状态。E0—E7、四道门、利润桥、估值、分析结论和决策仍属后续策略实现。

## 所有权与路径

- SQLite 默认位于 `var/state/invest_system.sqlite3`，使用 `PRAGMA user_version=3`。
- 内容寻址缓存默认位于 `var/cache/kb-releases/sha256/<前两位>/<完整 SHA-256>`，Release Manifest 和 artifact 使用同一 CAS。
- 数据库、缓存和运行配置均由 InvestSystem 独立持有。实现不读取 KB SQLite、`raw/`、`staging/`、`published/`、工作树或 Python 包，也不将策略状态写回 KB。

## 身份、Receipt 与留存闭包

### 完整五字段引用

每个根 Release 和 source Release 都保存完整 `StrategyInputRef`，五个字段不得漂移：

1. `schema_version`；
2. `dataset_release_id`；
3. `knowledge_cutoff`；
4. `release_manifest_schema_version`；
5. `manifest_hash`。

同一 `dataset_release_id` 若尝试重映射到不同的任一字段，存储层都会失败关闭。首版 `StrategyRunManifest` 仍严格限定一个 `strategy_input_ref`。

`manifest_hash` 是提供方 Manifest 合同的语义哈希，由 Adapter 按对应规范验证。每个闭包节点另以 `manifest_document_hash + manifest_size_bytes` 承诺完整 Manifest 文档的物理身份；SQLite 在首次写入前逐字节核对，并将物理摘要保存到 CAS 和 run pin。两条哈希轴不得假定相等。KB reference Adapter 使用 `irkb-jsonl-v1` 的 sealed Manifest 表示（规范 JSON 后恰好一个 LF），确保 HTTP/export 对同一规范文档得到相同物理身份。同理，Receipt 和闭包的合同身份哈希，与 SQLite 中保存的完整 canonical document hash 也是明确分离的校验轴。

### 根 Receipt 与传递 source 闭包

- `ArtifactConsumptionReceipt` 只描述本次策略直接消费的根 Release 及其精确 artifact 集；不把 source Release artifact 冒充为根消费项。
- `ReleaseRetentionClosure` 从该根 Release 出发，记录所有可达的传递 source Release、每个节点的完整五字段引用、Manifest 完整文档摘要/大小、精确 artifact 描述和直接依赖边。
- 闭包模型强制节点和 artifact 唯一且规范排序、依赖端点存在、无环、全部节点从根可达，且 source `knowledge_cutoff` 不得晚于其父 Release。
- Receipt artifact 集必须与闭包根节点完全相等；artifact 字节和 Manifest 字节则必须精确覆盖闭包每个成员，不得缺失或多交。
- Receipt 到 closure 的对应是不可变映射；同一身份只允许字节完全相同的幂等重试。

v3 的主要表组为：`receipts` / `receipt_artifacts` / `receipt_closures`、`retention_closures` / `closure_releases` / `closure_dependencies` / `closure_artifacts`、`release_manifests` / `release_artifacts`、三类 observation 表及 `release_heads`、`run_release_status_confirmations` / `run_release_status_confirmation_items` / `strategy_run_confirmation_bindings`、`legacy_v2_quarantined_run_pins`，以及 `strategy_run_pins` / `pin_releases` / `pin_artifacts`。`pin_artifacts` 使用 `run_id + release_id + artifact_id` 三元主键，因而不会把不同 source Release 中同名 artifact 混同。

## 持久化与观察链

`record_verified_consumption(receipt, retention_closure, artifact_payloads, manifest_payloads)` 执行精确集合校验，验证 artifact 的字节数和 SHA-256，再持久化 CAS、Receipt、Manifest 快照和留存闭包。文件必须先成功落盘，之后 SQLite 元数据才在 `BEGIN IMMEDIATE` 事务中一次可见。如果元数据事务失败，可能留下未登记的内容寻址孤立文件；它不会暴露部分 Receipt 或闭包，后续收养时仍须重新验证。

`append_observation()` 持久化三条彼此分离的观察链：

- `ArtifactFetchObservation`：记录运输和 Schema 验证结果；`passed` 观察必须绑定已持久化的精确 Receipt 和完全相同的 artifact ID 集。
- `ReleaseStatusObservation`：记录已验证的 provider status event 或失败关闭结果；支持 `building`、`validated`、`published` 和终态 `withdrawn`。
- `ReleaseAdmissionObservation`：记录 InvestSystem 本地 `authorized`、`unconfirmed` 或 `denied`，只能指向该 Release 精确的 current status observation；只有已验证的 `published` 可被授权。

每个 Release 的每类观察只有一条线性 current head。新观察的 `supersedes` 必须精确指向当前 head，`observed_at` 不得倒退且不得晚于可信持久化时钟；新 status 不删除 admission head，而是通过其绑定的 status ID 不再等于 current status 使旧授权立即失效，下一条 admission 继续 supersede 旧 head。通过验证的 provider status 必须从 sequence 1 开始形成无缺口 hash chain：新事件的 `status_sequence` 恰好递增 1，`previous_status_event_hash` 等于上一事件 hash，`status_recorded_at` 不倒退。允许用新 Observation 精确重复确认最新同一 provider event，以便从临时 `unconfirmable` 恢复和定期刷新；事件 ID/hash 重映射、较旧事件回放、链跳跃和 `withdrawn` 后的新事件全部失败关闭。provider-owned event/artifact ID 作为最长 256 字符的 opaque ID 保存，允许公共合同中的 `/`，但从不用于拼接缓存路径。

除可变 current-head 投影 `release_heads` 外，v3 表都有禁止 `UPDATE` 和 `DELETE` 的 SQLite trigger，并为全部主键/唯一键增加冲突插入防线，外部连接即使使用默认 `recursive_triggers=OFF` 的 `INSERT OR REPLACE` 也不能替换不可变行。`release_heads` 禁止删除，其每次更新只能推进一个 head，且新 Observation 必须属于同一 Release/类型并精确 supersede 旧 head；pin/read 还会独立确认 head 是唯一链尾。Receipt、closure 与 run confirmation 的 canonical BLOB 是聚合权威，所有 child index 在 fetch、pin 和 read 时都须与其精确一致，不能通过追加自洽子行扩大既有 Receipt、闭包、confirmation 或 run pin。Observation 与 run confirmation 的 canonical BLOB 每次都会按精确字段集、嵌套类型、枚举、规范 UTC、数组规范顺序和模型语义严格反序列化，再逐字节重新规范化并核对 SQLite 投影；数据库直写不能用“投影一致但合同非法”的文档取得授权。

## Run-scoped 当前状态确认

本地 `release_heads` 只表示已经持久化的最新观察，不能证明远端当前仍为 `published`。v3 因此要求每个新 run 额外携带一个确定性的 `RunReleaseStatusConfirmation`：

- confirmation 精确绑定 `run_id`、根 Release、Receipt、闭包和一个已配置的 authority contract；
- items 必须与闭包中的根及全部传递 source Release 完全相等，不得缺少或增加 Release；
- 每个 item 保存完整五字段输入引用、status observation 与 provider event 身份、可信 `provider_snapshot_at`、本机 `checked_at` 和原始响应/导出字节哈希；
- authority policy 固定 contract hash、最大状态年龄和允许时钟偏差；旧不可变导出包不能因今天重新读取而获得新的当前性；
- confirmation 的 canonical parent 与 self-excluding hash 是权威，SQLite child rows 只是精确索引。

`ReleaseCacheStore` 的 authority policy 默认是空集合，所以没有已固定真实传输契约时，任何新 pin 都在 I/O/策略执行前失败关闭。测试只能显式注入标记清楚的 synthetic authority；它不会进入默认配置或 KB 支持矩阵。Stage 3 固定正式 HTTP/export response 契约、完整 status event、可信 provider snapshot 时间和响应字节后，才能登记真实 authority。

authority policy 是受信 InvestSystem 进程在构造存储对象时取得的私有只读配置快照，用来避免调用方经公共接口或共享可变字典改变准入；它不是针对同一 Python 进程内任意恶意代码的权限沙箱。Stage 3 启用真实 authority 时，必须由已认证的只读 transport 构造 confirmation，并把原始响应或导出证据保存在 InvestSystem 自有不可变 CAS 中供哈希重算；不能只信任调用方填写的 `authority_id`、contract hash、confirmation self hash 或 `response_bytes_hash`。

## Receipt 派生的原子 pin

`pin_run(manifest, confirmation)` 不接收调用方声明的 `artifact_ids`。它从 `StrategyRunManifest.artifact_consumption_receipt_hash` 解析已持久化 Receipt，再通过不可变映射得到整个留存闭包。一个 `BEGIN IMMEDIATE` 事务会重核：

1. Manifest 中的完整五字段根引用和 Receipt 身份；
2. current fetch head 是否对该 Receipt 验证通过；
3. confirmation 是否由允许的精确 authority contract 生成、仍在最大年龄/时钟偏差/有效期内，并与 run、Receipt 和闭包完全绑定；
4. confirmation 是否恰好覆盖闭包中每一个根或 source Release，且每个 item 仍对应通过验证的 current `published` provider event；
5. 根 Release 的 current admission 是否仍对相同 provider event `authorized`；
6. Manifest 和 artifact CAS 字节、大小、哈希和映射是否完整；Receipt、闭包、Manifest、artifact、Observation 和 confirmation 的时间因果均成立。

全部条件成立后，才会同时写入 run pin：`pin_releases` 固定每个闭包 Release 的 Manifest 文档 SHA-256 和当时 status observation，`pin_artifacts` 固定所有闭包 artifact 的三元身份、哈希和大小。任一条件失败都不会产生部分 pin。这保证策略运行的历史依赖由已验证 Receipt 和闭包派生，而不是一个可以少报的调用方子集。

## 普通读取与审计重放

- 创建新 run 时，必须有尚未过期、run-scoped、全闭包覆盖且 authority contract 被显式允许的 confirmation；根 fetch/status/admission 必须与 current head 精确相等，闭包每个成员都必须 current passed/published。撤回、无法确认、未发布、本地未授权、观察失效、confirmation 缺失/过期或缓存损坏任一情况都失败关闭。
- `RunPurpose.NEW_RUN` 普通读取只向策略暴露根 Receipt 的 artifact，不直接暴露 source Release artifact。读取时仍要求根 fetch/status/admission 和每个闭包成员的 status observation 与 pin 时快照精确相同；即使新观察仍为 `published`，也不会静默改写旧 run 的证据边界。
- `RunPurpose.AUDIT_REPLAY` 必须提供 `AuditReplayRequest`，并以 `source_run_id + source_manifest_hash` 精确绑定已 pin 的原始 run。审计可读取根或 source Release 的历史 pin artifact，即使当前已撤回也仍可追溯；返回值明确区分目标 Release 的历史 pinned status、根 Release 的历史 admission，以及目标 Release 的 current access，不能用 root 的 `authorized` 隐藏 source 的撤回。每次读取仍重验完整闭包、文件路径、大小和哈希。
- 审计读取不会改写原 `StrategyRunManifest`，也不能被用于创建新的当前决策、仓位、批准或订单。

## 容量与留存

- 默认软阈值为 `20 GiB`。`quota_report()` 按物理 CAS 字节判断 `over_limit`，并分别报告已登记字节、孤立文件字节和被历史 pin 覆盖的唯一 Manifest/artifact 字节。
- 软阈值只产生运营告警，不是硬准入上限，也不授权删除。实际磁盘写满仍会使写入失败。
- v3 不提供自动 GC 或删除 API，历史 run pin 引用的 Manifest 和 artifact 永不自动删除。如果未来增加未引用对象清理，必须另立规格并继续保护全部历史 pin。
- 容量扫描会显式报告 missing、corrupt、metadata 和 scan failure；符号链接、junction 和多硬链接对象不会被当作本项目独占且可信的缓存。

## Schema 升级与失败关闭

新库直接创建 v3。并发首次打开先在一致的只读 snapshot 中预检，再通过有界 SQLITE_BUSY/LOCKED retry 建立 WAL，最后在单个 `BEGIN IMMEDIATE` 中重新识别、建表或迁移并验证完整 Schema；并发构造不会暴露半成品。打开旧 `user_version=1` 库时，只有表、列和显式索引 inventory 与已知 v1 完全相等，且所有 v1 表均为空，才会升级为 v3。已验证的 v2 会在同一事务中只新增 confirmation/binding 表、索引和不可变 trigger 后升为 v3，不重写既有 Receipt、Observation、闭包或 pin。

任何非空 v1 库都缺少正式 Receipt、三类 canonical observation 和真实传递闭包，无法无损推导；因此必须保持原样并失败关闭，不把旧的调用方 artifact 子集伪装成新 Receipt 或闭包。v2 既有 pin 没有 run-scoped confirmation；迁移事务会把每个旧 run 写入不可变 `legacy_v2_quarantined_run_pins`，使其永久只作为历史材料供 `audit_replay`。即使之后有人直接向 SQLite 注入一套 confirmation、items 和 binding，旧 run 仍不能恢复普通读取或重新准入，审计重放也忽略这些后注入绑定。未知版本、未版本化的非空数据库、未知表/索引/view/trigger、v2/v3 定义偏移、`quick_check` 或 `foreign_key_check` 失败也都拒绝打开。

## 未完成的阶段边界

- 生产级 KB HTTP API 传输、鉴权、重试、超时和响应封装验证；
- 生产级不可变导出包发现、解包和完整性验证；
- 从 KB 获取或订阅真实 current status，并将其转换为可持久化 observation；
- 由已认证只读 transport 保留并重核 current-status 原始响应/导出证据，再启用真实 authority；
- 使用正式 KB Published Release 的端到端 smoke；
- 产业事件策略与题材轮动策略的 E0—E7、规则、归因、估值和决策逻辑。

因此，v3 已经提供可审计且默认拒绝真实新 run 的本地“消费—观察—确认—准入—留存”骨架，但不应宣称已能从真实 KB 独立获取 Release，也不应宣称任何策略已实现。
