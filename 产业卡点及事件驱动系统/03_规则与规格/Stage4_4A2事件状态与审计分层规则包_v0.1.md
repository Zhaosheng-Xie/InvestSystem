# Stage 4 / 4A-2 事件状态与审计分层规则包 v0.1

文档状态：`draft_for_owner_approval`

目标批准范围：`stage4_synthetic_research_validation`

当前批准：`none`

包含规则：`FR-EVT-001`、`FR-EVT-002`、`FR-EVT-003`、`FR-EVT-004`

当前权限：`specification and contract validation only`；不签发 runtime capability，不授权 `backtest`、`paper`、`shadow`、`live`、仓位、组合、订单或资金部署

## 1. 目的

本包把 PRD v0.3 的完整商业事件语义收敛为 owner 可逐项批准的提案，解决四个问题：

1. E0—E7/E3.5 如何按事实护照升级、降级、修订和迁移；
2. `E4_public` 如何独立于公告标题和 Stage 2B 窄规则判定；
3. 上市公司、卖方/供应商、客户/买方和采购主体如何关联，并固定最早合法公开事实；
4. Fact、Assumption、Derived、Judgment 如何物理与语义分层。

本包仍只面向 provider-neutral 合成 fixture。真实 KB transport、current-status authority 和 Context Pack smoke 属于 Stage 3；四道门、利润桥、估值和退出属于后续 4A 批次；成交、风险、仓位和订单属于 Stage 5。

Stage 2B 的 E3.5/E4 规则只作为已验证基线，不自动获得本包权限。本包未获 owner 精确批准前，代码只能验证 draft 文档结构和失败关闭边界，不能执行事件分类。

## 2. 公共结果与状态分离

### 2.1 四类结果

| 结果 | 含义 |
|---|---|
| `PASS` | 当前规则的全部事实与治理条件成立 |
| `REJECT` | 已有明确反证足以否决当前命题 |
| `ABSTAIN` | 未知、冲突、不可恢复或独立性不足，不能安全判断 |
| `BLOCKED` | PIT、权限、结构、身份、迁移或审计硬失败 |

同一规则内优先级为 `BLOCKED > REJECT > ABSTAIN > PASS`。`unknown` 不是 `false`；`conflicted` 不得按多数票自动解决。

### 2.2 三套状态必须分离

- `event_state`：E0—E7/E3.5，只描述商业事实成熟度；
- `decision_state`：研究、拒绝、`ABSTAIN`、`BLOCKED` 或后续四道门结果；
- `position_state`：Stage 5 才可管理的 `FLAT/STARTER/CORE/TRIM/EXIT`。

4A-2 只产生事件判断和研究审计。任何事件状态均不得自动产生仓位、订单或运行模式授权；`E3.5` 的 `SHADOW_ONLY` 只能是研究结果标签，不构成 `shadow` run 权限。

## 3. E 状态事实护照

### FR-EVT-001

每个状态使用独立的 `evidence passport`，不使用加权分数：

| 状态 | 必需事实护照 | 聚合 |
|---|---|---|
| `E0` | 产业需求或技术叙事已公开，目标公司商业验证尚未成立 | 叙事命题 `confirmed` |
| `E1` | 产品研发、样品、标准或技术可行性至少一项成立 | OR |
| `E2` | 客户测试、认证、定点或供应商资格至少一项成立 | OR |
| `E3` | 招标、采购意向、框架、预计份额或商业谈判至少一项成立 | OR |
| `E3.5` | 强商业线索成立，但 `E4_public` 为 `REJECT/ABSTAIN` | 强线索 AND E4 `REJECT/ABSTAIN` |
| `E4` | `FR-EVT-002` 的 `E4_public=PASS` | 严格 AND |
| `E5` | 实际交付、验收或可核验履约进展至少一项成立，且 E4 护照完整 | E4 AND 履约 OR |
| `E6` | 收入、增量利润、现金回收均得到财务验证，且 E5 护照完整 | E5 AND 三项 AND |
| `E7` | 复购/规模化、周期成熟、合同终止或论点完成之一有明确终局事实，并满足相应前置状态 | 前置状态 AND 终局 OR |

E7 终局子型及前置状态：

- `repeat_or_scale`、`cycle_matured`：至少已有 E6；
- `contract_terminated`：至少已有 E4；
- `thesis_completed`：至少已有 E0，并有显式完成/关闭理由。

### 3.1 状态选择

- 当前快照输出全部通过的 `attained_states`、最高非终局状态和可选 E7 终局；
- 允许一次新快照跨越多个序号状态，但只有中间每个必需护照均完整时才允许，不能制造虚假的逐日过渡；
- 中间护照缺失时不允许跳级，结果为 `ABSTAIN`；
- `E3.5` 不是 E4 的弱通过，也不是交易权限；E4 一旦 PASS，当前最高状态不得同时保留 E3.5；E4 为 `BLOCKED` 时不得产生 E3.5 或任何其他事件状态；
- `E5/E6/E7` 不自动触发加仓、持有或退出，只向后续规则提供事实成熟度。

### 3.2 修订、重复和降级

- `logical_event_id` 在同一商业事件修订链中稳定；每次快照使用新的 `event_snapshot_id` 和递增 `revision`；
- 完全相同 canonical content hash 的重复材料只登记 duplicate observation，不创建新状态；
- 同源转载、镜像、摘要和机器转述属于同一 `lineage_group_id`，不能增加独立证据数；
- 同一 logical event 出现新内容时创建 append-only revision，通过 `supersedes_event_snapshot_id` 关联，禁止覆盖旧快照；
- 明确 superseding 反证可使当前最高状态降级，或进入 `E7/contract_terminated`；必须保留 `previous_confirmed_state`、反证事实和原因；
- 仅因新输入缺字段、资料不可恢复或冲突，不能静默降级或沿用旧状态，应 `ABSTAIN` 并保留 last-confirmed 审计引用；
- 不同规则版本不得原位迁移。必须在同一固定输入上重放，记录 from/to rule bundle hash、迁移结果和 replay hash；不能重放时 `BLOCKED`。

## 4. E4_public 独立判定

### FR-EVT-002

`E4_public` 六项严格 AND：

1. `authorized_public_evidence`：审核合格且允许用于当前 scope 的公开证据；
2. `listed_company_ownership_path`：卖方法律主体到上市公司利润归属路径可核验；
3. `signed_or_formally_ordered`：合同已签署或订单已正式下达；
4. `effective_or_conditions_satisfied`：合同已生效，或全部实质性生效条件已完成；
5. `binding_minimum_obligation`：最低金额、最低数量或不可任意撤销义务至少一种可核验；
6. `minimum_not_zeroable`：取消、退货和验收条款不能把最低义务实质清零。

判定表：

- PIT、授权、输入身份、审计或规则 capability 失败：`BLOCKED`；
- 六项任一明确 `refuted`：`REJECT`；
- 六项任一 `unknown/conflicted`：`ABSTAIN`；
- 六项全部 `confirmed`，且至少一条授权权威原文直接支持签署/正式下达、生效和最低义务：`PASS`；
- CandidateEvent、公告标题、关键词、市场热度、预计份额、互动问答或调研记录不得单独升级 E4；
- 中标候选/结果/通知、框架协议、“以实际订单为准”或仍需另签合同，若构成强商业线索，只能进入 E3.5。

### 4.1 证据链与保密

- 一个权威原文足以建立 `E4` 事件候选；
- 是否具备至少两条独立公开证据链、其中至少一条权威原文，作为 `independent_gate_evidence_ready` 单独输出，留给四道门使用；不得把该条件偷塞进 E4 状态；
- 两条链必须有不同发布责任主体、不同 acquisition lineage，且不是同一原文的转述；
- 最低数量或不可撤销义务已确认、但金额/价格/收入确认节奏保密时，E4 仍可 PASS，同时 `economic_quantification=unknown`；后续利润门必须 `ABSTAIN`，不得补行业 ASP 或模型估值；
- 如果最低义务本身也无法核验，则 E4 为 `ABSTAIN`，不能用“合同存在”替代经济闭环。

## 5. 主体关联与最早合法公开事实

### FR-EVT-003

事件关联使用以下角色，不以名称相似度自动合并：

| 角色 | 含义 | E4 必需性 |
|---|---|---:|
| `listed_company` | 证券对应上市公司主体 | 必需 confirmed |
| `economic_beneficiary` | 承接利润的法律主体 | 必需 confirmed |
| `seller_supplier` | 合同卖方或供应商 | 必需 confirmed，可与 economic beneficiary 相同 |
| `customer_buyer` | 客户或买方法律主体 | 允许因合规保密显式 unknown |
| `procurement_actor` | 招标、采购或政府采购责任主体 | 适用时必需；不适用须显式 not_applicable |

每条 `party_link` 保存 `legal_entity_id`、角色、direct/indirect、所有权或交易关系、supporting/conflicting fact IDs、`lineage_group_ids` 和有效时点。卖方—上市公司归属冲突会使 E4 `ABSTAIN`；仅有间接产业关联不能证明合同主体或利润归属。

买方/采购主体因合法保密为 unknown 时，不自动否决已有权威合同的 E4，但 `cross_party_corroboration_ready=false`，不得伪造客户名称或第二条证据链。

### 5.1 最早合法公开事实

- 候选必须记录 `earliest_legal_public_fact_id` 和其 provider `available_at`；
- 只在授权公开、审核合格、`available_at <= knowledge_cutoff` 的事实中选择；
- 选择键固定为 `(available_at, fact_id)` 升序，以解决同一微秒并列；
- 声明值与确定性选择不一致、使用未来事实、非公开/MNPI、权限不清或缺失 provider `available_at`：`BLOCKED`；
- `event_at/source_published_at/first_seen_at/verified_at` 仅用于解释，不得替代 provider `available_at`；
- 同源后续转载不能把最早可用时间提前，也不能覆盖原事实。

## 6. Fact / Assumption / Derived / Judgment 分层

### FR-EVT-004

| 类型 | 必需字段 | 禁止事项 |
|---|---|---|
| `Fact` | provider fact ID、subject、predicate、value 引用、`available_at`、evidence IDs、input ref | 不由策略创建或改写；不包含场景、公式或策略结论 |
| `Assumption` | assumption ID、`as_of`、scenario ID、理由、依赖引用、至少一个可观察证伪条件 | 不冒充 Fact；未知事实不能无说明变成假设 |
| `Derived` | derived ID、formula ID/version、依赖 IDs、scenario、计算输入 hash、结果 hash、`as_of` | 不依赖 Judgment；不覆盖 Fact；禁止非确定性/隐藏默认值 |
| `Judgment` | judgment ID、rule ID/version/hash、结果、reason codes、Fact/Assumption/Derived 引用、`as_of` | 不作为 provider Fact，不反写 KB，不直接生成订单 |

### 6.1 依赖与时间

- 四类 ID 在单次 run 内全局唯一；同一 ID 不得跨类型复用；
- Assumption 可依赖 Fact/Assumption；Derived 只可依赖 Fact/Assumption/Derived；Judgment 可引用前三类；
- Derived 依赖图必须是有向无环图；环、缺失依赖、跨 run 隐式引用或依赖 Judgment 均 `BLOCKED`；
- Derived 的 `as_of` 不得早于任一依赖的可用/审阅时点；Judgment 的 `as_of` 不得早于其全部依赖；
- 所有对象保存创建者、版本、输入引用和 canonical hash；新版本通过 supersedes 追加，不原位覆盖；
- `writeback_to_kb=false`、`authorizes_positions=false`、`authorizes_orders=false` 为不可变边界。

### 6.2 冲突和证伪

- Fact 冲突保留双方 ID，不用策略对象覆盖 provider Fact；
- Assumption 的证伪触发器必须是可观察命题，不接受“长期看好”等不可检验文字；
- Derived 只报告公式结果，不把公式输出写成 Fact；
- Judgment 必须保留支持、反对、冲突和待核问题；没有支持证据的 Judgment 不得 PASS；
- 人工覆盖需要新 Judgment 和 approval reference，不能修改原对象。

## 7. 机器提案与批准门

draft machine bundle：

`机器制品/industrial_event_stage4_4a2_event_semantics_v0.1.0-draft.rule-bundle.json`

运行时不得解析 Markdown。当前 bundle 必须保持：

- `declared_status=draft`；
- 无 approval record；
- `allowed_run_modes=[]`；
- `runtime_capability_issued=false`；
- 全部 backtest/paper/shadow/live/positions/orders 权限为 false。

只有 owner 明确批准本文件第 8 节全部项目后，才可生成新的非 draft machine bundle、精确 approval record、四类业务测试和事件 evaluator。不能通过把 draft 文件改名、伪造 registry 或复用 Stage 2B/4A-1 capability 获得权限。

## 8. 待 owner 确认的 16 项

- [ ] 1. 同意 E0—E7/E3.5 使用第 3 节 evidence passport，不使用综合分数。
- [ ] 2. 同意 E1/E2/E3/E5 的同层事实使用 OR，E6 使用收入/增量利润/现金回收严格 AND。
- [ ] 3. 同意 E3.5 为“强商业线索 AND E4 `REJECT/ABSTAIN`”；E4 为 `BLOCKED` 时不产生事件状态。
- [ ] 4. 同意中间护照完整时可压缩跨级；护照缺失时 `ABSTAIN`，不制造伪顺序。
- [ ] 5. 同意 E7 四个终局子型及各自前置状态。
- [ ] 6. 同意 logical event、snapshot、revision、duplicate、supersedes 的 append-only 规则。
- [ ] 7. 同意明确反证可降级；缺失/不可恢复/冲突不能静默降级或沿用。
- [ ] 8. 同意规则版本迁移必须固定输入重放，不能原位改写。
- [ ] 9. 同意 E4 六项严格 AND 和 `BLOCKED > REJECT > ABSTAIN > PASS`。
- [ ] 10. 同意一个权威原文建立 E4 候选，两条独立链只作为后续 Gate readiness。
- [ ] 11. 同意最低数量/不可撤销义务已知但金额价格保密时 E4 PASS、利润门 ABSTAIN。
- [ ] 12. 同意五类 party role，以及买方合法保密不自动否决 E4、但不能形成跨主体确认。
- [ ] 13. 同意最早合法公开事实按 `(available_at, fact_id)` 确定性选择。
- [ ] 14. 同意同源转述共享 lineage，不增加独立证据且不提前 PIT。
- [ ] 15. 同意 Fact/Assumption/Derived/Judgment 的字段、依赖方向、DAG 和时间规则。
- [ ] 16. 确认批准范围仍仅为合成 `research / validation_only`，不授权 backtest、paper、shadow、live、仓位或订单。

## 9. 批准后的测试完成门

每条规则至少需要正例、反例、边界例和 `ABSTAIN`：

- E0—E7 全护照、压缩跨级、缺中间护照、降级、duplicate/revision、版本迁移；
- E4 六项逐项反证/未知/冲突、单权威候选、两链 readiness 和保密经济量；
- 主体直接/间接/保密/冲突、同源转述和最早公开事实并列边界；
- 四类知识合法依赖、跨类型 ID、DAG 环、时间倒置、Judgment→Derived 禁止和 KB writeback 禁止；
- 错误 scope/hash/status/authority 必须在 evaluator 前失败关闭。
