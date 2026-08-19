# Stage 6 / 6B 历史准入、状态确认与原子留存精确规则包 v0.1

状态：`draft_for_owner_approval`

适用策略：`industrial_bottleneck_event`

拟议批准 scope：`stage6_historical_admission_validation`

本文只冻结 Stage 6B 的输入、状态证据、确认、原子提交和 admission seal 规则。它不签发 capability，不执行正式历史 run，不读取策略表现，不打开 development、walk-forward 或 holdout，不授权 backtest、paper、shadow、live、仓位、订单、券商连接、资金部署或 KB 写入。

## 1. 6B 的唯一目标

Stage 3 已证明真实公网只读传输兼容；Stage 2A 已有 provider-neutral Receipt、Observation、Retention Closure、`RunReleaseStatusConfirmation` draft 与 SQLite v3 pin 骨架；Stage 6A 已批准历史验证必须先过新鲜状态确认和原子留存门。

这些既有制品都不是正式历史准入授权。6B 的目标是形成一个独立、可失败关闭的 `HistoricalRunAdmissionSeal`：只有同一次 admission 中的精确输入、完整 Release 闭包、新鲜状态证据、确认、Manifest、预注册引用和 pin 全部闭合，后续阶段才可能消费该 seal。没有 seal 时 evaluator 调用必须为零。

6B 的批准仅允许实现和验证 admission。正式 historical run 仍须等待 6B 独立验收、完整预注册和 6C 另行授权。

## 2. 阶段与权限边界

| 能力 | 6B draft | 6B 获批后拟议验证能力 | 正式历史运行 |
| --- | --- | --- | --- |
| 形成规则/测试 | 是 | 是 | 否 |
| 真实公网只读状态兼容验证 | 否 | 允许短期只读凭据、隔离验证状态库 | 否 |
| 签发 validation-only confirmation/seal | 否 | 仅临时、隔离、`authority_eligible=false` 验收 | 否 |
| 调用策略 evaluator | 否 | 否 | 6C 另行授权 |
| 打开 holdout | 否 | 否 | 6D 另行授权 |
| backtest/paper/shadow/live | 否 | 否 | 不由 6B 授权 |

Stage 6A governance capability 只能授权形成本草案，不能签发 6B runtime capability。Stage 3 validation-only 对象、Stage 5 capability、Stage 7 current-run authority 均不能替代 6B 独立身份。

## 3. 精确依赖与职责边界

6B machine draft 必须固定：

- Stage 6A approved bundle、approval record 与验收记录；
- KB transport snapshot lock `02e0505f...`，来源提交 `aab36fe229104779b50ec71e2dc37a9fad81d285`；
- InvestSystem 自有 Receipt、Observation、Retention Closure、StrategyRunManifest 和 RunReleaseStatusConfirmation draft Schema；
- SQLite v3 的 receipt-derived full-closure pin、append-only Observation、confirmation binding、quarantine 与 audit-only 语义；
- 实现进入基线提交 `59e1edd80765dbd67635d1497b2fc008d08b21d9`。

依赖只提供可复用技术基础，不自动批准其 draft Schema 或当前实现用于历史准入。任何承重字节、Schema、canonical profile、authority profile 或事务集合变化都必须升级 6B 版本并重新验收。

InvestSystem 只访问 KB 公共只读 HTTPS API 或授权不可变导出包。当前状态 authority 必须来自独立在线 HTTPS 状态获取；导出包只能提供不可变内容，不能单独证明“当前仍 published”。禁止读取 KB SQLite、`raw`、`staging`、`published`、工作树源码或内部包。

## 4. Admission request 与单输入规则

`HistoricalAdmissionRequest` 至少固定：

- `request_id`、`run_id`、`strategy_id`、purpose 与 canonical hash；
- 一个且仅一个五字段 `strategy_input_ref`；
- 已批准 6B rule identity、批准记录和 capability identity；
- 代码提交、runtime lock、semantic config 和注入时钟；
- 已批准的 `HistoricalValidationPreregistration` ID/hash；
- transport snapshot lock、authority profile hash；
- 期望的根 Release ID，不允许 `latest`。

6B 实现验收可以使用专用 validation preregistration fixture，但必须标记 `validation_only=true`、`not_historical_evidence=true`，不得冒充正式预注册。正式预注册缺失或仍含 `OWNER_DECISION_REQUIRED` 时，不得形成正式 admission seal。

## 5. 完整 Release 闭包

根 Receipt 只描述策略入口制品；`ReleaseRetentionClosure` 必须另行固定根 Release 与所有传递 source Release、Manifest、依赖边和实际引用 artifact。闭包必须：

- 根节点与 request 的五字段 `strategy_input_ref` 完全一致；
- 节点按 Release ID 规范排序，禁止缺失、额外、不可达、环或同 ID 异内容；
- 每个 source cutoff 不晚于其父节点和根 run 允许 cutoff；
- 每个 Manifest 和 artifact 的语义/物理哈希、大小、Schema 与缓存字节一致；
- confirmation items、pin releases 和 closure Release 集合完全相等，不能多交或少交；
- 每次读取和 audit replay 重新验证完整闭包与 CAS 字节。

每个 run 对外仍只有一个 `strategy_input_ref`；闭包中的 source Release 不是额外策略输入，不得绕过 ADR-0001 引入多输入。

## 6. 状态 authority profile

首版拟议 profile 固定为：

| 字段 | 值 |
| --- | --- |
| `authority_id` | `kb_public_https_status_v1` |
| endpoint origin | `https://82.157.112.120` |
| status path | `/api/v1/dataset-releases/{release_id}/status` |
| transport snapshot | `02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169` |
| provider snapshot 最大年龄 | `300` 秒 |
| consumer/provider 最大时钟偏差 | `30` 秒 |
| confirmation TTL | `300` 秒 |
| redirect | 禁止 |
| TLS | 必须验证；禁止关闭证书验证 |
| credential | 短期、只读、进程内；不得进入 canonical bytes、日志、数据库或 Git |

authority contract hash 对上述完整 profile 的规范字节计算。endpoint、时间窗口、TLS、凭据范围或 transport lock 任一变化都形成新的 profile/hash，不得在配置中静默覆盖。

## 7. 原始状态证据与 PIT

对闭包中的每个 Release，必须在同一次 admission 窗口通过真实 HTTPS 获取完整 status history，并保留：

- Release ID、HTTP response 原始字节 SHA-256、状态响应头的允许字段；
- 完整事件链、当前 head 的 event ID/hash/sequence/status/recorded_at；
- `provider_snapshot_at`、本地 `checked_at`、authority profile hash；
- Schema validation、身份闭合和授权结果。

Bearer Token、Authorization header、完整请求头和任何凭据不得保留。

每条链必须从 sequence 1 连续到 head，previous hash、自哈希、Release ID 与 `current_status_event` 闭合；head 必须为 `published`。`withdrawn` 是终态；building、validated、withdrawn、空链、断链、未知字段或无法确认均阻断。

PIT 约束：

- `status_recorded_at <= provider_snapshot_at`；
- provider snapshot 不得领先本地时钟超过 `30` 秒；
- pin transaction 开始时，snapshot 年龄不得超过 `300` 秒；
- item.checked_at 必须位于 confirmation request/confirm 窗口；
- confirmation 必须在 `confirmed_at + 300` 秒前消费；
- transaction 前若发现新的状态 head，旧 confirmation 立即失效。

原始 response bytes 必须进入 IS 自有内容寻址缓存并由 hash 引用；动态 meta 只属于观察身份，不进入 Release/Manifest 语义哈希。

## 8. RunReleaseStatusConfirmation

6B 必须把现有 `0.1.0-draft` 合同经批准后升级为独立版本，至少绑定：

- confirmation/run/root Release identity；
- receipt hash、完整 closure hash；
- authority ID/profile hash；
- requested/confirmed/expires 时间；
- 按 Release ID 排序的完整 items；
- 每项五字段 input ref、status observation、event ID/hash/sequence、snapshot/check 时间和 response bytes hash；
- canonical profile 与 self hash。

confirmation 只能由受信 6B issuer 基于本次实际验证的 response bytes 构造，不能接受调用方自报 PASS。Stage 3D 的 response hash、旧 confirmation、另一个 run 的 confirmation 或 Stage 7 confirmation 均不得复用。

## 9. Manifest、Observation 与 admission seal

`HistoricalRunAdmissionEnvelope` 必须同时绑定：

- HistoricalAdmissionRequest 与 preregistration hash；
- 精确 `ArtifactConsumptionReceipt`；
-完整 `ReleaseRetentionClosure`；
- root fetch/status/admission Observation 及每个 source Release 的 status evidence；
- `StrategyRunManifest` 的完整 canonical bytes/hash；
- `RunReleaseStatusConfirmation`；
- pin releases/artifacts 的规范集合；
- admission transaction profile、schema version 和代码提交。

`HistoricalRunAdmissionSeal` 是上述闭包成功提交后的唯一可见完成标志，至少包含 `run_id`、envelope hash、manifest hash、confirmation hash、closure hash、commit generation/transaction ID、committed_at 与 seal hash。

后续 evaluator 只能接收从状态库重新读取并完整复核的 seal；不能以“对象构造成功”、Stage 3 验收记录、单独 confirmation 或调用方布尔值替代。

## 10. 原子提交语义

网络 I/O、Schema/哈希校验和候选 CAS 字节准备在 SQLite 写事务之前完成；持有数据库写锁期间禁止网络请求。

CAS 是内容寻址的非权威物理材料。事务失败或崩溃可能留下未被任何 seal 引用的完整 CAS orphan，但它不构成 run、pin、confirmation 或准入状态，不能被 evaluator 读取；不得自动删除任何已被历史引用的对象。

单一 `BEGIN IMMEDIATE` 权威事务必须重新验证 current heads、freshness、canonical bytes 和完整集合，并原子写入或精确链接：

1. Release identities、Manifest/artifact CAS 索引；
2. Receipt 与完整 Retention Closure；
3. append-only fetch/status/admission Observations 与 heads；
4. preregistration binding；
5. StrategyRunManifest；
6. RunReleaseStatusConfirmation 与 items；
7. full-closure pin releases/artifacts；
8. confirmation binding；
9. HistoricalRunAdmissionEnvelope；
10. 最后写 HistoricalRunAdmissionSeal。

任一步失败必须回滚全部权威行，seal 不存在，evaluator 调用为零。不能先提交 pin 再补 confirmation/seal，也不能让 caller 选择 artifact 子集。

## 11. 幂等、并发、崩溃与迁移

- 同一 `run_id`、request/envelope/seal 同字节重试返回既有结果，不创建新行；
- 同一 ID 或幂等键异字节必须 `IMMUTABLE_IDENTITY_CONFLICT`；
- 并发 admission 只有一个 generation 成功，失败方必须从最新 heads 重新构造，不能只重试写事务；
- WAL/IOERR/FULL/BUSY、进程崩溃和断电恢复后只能观察到完整 seal 或无 seal；
- `INSERT OR REPLACE`、直接 UPDATE/DELETE、head 回拨和 child-row 注入必须失败关闭；
- SQLite v2 quarantine 永久 audit-only，补写 confirmation 不得恢复新 run；
- Stage 5D 预留的 SQLite v4 不得被 6B 偷用或改义。6B 实现前必须形成不与 5D-2 冲突的迁移版本/表前缀并由 owner 批准；未决定时只允许临时数据库验证，不得迁移正式状态库。

## 12. 撤回、读取与 audit replay

任何 closure Release 在 admission 前撤回或不可确认都阻止新 seal。seal 提交后出现撤回：

- 不改写历史 seal、Manifest、receipt、结果或输入字节；
- 阻止所有新的 current decision/historical admission；
- 既有材料仅能按精确 source run/replay hash 做 `audit_replay`；
- audit 重新显示当前撤回状态，保持 `audit_only=true`、全部 authority false、零写入；
- 不生成新策略结论、批准、仓位、订单或 paper/live 行为。

普通读取与 audit 读取都必须重验 canonical parent、child indexes、CAS 和完整 pin closure；SQLite 投影不能替代 canonical bytes。

## 13. 失败状态与最低验收矩阵

6B admission 状态 closed world：

- `SEALED_VALIDATION_ONLY`：仅 6B 临时/隔离验收 seal；
- `PRECHECK_BLOCKED`：I/O 前身份、scope、Schema 或配置失败；
- `STATUS_UNCONFIRMED`：状态、authority、freshness 或链无法确认；
- `RECONCILIATION_BLOCKED`：Receipt/closure/Manifest/Observation/confirmation/pin 不一致；
- `IMMUTABLE_IDENTITY_CONFLICT`：同键异字节；
- `ATOMIC_COMMIT_BLOCKED`：SQLite/CAS/并发/崩溃门失败；
- `AUDIT_REPLAY_ONLY`：撤回后或 legacy quarantine 的只读审计。

最低测试必须覆盖：exact happy seal、每个 closure source、新鲜度等号与超界、时钟偏差、断链/撤回/非 published、response 篡改、缺/多 closure item、single input、Manifest/Receipt/Observation/preregistration 漂移、同键幂等/冲突、并发 generation、每个原子步骤失败、WAL 恢复、canonical/child/CAS 篡改、v2 quarantine、撤回后 audit 和零 evaluator 调用。

6B 验收必须使用独立临时 IS state/cache；不得修改 KB，不得读取 KB 内部状态，不得把测试 seal 留在正式 state DB。

## 14. Owner 逐项批准清单

- [ ] `6B-01`：批准 6B 只负责 historical admission、状态确认、原子留存和 seal，不执行策略 evaluator、development、walk-forward 或 holdout。
- [ ] `6B-02`：批准拟议 scope 为 `stage6_historical_admission_validation`；当前 draft 零 capability，获批后也只允许隔离 validation-only 验收。
- [ ] `6B-03`：批准精确绑定 Stage 6A 批准谱系、`59e1edd` 基线、IS 自有消费/留存/Manifest/confirmation 合同和 `aab36fe` transport snapshot。
- [ ] `6B-04`：批准只经 KB 公共只读 HTTPS/不可变导出消费内容，当前状态 authority 必须另经真实在线 HTTPS 获取，禁止 KB 内部读取和 KB 写入。
- [ ] `6B-05`：批准 `HistoricalAdmissionRequest` 内容寻址，并要求一个且仅一个五字段 `strategy_input_ref`、精确规则/代码/配置/预注册/transport/authority 身份。
- [ ] `6B-06`：批准 validation preregistration fixture 必须显式非历史证据；正式预注册缺失或含未决字段时不得签发正式 seal。
- [ ] `6B-07`：批准 Receipt 根与 Retention Closure 分层，闭包精确覆盖所有传递 Release、Manifest、依赖和 artifact，禁止 caller 少报或多报。
- [ ] `6B-08`：批准 closure source Release 不是第二个策略输入，首版 run 仍只有一个对外 `strategy_input_ref`。
- [ ] `6B-09`：批准 authority ID、endpoint、path、transport lock、TLS、redirect 和 credential 边界按第 6 节精确冻结，任一变化形成新 profile/hash。
- [ ] `6B-10`：批准 provider snapshot 最大年龄 `300` 秒、最大时钟偏差 `30` 秒、confirmation TTL `300` 秒，边界按含等号通过、超出失败关闭。
- [ ] `6B-11`：批准短期只读凭据只在进程内使用，Token/Authorization header 不得进入 canonical bytes、日志、状态库、缓存或 Git。
- [ ] `6B-12`：批准每个 closure Release 获取完整 status history 原始响应和 response SHA，事件链必须连续、自哈希闭合且 current head 为 published。
- [ ] `6B-13`：批准状态 recorded/snapshot/checked/confirmed/expires 的 PIT 关系和 transaction 前新 head 失效规则。
- [ ] `6B-14`：批准原始状态 response bytes 进入 IS CAS，动态 meta 只作观察证据，不进入 Release/Manifest 语义哈希。
- [ ] `6B-15`：批准 RunReleaseStatusConfirmation 精确绑定 run、receipt、closure、authority、时间窗和完整排序 items，并由受信 issuer 从实际 response 构造。
- [ ] `6B-16`：批准禁止复用 Stage 3 validation-only、旧 run、另一个 run、Stage 7 或调用方自报的 confirmation。
- [ ] `6B-17`：批准 HistoricalRunAdmissionEnvelope 同时绑定 request/preregistration、Receipt、Closure、Observations、Manifest、confirmation、pin 集合和事务 profile。
- [ ] `6B-18`：批准 HistoricalRunAdmissionSeal 是唯一 admission 完成标志；后续 evaluator 只能消费从状态库重读并复核的 exact seal。
- [ ] `6B-19`：批准网络与候选 CAS 准备在事务外完成，数据库写事务内禁止网络 I/O。
- [ ] `6B-20`：批准未被 seal 引用的 CAS orphan 不是权威 run 状态，不可被 evaluator 读取；历史已引用制品不得自动删除。
- [ ] `6B-21`：批准第 10 节十类对象在单一 `BEGIN IMMEDIATE` 中原子链接/写入，并最后写 seal。
- [ ] `6B-22`：批准任何 admission 失败权威状态零写、seal 不存在且 evaluator 调用为零，不允许 partial pin、partial Manifest 或 partial confirmation。
- [ ] `6B-23`：批准同 run 同字节幂等、同键异字节冲突，失败 run 不得被成功重试覆盖。
- [ ] `6B-24`：批准并发只有一个 generation 成功，heads 变化后必须重新构造全部 admission，不能只重试 SQL。
- [ ] `6B-25`：批准 WAL/IOERR/FULL/BUSY/崩溃恢复只能观察完整 seal 或无 seal，并阻断 REPLACE、UPDATE/DELETE、head 回拨和 child 注入。
- [ ] `6B-26`：批准 SQLite v2 quarantine 永久 audit-only，任何补写不得恢复新 run。
- [ ] `6B-27`：批准不得占用 Stage 5D 已预留的 SQLite v4 语义；6B 正式迁移版本/表前缀须另行明确批准，未决前只使用临时验证库。
- [ ] `6B-28`：批准任一 closure Release 撤回或不可确认阻断新 seal，历史 seal 不改写且只允许严格 audit replay。
- [ ] `6B-29`：批准普通读取和 audit replay 均重验 canonical parent、child indexes、CAS 与完整 pin closure，SQLite 投影不能冒充权威字节。
- [ ] `6B-30`：批准第 13 节七种 admission 状态 closed world 和最低失败注入矩阵，不得用异常吞掉、默认 PASS 或静默降级。
- [ ] `6B-31`：批准 6B 验收只在独立临时 IS state/cache 中进行，所有 output 保持 validation-only、authority_eligible=false，正式 state DB 与 KB 零修改。
- [ ] `6B-32`：批准 32 项必须整包原子批准；部分、pending、拒绝、identity drift 或缺验收均保持零 runtime authority，6C/6D 继续未授权。

## 15. 批准后的唯一实施顺序

1. 保持本规格和 draft machine proposal 原始字节不变；
2. owner 原子批准或退回第 14 节 32 项；
3. 获批后形成独立 approved bundle、approval record 和 6B validation capability；
4. 先实现纯 contracts/issuer/adapter，再实现临时库原子 seal，不修改正式状态库；
5. 跑离线 failure matrix，再用短期只读凭据做一次真实 HTTPS validation-only seal 验收；
6. 单独批准存储迁移后才允许正式状态库升级；
7. 6B 验收完成后，另行形成包含所有具体日期和统计阈值的正式 preregistration；
8. 6C 仍须独立授权，6D holdout 仍保持关闭。

任一缺项不得通过修改现有 Stage 2A pin 骨架、复用 Stage 3 证据或直接运行历史策略绕过。
