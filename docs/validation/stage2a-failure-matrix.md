# Stage 2A 离线内核失败矩阵

> 文档状态：`active / implementation_mapped / ci_acceptance_pending`
> 适用范围：`Stage 2A 公共契约验证、provider-neutral 投影、消费持久化、run-scoped 状态确认、准入与留存内核`
> 不在范围：`HTTP transport、immutable export transport、真实 provider current status、正式 Release E2E、策略语义`

本文把 Stage 2A 完成门映射到仓库中已经存在的测试 ID。测试存在只表示行为已有可执行检查，不能替代锁定环境和 Windows/Linux CI 的实际成功记录；本文不登记 Stage 2A 已完成，也不登记当前 CI 已通过。

## 1. 输入分类

| 标识 | 含义 | 证据使用规则 |
|---|---|---|
| `KB_OFFICIAL_FIXTURE` | `contracts/providers/investment_research_kb/v1/vendor/` 中受 snapshot lock、官方 contract lock 和 fixture lock 共同保护的原始字节 | 只作正常契约、规范化和确定性投影锚点；不得改写后继续称为官方 fixture，也不得把其中的 `published` 当作当前运行授权。 |
| `INVESTSYSTEM_FAILURE_INJECTION` | InvestSystem 在临时目录或内存中复制确定输入后主动篡改、重封装或构造的负例 | 只证明消费者失败关闭；不得冒充 KB 官方负例、真实 Release 或 provider 当前状态。 |
| `INVESTSYSTEM_SYNTHETIC_STATE` | InvestSystem 自建的 Receipt、Observation、Retention Closure、Manifest 和状态场景 | 用于验证本地幂等、冲突、因果、准入、pin 和 audit replay；不证明真实 KB 传输或策略能力。 |
| `SQLITE_CORRUPTION_INJECTION` | 测试绕过公共 API，直接通过 SQLite 写入、替换、删除或修改内部行、索引投影、head、trigger 或 schema | 只验证数据库防篡改和再次读取时的重核；这些写法不是支持的运行接口。 |
| `CAS_CORRUPTION_INJECTION` | 测试直接损坏、缺失、替换或链接内容寻址缓存中的文件或路径 | 验证每次读取、pin 和容量扫描都失败关闭；不授权自动删除或修复历史材料。 |
| `STATIC_ISOLATION_GUARD` | 对源码、依赖、Git 元数据、默认路径和 CI 配置执行静态边界检查 | 证明仓库没有已知的跨仓隐式依赖；不替代操作系统权限和部署侧只读凭证。 |

所有从官方 fixture 派生但发生过任何修改的测试样本都归类为 `INVESTSYSTEM_FAILURE_INJECTION`，即使测试文件位于 `tests/contracts/`。

## 2. 正向控制锚点

| 输入分类 | 应成立的不变量 | 现有测试 ID |
|---|---|---|
| `KB_OFFICIAL_FIXTURE` | 固定来源提交、14 个锁定 v1 Schema、官方 fixture 和逐文件哈希能够形成只读 catalog | `tests/contracts/test_kb_contract_snapshot.py::test_fixed_public_catalog_verifies_all_fourteen_schemas_and_stage6_fixture` |
| `KB_OFFICIAL_FIXTURE` | provider canonical JSON、JSONL 和 Manifest 向量按 `irkb-jsonl-v1` 得到官方预期结果 | `tests/contracts/test_kb_provider_canonical.py::test_all_official_canonical_json_vectors`；`tests/contracts/test_kb_provider_canonical.py::test_all_official_jsonl_vectors`；`tests/contracts/test_kb_provider_canonical.py::test_all_official_manifest_vectors` |
| `KB_OFFICIAL_FIXTURE` | 同一固定 fixture 重复验证得到相同输入引用、Receipt、闭包、Manifest 字节和 provider-neutral 投影 | `tests/contracts/test_kb_reference_fixture.py::test_official_reference_fixture_projects_deterministically` |
| `KB_OFFICIAL_FIXTURE` | 公共入口只能使用已通过全部 lock 的 catalog 内 fixture，调用方不能替换文档 | `tests/contracts/test_kb_reference_fixture.py::test_public_reference_entrypoint_accepts_only_the_hash_locked_catalog_fixture` |
| `KB_OFFICIAL_FIXTURE` | 官方 fixture 可原样持久化完整留存闭包，但 contract-test 中的 `published` 不会自行授权新 run | `tests/acceptance/test_stage2a_offline_persistence.py::test_official_fixture_persists_exact_closure_but_never_authorizes_a_run` |
| `KB_OFFICIAL_FIXTURE` | 固定 fixture 的状态摘要只做交叉绑定，不冒充完整 status-event 正文或当前状态 authority | `tests/contracts/test_kb_reference_fixture.py::test_change_event_must_bind_the_validated_release`；`tests/acceptance/test_stage2a_offline_persistence.py::test_official_fixture_persists_exact_closure_but_never_authorizes_a_run` |
| `STATIC_ISOLATION_GUARD` | 两种批准传输面在公共传输契约固定前都以稳定 blocker code 在 I/O 前拒绝，代码与支持矩阵一致 | `tests/contracts/test_kb_transport_capability.py::test_every_approved_kb_transport_fails_closed_before_io`；`tests/contracts/test_kb_transport_capability.py::test_support_matrix_matches_the_executable_transport_boundary` |
| `INVESTSYSTEM_SYNTHETIC_STATE` | 正式本地路径从 Receipt 派生完整闭包 pin，重复 pin 幂等，普通读取与审计读取严格分离 | `tests/unit/test_storage.py::test_formal_path_pins_full_closure_and_separates_normal_from_audit` |

## 3. 公共契约、来源和 Schema 失败矩阵

| 输入分类 | 故障或攻击 | 预期失败语义 | 现有测试 ID |
|---|---|---|---|
| `INVESTSYSTEM_FAILURE_INJECTION` | 请求未锁定路径、父目录、绝对路径或 Windows 分隔路径 | catalog 拒绝读取，不能越过固定 vendor 清单 | `tests/contracts/test_kb_contract_snapshot.py::test_catalog_reads_only_locked_safe_vendor_paths` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 重复 JSON key、NFC 后 key 冲突、NaN 或 Infinity | strict JSON 解析失败，不接受歧义或非有限数 | `tests/contracts/test_kb_contract_snapshot.py::test_strict_json_rejects_ambiguous_keys_and_non_finite_numbers` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 锁定文件增加一个字节 | snapshot 大小/哈希核对失败 | `tests/contracts/test_kb_contract_snapshot.py::test_snapshot_lock_detects_one_byte_tampering` |
| `INVESTSYSTEM_FAILURE_INJECTION` | `source_contracts_tree` 被改写 | 固定来源树身份核对失败 | `tests/contracts/test_kb_contract_snapshot.py::test_snapshot_lock_requires_the_exact_source_tree_identities` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 单文件 Git blob 身份被改写 | snapshot Git blob 核对失败 | `tests/contracts/test_kb_contract_snapshot.py::test_snapshot_lock_binds_each_source_git_blob_identity` |
| `INVESTSYSTEM_FAILURE_INJECTION` | fixture lock 被篡改，但外层 snapshot 被重新封装 | 独立官方 fixture lock 仍拒绝输入 | `tests/contracts/test_kb_contract_snapshot.py::test_stage6_fixture_lock_is_checked_independently_of_snapshot_lock` |
| `INVESTSYSTEM_FAILURE_INJECTION` | fixture 声明未知 artifact Schema | 未知 provider contract ID 失败关闭 | `tests/contracts/test_kb_contract_snapshot.py::test_unknown_artifact_schema_in_stage6_fixture_fails_closed` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 被篡改的 Schema 与 lock 一起重新封装 | Draft 2020-12 Schema 自检仍拒绝无效 Schema | `tests/contracts/test_kb_contract_snapshot.py::test_invalid_resealed_schema_fails_draft_2020_12_self_check` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 时间字符串满足正则但日历日期不存在 | format checker 拒绝无效时间 | `tests/contracts/test_kb_contract_snapshot.py::test_format_checker_rejects_calendar_invalid_but_pattern_matching_timestamp` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 锁定 vendor 文件被符号链接替换 | catalog 拒绝链接对象 | `tests/contracts/test_kb_contract_snapshot.py::test_locked_vendor_file_replaced_by_link_is_rejected` |
| `INVESTSYSTEM_FAILURE_INJECTION` | `latest`、裸字符串 `manifest_hash`、大写哈希、非 UTC、错误字段名、额外字段或浮点数 | InvestSystem 输入 Schema 失败关闭，五字段引用不能漂移 | `tests/contracts/test_schemas.py::test_verified_input_schema_fails_closed_on_contract_drift`；`tests/contracts/test_schemas.py::test_strategy_input_reference_schema_has_exact_five_fields` |
| `INVESTSYSTEM_FAILURE_INJECTION` | Receipt、Observation 或闭包 Schema 出现未知字段、裸哈希、非法枚举或结构漂移 | InvestSystem 自有消费契约失败关闭 | `tests/unit/test_consumption.py::test_consumption_schemas_fail_closed`；`tests/unit/test_retention.py::test_retention_machine_contract_rejects_structural_drift` |

## 4. Release 内容、状态、PIT 与投影失败矩阵

| 输入分类 | 故障或攻击 | 预期失败语义 | 现有测试 ID |
|---|---|---|---|
| `INVESTSYSTEM_FAILURE_INJECTION` | artifact 同大小字节篡改 | `ARTIFACT_HASH_MISMATCH` | `tests/contracts/test_kb_reference_fixture.py::test_same_size_artifact_tampering_fails_hash_check` |
| `INVESTSYSTEM_FAILURE_INJECTION` | artifact 大小变化 | 在投影前得到 `ARTIFACT_SIZE_MISMATCH` | `tests/contracts/test_kb_reference_fixture.py::test_artifact_size_tampering_fails_before_projection` |
| `INVESTSYSTEM_FAILURE_INJECTION` | Manifest self hash 被篡改 | `MANIFEST_HASH_MISMATCH` | `tests/contracts/test_kb_reference_fixture.py::test_manifest_self_hash_is_verified` |
| `INVESTSYSTEM_FAILURE_INJECTION` | artifact 重封装后保留错误 logical content hash | `CONTENT_HASH_MISMATCH` | `tests/contracts/test_kb_reference_fixture.py::test_semantic_self_hash_is_verified_after_artifact_resealing` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 当前状态为 `building`、`validated` 或 `withdrawn` | `RELEASE_NOT_PUBLISHED`，不能生成可准入结果 | `tests/contracts/test_kb_reference_fixture.py::test_every_non_published_current_status_fails_closed` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 图边 `available_at` 晚于 cutoff | `PIT_VIOLATION` | `tests/contracts/test_kb_reference_fixture.py::test_future_available_at_fails_pit_after_valid_resealing` |
| `INVESTSYSTEM_FAILURE_INJECTION` | source Release cutoff 晚于 Context Release cutoff | `PIT_VIOLATION` | `tests/contracts/test_kb_reference_fixture.py::test_source_release_cutoff_cannot_exceed_context_cutoff` |
| `INVESTSYSTEM_FAILURE_INJECTION` | review 或 publication 时间晚于 cutoff | `PIT_VIOLATION` | `tests/contracts/test_kb_reference_fixture.py::test_future_review_and_publication_times_fail_pit_after_full_resealing` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 图可见时间早于来源文档，或图边早于端点节点 | `PIT_VIOLATION` | `tests/contracts/test_kb_reference_fixture.py::test_graph_cannot_be_available_before_its_source_document`；`tests/contracts/test_kb_reference_fixture.py::test_graph_edge_cannot_predate_its_endpoint_nodes` |
| `INVESTSYSTEM_FAILURE_INJECTION` | fixture 中两个状态摘要不再互相绑定 | `CHANGE_STREAM_MISMATCH`；不尝试按缺失正文发明 status-event self-hash | `tests/contracts/test_kb_reference_fixture.py::test_change_event_must_bind_the_validated_release` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 出现当前窄投影不支持的非空集合 | `PROJECTION_UNSUPPORTED`，不能静默丢字段 | `tests/contracts/test_kb_reference_fixture.py::test_nonempty_unsupported_collection_is_never_silently_dropped` |
| `INVESTSYSTEM_FAILURE_INJECTION` | Context Pack source Release 身份与 Manifest 不一致 | `SOURCE_RELEASE_MISMATCH` | `tests/contracts/test_kb_reference_fixture.py::test_context_pack_source_release_must_match_manifest_build` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 图端点不能闭合到固定证据链，或边语义与 provider Fact 冲突 | `EVIDENCE_CHAIN_MISMATCH` | `tests/contracts/test_kb_reference_fixture.py::test_graph_endpoint_must_close_to_the_pinned_evidence_chain`；`tests/contracts/test_kb_reference_fixture.py::test_graph_edge_semantics_must_match_the_pinned_provider_fact` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 五字段输入引用与已验证 Release 不一致 | `INPUT_REF_MISMATCH` | `tests/contracts/test_kb_reference_fixture.py::test_five_field_input_reference_must_match_the_validated_release` |

## 5. Receipt、Observation 与留存闭包失败矩阵

| 输入分类 | 故障或攻击 | 预期失败语义 | 现有测试 ID |
|---|---|---|---|
| `INVESTSYSTEM_FAILURE_INJECTION` | Receipt self hash 错误、空制品、无序制品或重复 artifact ID | 构造阶段拒绝，Receipt 身份不能模糊 | `tests/unit/test_consumption.py::test_receipt_rejects_wrong_self_hash_empty_or_unordered_items`；`tests/unit/test_consumption.py::test_receipt_is_order_independent_but_rejects_duplicate_artifact_ids` |
| `INVESTSYSTEM_FAILURE_INJECTION` | fetch/status/admission 的结果、状态或失败原因互相矛盾 | Observation 构造失败 | `tests/unit/test_consumption.py::test_observations_enforce_failure_and_admission_semantics` |
| `INVESTSYSTEM_FAILURE_INJECTION` | Observation 使用 `latest`、非 UTC、未知枚举或 self-supersession | Observation 失败关闭 | `tests/unit/test_consumption.py::test_observations_reject_latest_non_utc_unknown_enum_and_self_supersession` |
| `INVESTSYSTEM_FAILURE_INJECTION` | Observation 只绑定部分或错误的五字段 Release 身份 | Observation 构造失败 | `tests/unit/test_consumption.py::test_every_observation_binds_the_full_input_reference_identity` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 闭包根身份与 Receipt 五字段引用漂移 | 闭包构造失败 | `tests/unit/test_retention.py::test_closure_rejects_any_root_five_field_identity_mismatch` |
| `INVESTSYSTEM_FAILURE_INJECTION` | source 依赖缺失、cutoff 晚于父 Release、出现不可达节点或环 | 闭包构造失败 | `tests/unit/test_retention.py::test_closure_rejects_missing_dependency_and_future_dependency_cutoff`；`tests/unit/test_retention.py::test_closure_rejects_unreachable_nodes_and_cycles` |
| `INVESTSYSTEM_FAILURE_INJECTION` | Manifest 文档物理哈希或大小错误 | 留存节点拒绝错误物理承诺 | `tests/unit/test_retention.py::test_manifest_document_commitment_rejects_wrong_hash_or_size` |
| `INVESTSYSTEM_FAILURE_INJECTION` | artifact/Manifest payload 使用非法 ID、非 bytes 或多余/缺失集合 | payload 或持久化入口拒绝 | `tests/unit/test_retention.py::test_byte_payloads_reject_invalid_ids_and_non_bytes`；`tests/unit/test_storage.py::test_record_verified_consumption_is_exact_idempotent_and_opaque_manifest_safe` |

## 6. SQLite v3 状态确认、准入、pin 与审计失败矩阵

| 输入分类 | 故障或攻击 | 预期失败语义 | 现有测试 ID |
|---|---|---|---|
| `INVESTSYSTEM_SYNTHETIC_STATE` | 新 pin 没有 run-scoped confirmation，或没有被允许的精确 authority contract | 默认拒绝，零 confirmation/pin 持久化 | `tests/unit/test_storage.py::test_new_pin_defaults_to_fail_closed_without_confirmation_or_authority` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 调用方尝试通过公开属性或已取得的 policy 映射就地修改配置 | 不暴露公共可变入口，构造时取得的私有配置快照不能就地修改；受信进程内任意代码本身不属于安全边界 | `tests/unit/test_storage.py::test_authority_policy_registry_exposes_no_public_mutation_surface` |
| `INVESTSYSTEM_FAILURE_INJECTION` | confirmation 缺少 source Release、已过期或绑定另一个 run | 必须精确覆盖完整闭包且仍在可信时间窗内，整笔事务回滚 | `tests/unit/test_storage.py::test_confirmation_rejects_missing_closure_item_expiry_and_wrong_run_binding` |
| `INVESTSYSTEM_FAILURE_INJECTION` | confirmation 的 provider event ID/hash/sequence 或五字段 Release 身份与持久状态漂移 | confirmation 与 current passed/published event 及闭包身份必须逐字段一致 | `tests/unit/test_storage.py::test_confirmation_rejects_status_event_or_release_identity_mismatch` |
| `INVESTSYSTEM_FAILURE_INJECTION` | confirmation 在闭包之外增加一个 Release | 根及全部传递 source Release 必须精确覆盖，不得多交或少交 | `tests/unit/test_storage.py::test_confirmation_rejects_an_extra_release_outside_the_closure` |
| `INVESTSYSTEM_FAILURE_INJECTION` | provider snapshot 超过 authority 最大年龄、领先本地时钟、超过检查时钟偏差，或 provider event 晚于 snapshot | 状态当前性和时间因果失败关闭 | `tests/unit/test_storage.py::test_confirmation_rejects_stale_provider_snapshot`；`tests/unit/test_storage.py::test_confirmation_rejects_provider_snapshot_clock_skew`；`tests/unit/test_storage.py::test_confirmation_rejects_event_after_provider_snapshot` |
| `INVESTSYSTEM_SYNTHETIC_STATE` | confirmation 之后任一 source Release 出现撤回事件 | 新 pin 拒绝，既有历史材料不被改写 | `tests/unit/test_storage.py::test_confirmation_cannot_admit_after_a_new_withdrawal_event` |
| `INVESTSYSTEM_SYNTHETIC_STATE` | source Release 尚未被当前 `published` 状态完整确认 | 整个 `pin_run` 回滚，不产生部分 pin | `tests/unit/test_storage.py::test_pin_is_atomic_until_every_source_is_current_published` |
| `INVESTSYSTEM_SYNTHETIC_STATE` | root Release 撤回 | 新 pin 和普通读取失败；既有固定材料仅可 `audit_replay`；撤回终态不能恢复 | `tests/unit/test_storage.py::test_withdrawal_blocks_normal_access_but_preserves_audit` |
| `INVESTSYSTEM_SYNTHETIC_STATE` | source Release 撤回 | 审计上下文显示 source 当前撤回，不得由 root 历史授权掩盖 | `tests/unit/test_storage.py::test_source_withdrawal_is_visible_in_source_audit_context` |
| `INVESTSYSTEM_SYNTHETIC_STATE` | provider event ID/hash 被重映射或旧 sequence 回放 | current head 保持不变并拒绝输入 | `tests/unit/test_storage.py::test_status_replay_and_stale_sequence_leave_head_unchanged` |
| `INVESTSYSTEM_SYNTHETIC_STATE` | provider status chain 不从 sequence 1 开始、存在缺口或 previous hash 错误 | 状态不可确认，不能授权或 pin | `tests/unit/test_storage.py::test_provider_status_chain_rejects_gaps_and_wrong_previous_hash` |
| `INVESTSYSTEM_SYNTHETIC_STATE` | Observation、Manifest 或 pin 的持久化/业务时间倒置 | 因果检查失败关闭 | `tests/unit/test_storage.py::test_observation_and_manifest_persistence_times_enforce_real_causality`；`tests/unit/test_storage.py::test_admission_cannot_predate_status`；`tests/unit/test_storage.py::test_manifest_cannot_predate_required_observation` |
| `INVESTSYSTEM_SYNTHETIC_STATE` | 相同 Observation 重试、同 ID 不同内容、非线性 supersedes | 精确重复幂等；身份冲突或非线性推进被拒绝 | `tests/unit/test_storage.py::test_observation_idempotency_collision_and_linear_supersedes` |
| `INVESTSYSTEM_FAILURE_INJECTION` | 已复用闭包的 child index 在关联新 Receipt 前被污染 | 新关联失败，不能复用损坏闭包 | `tests/unit/test_storage.py::test_reused_closure_is_verified_before_linking_a_new_receipt` |
| `SQLITE_CORRUPTION_INJECTION` | pin 事务中人为触发 SQLite 写失败，或调用旧的 artifact 子集参数 | 所有派生 pin 回滚；调用方不能少报 artifact | `tests/unit/test_storage.py::test_pin_failure_rolls_back_every_derived_pin_and_removes_subset_bypass` |
| `INVESTSYSTEM_SYNTHETIC_STATE` | 多线程首次打开同一空库 | 有界初始化重试收敛到一个完整、可验证的 SQLite v3，不暴露半成品 | `tests/unit/test_storage.py::test_concurrent_first_initialization_converges_on_one_verified_v3` |
| `INVESTSYSTEM_SYNTHETIC_STATE` | 非空、已验证的 SQLite v2 含有旧 pin，但没有 run confirmation | 无损升级为 v3 并写入不可变 quarantine；旧 pin 只能 `audit_replay`，普通读取和重新准入均拒绝 | `tests/unit/test_storage.py::test_nonempty_v2_migrates_losslessly_as_audit_only` |

## 7. SQLite 直接篡改失败矩阵

| 输入分类 | 故障或攻击 | 预期失败语义 | 现有测试 ID |
|---|---|---|---|
| `SQLITE_CORRUPTION_INJECTION` | 直接 `UPDATE` Observation 或 `DELETE` current head | append-only/head trigger 阻止写入 | `tests/unit/test_storage.py::test_append_only_triggers_cover_observations_and_head_delete` |
| `SQLITE_CORRUPTION_INJECTION` | `INSERT OR REPLACE`、head 回拨或不可变主键冲突 | 即使 `recursive_triggers=OFF` 也拒绝绕过 | `tests/unit/test_storage.py::test_database_guards_reject_replace_and_head_rollback_bypasses` |
| `SQLITE_CORRUPTION_INJECTION` | 撤回后直接插入并切换到伪造 `published` status | 全链重核识别撤回终态，新 pin 和普通读取失败 | `tests/unit/test_storage.py::test_forged_status_after_withdrawal_cannot_restore_release_access` |
| `SQLITE_CORRUPTION_INJECTION` | 修改 Observation canonical parent 或 subtype 投影 | canonical 文档是权威，授权和 pin 失败 | `tests/unit/test_storage.py::test_canonical_observation_remains_authoritative_over_sqlite_projection` |
| `SQLITE_CORRUPTION_INJECTION` | 注入字段投影看似有效、但 canonical status 不符合机器契约的行 | admission 与 pin 均失败关闭 | `tests/unit/test_storage.py::test_non_contract_canonical_status_cannot_be_authorized_or_pinned` |
| `SQLITE_CORRUPTION_INJECTION` | 给既有 Receipt 追加 child artifact 行 | canonical Receipt 与索引不一致，读取失败 | `tests/unit/test_storage.py::test_canonical_receipt_rejects_appended_child_rows` |
| `SQLITE_CORRUPTION_INJECTION` | 同时给闭包和 pin 追加自洽 child 行 | canonical Closure 仍拒绝扩大历史集合 | `tests/unit/test_storage.py::test_canonical_closure_rejects_self_consistent_appended_pin_rows` |
| `SQLITE_CORRUPTION_INJECTION` | 为迁移自 v2 的 quarantined run 直接注入完整 confirmation/items/binding | quarantine 优先；不能恢复 `NEW_RUN`，也不能污染原历史审计重放 | `tests/unit/test_storage.py::test_nonempty_v2_migrates_losslessly_as_audit_only` |
| `SQLITE_CORRUPTION_INJECTION` | confirmation canonical JSON 含额外字段、错误 JSON 类型、布尔 sequence、非规范 UTC/排序/字节或模型语义错误；或数据库中 parent hash 与投影被一起伪造成自洽 | 严格解析和逐字节模型往返失败，pin/read 不能依靠自洽哈希或 SQLite 投影取得授权 | `tests/unit/test_status_confirmation.py::test_strict_canonical_parser_rejects_structural_type_and_time_drift`；`tests/unit/test_status_confirmation.py::test_strict_canonical_parser_rejects_noncanonical_bytes_and_array_order`；`tests/unit/test_status_confirmation.py::test_strict_canonical_parser_rejects_invalid_documents`；`tests/unit/test_storage.py::test_non_contract_confirmation_parent_cannot_authorize_pin_or_read` |
| `SQLITE_CORRUPTION_INJECTION` | 非空 v1、未知 v1、未版本化 view、v3 额外 view 或缺失 trigger | 不做有损猜测迁移，保持原库并拒绝打开 | `tests/unit/test_storage.py::test_empty_known_v1_upgrades_but_nonempty_v1_is_preserved`；`tests/unit/test_storage.py::test_unknown_empty_v1_and_tampered_v3_fail_closed` |

## 8. CAS 与文件系统失败矩阵

| 输入分类 | 故障或攻击 | 预期失败语义 | 现有测试 ID |
|---|---|---|---|
| `CAS_CORRUPTION_INJECTION` | 已登记 CAS 内容被改写或出现孤立文件 | 容量报告区分 pinned、orphan 和 corrupt，不自动删除 | `tests/unit/test_storage.py::test_quota_reports_pinned_manifests_artifacts_orphans_and_corruption` |
| `CAS_CORRUPTION_INJECTION` | CAS 前缀目录被符号链接或 junction 替换 | 读写失败关闭 | `tests/unit/test_storage.py::test_cache_symlink_or_junction_is_rejected_fail_closed` |
| `CAS_CORRUPTION_INJECTION` | 外部文件通过硬链接伪装成项目独占 CAS 对象 | 不收养多硬链接对象 | `tests/unit/test_storage.py::test_cache_hardlink_is_not_adopted_as_independently_owned` |
| `CAS_CORRUPTION_INJECTION` | quota 扫描路径被目录链接替换 | 扫描失败关闭且不越出 cache root | `tests/unit/test_storage.py::test_quota_rejects_cache_path_replaced_by_directory_symlink`；`tests/unit/test_storage.py::test_quota_checks_cache_root_before_starting_walk` |
| `CAS_CORRUPTION_INJECTION` | 已 pin 的 source Manifest 或 artifact 字节被损坏 | 每次普通/审计读取重新验证完整闭包并拒绝损坏内容 | `tests/unit/test_storage.py::test_every_read_revalidates_source_artifacts_and_manifests` |

## 9. 跨仓和策略边界失败矩阵

| 输入分类 | 边界 | 预期失败语义 | 现有测试 ID |
|---|---|---|---|
| `STATIC_ISOLATION_GUARD` | 源码导入 KB 包或修改 `PYTHONPATH` | 架构测试失败 | `tests/architecture/test_repository_isolation.py::test_source_never_imports_the_kb_package_or_mutates_pythonpath` |
| `STATIC_ISOLATION_GUARD` | 策略代码导入 provider integration，包括动态或相对导入 | 架构测试失败，策略层只能接收 provider-neutral DTO | `tests/architecture/test_repository_isolation.py::test_strategy_code_cannot_import_provider_integrations`；`tests/architecture/test_repository_isolation.py::test_strategy_import_guard_covers_absolute_relative_and_dynamic_forms` |
| `STATIC_ISOLATION_GUARD` | 源码读取 sibling KB 路径、SQLite、`raw`、`staging` 或 `published` | 架构测试失败 | `tests/architecture/test_repository_isolation.py::test_source_contains_no_executable_sibling_repository_reference`；`tests/architecture/test_repository_isolation.py::test_source_has_no_static_kb_internal_path_reads` |
| `STATIC_ISOLATION_GUARD` | 依赖声明引入 KB editable/VCS/local path，或仓库出现 submodule/link/junction/hardlink | 架构测试失败 | `tests/architecture/test_repository_isolation.py::test_dependencies_contain_no_kb_editable_vcs_or_local_path`；`tests/architecture/test_repository_isolation.py::test_repository_has_no_submodule_symlink_junction_or_hardlink` |
| `STATIC_ISOLATION_GUARD` | required CI checkout 另一仓、依赖服务进程或共享状态 | 架构测试失败 | `tests/architecture/test_repository_isolation.py::test_required_ci_checks_out_only_this_repository_without_services` |

## 10. 正式验收要求

Stage 2A 关闭前，正式验收记录必须在精确实现提交上补充以下运行证据：

1. 从 `requirements-dev.lock` 建立的干净 Python 3.12 环境完成 `pip check`、Ruff、mypy、pytest、compileall 和 `git diff --check`；
2. GitHub Actions 的 Windows 与 Ubuntu 作业均完整执行并成功，登记 run/job URL、测试数和跳过原因；
3. 本矩阵中的测试 ID 与最终提交一致，任何改名、删除或语义变化均同步更新；
4. 官方 fixture、InvestSystem failure injection、SQLite corruption injection 和 CAS corruption injection 的报告标签保持分离；
5. 验收结论继续明确：Stage 2A 离线内核不等于 HTTP/export transport、真实 Release 消费、provider 当前状态确认或策略实现。

在上述证据形成前，本矩阵只能作为实现映射，不能单独把 Stage 2A 标记为 `completed`。
