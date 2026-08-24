# Stage 6 最小历史公共数据消费契约草案 v0.1

状态：`draft_for_owner_confirmation / zero_runtime_authority`

形成日期：`2026-08-24`

形成基线：`7e294f2d48498d94c4c5063e23a144c606fe106f`

KB census 声明基线：分支 `codex/stage6-historical-census`，commit `857c86787ed46d34e4f4f17eefa4bbde78089d15`，结论 `NOT_READY`。该提交尚未推送，本轮只使用 owner 转述的状态，不读取 KB worktree、数据库、tmp 或制品，也不把声明计数当作 IS 独立验收证据。

## 1. 总体裁决

IS 接受 KB 当前 `NOT_READY` 结论：`scope-eligible Release=0 / artifact=0` 意味着当前不能开始真实 Stage 6 handoff、candidate census、coverage 或 historical run。

四个建议 Release family 的业务分层总体合理，但不能直接由一次 IS run 同时引用四个 root。ADR-0001 首版要求每次 run 恰好一个 `strategy_input_ref`，因此最终必须新增一个单一 root aggregate Release：

`historical-stage6-public-input-2019-2025.v1`

它的 Manifest/retention closure 内容寻址地引用全部 source-family Release、Schema 和 artifacts。source families 可独立构建、审核和发布，但 IS 正式候选投影只接受完整 root closure。

为降低 KB backfill、审核和 Release DAG 复杂度，建议把 `historical-common-reference-factors` 合并为 `historical-security-market-reference` 内的版本化 artifact group；首版保留三个 source families：

1. `historical-public-evidence-2019-2025.v1`
2. `historical-security-market-reference-2019-2025.v1`
3. `historical-public-financials-2019-2025.v1`

如果 KB 工程上必须独立刷新 factors，可以保留第四个 child Release，但不得让 IS 直接使用多个 strategy input refs，且 factor Release 必须精确依赖 market-reference raw basis。

## 2. Stage 6 最小 P0 数据域

以下全部是正式 candidate/readiness census 的 P0；任一缺失都不能通过 aggregate coverage 掩盖。

### P0-A：公共证据和历史 PIT

- Document、Span、Fact、CandidateEvent、EvidenceLink、EvidenceRef；
- economic/observed/available/knowledge times；
- correction、withdrawal、revision、supersedes lineage；
- Event→Company→Security 的有效期映射；
- conflict、counterexample、missing、unrecoverable 状态；
- 2019—2025 当时可见版本，禁止把后来采集的回顾性事实解释为 decision-time PIT。

### P0-B：历史证券主数据和 universe

- stable `company_id/security_id`；
- exchange、board、security type、listing/delisting dates；
- effective-dated ticker/name/code changes；
- ST/*ST、暂停上市、终止上市、失败和长期停牌历史；
- 证券与公司的有效期映射及 revision lineage；
- 明确保留后来退市、失败或被策略排除的证券，禁止 survivor-only。

首版正式 target universe 建议固定为 SSE/SZSE 普通人民币 A 股；基金、债券、优先股、B 股和其他品种不进入。BSE 是否进入首版由 owner 确认，推荐 deferred，以免在数据和 MarketRuleSet 尚未完整时扩大范围。

ST/*ST、新股、长期停牌等证券仍保留在基础 universe 和分母中，由 IS eligibility/support reason 排除或阻断；KB 不应提前删除。

### P0-C：市场参考与可成交性原始输入

- 每个交易所的完整交易日历和 session identity；
- effective-dated MarketRuleSet：tick、lot、price limits、T+1/settlement、board/risk-label rules；
- per-security/session SecuritySessionState：listed/eligible、suspended/resumed、one-price limit up/down、可证明对手方流动性；
- 2019—2025 未复权 OHLC/close、volume、turnover、observed/available time、source hash；
- broad-market benchmark 的同频 public marks/returns basis；
- 缺记录和被证明停牌必须区分，missing 不得自动补零；
- 一字板、涨跌停和停牌 mark 可以用于合法估值时，不得自动冒充 executable price。

### P0-D：公司行动和 total-return 基础

至少覆盖已批准 Stage 5D 的五类：

- cash dividend；
- share distribution；
- split/consolidation；
- rights/allotment；
- delisting/cash-out。

每项保存 announcement/record/ex/effective/recognized/paid/delivered/sellable/cash-available 中实际适用的时间、gross terms、ratio、currency、source 和 revision lineage。未知项显式 missing；不得只给事后复权价格。

KB 应发布 provider-neutral one-session total-return basis 或可精确重算该 return 的 raw action/mark closure；禁止使用依据未来公司行动构造的全样本 backward-adjusted price 作为 PIT 输入。

### P0-E：历史财务和策略事实原料

- Stage 4 Gate、利润桥、估值所需的历史公开财务报表/指标；
- report period、announcement/published/available times；
- restatement/revision lineage；
- currency/unit/accounting-standard identity；
- 不得用当前最新版财务覆盖历史 decision-time 版本。

仅策略未使用的扩展财务字段可后置；正式 Gate/利润桥承重字段不能后置。

### P0-F：peer reference 与通用因子

- PIT 一级行业；
- PIT 流通市值；
- ADV20 所需 turnover/calendar/session-state raw basis；
- Beta120 所需 security/benchmark one-session total returns；
- versioned `adv20` 和 `beta120` factor artifacts、公式、window identity、basis hashes、available_at 和 completeness status。

这些是通用市场参考因子，不包含 target/candidate/performance 信息，可以由 KB 发布。IS 必须验证其 raw-basis closure 并确定性抽样重算；factor artifact 不能替代 raw marks/calendar/actions/benchmark。

## 3. 可后置项

- tick/order-book 或完整 intraday 深度；首版已有 daily/verified-state 足以做支持 census，不能用于声称真实盘口成交；
- 20/120-session 非确认性 horizon 的预计算收益；IS 可从同一 daily basis 重放；
- 第二、三级行业分类和风格因子；
- BSE universe；
- 未命中候选/peer 的公司行动扩展字段，但 action type/存在性/PIT identity 仍为 P0；
- 与 Stage 4/5/6 承重规则无关的财务扩展指标；
- 分钟/tick benchmark Beta。

后置项命中候选时必须使该候选 `UNSUPPORTED/INDETERMINATE`，不得事后补数据或从分母删除。

## 4. ADV20 推荐口径

建议 KB 发布版本化 `adv20.v1`，IS 接受前独立复核：

- measure：CNY trading amount/turnover，不是 share volume；
- window：decision session 之前恰好 20 个 exchange sessions，不含 decision session；
- denominator：固定 20 sessions；
- 正常交易/涨跌停 session 使用实际 turnover；
- 全日停牌只有在 SecuritySessionState 明确证明时才记 `0` 并进入 20-session denominator；
- missing observation、未知状态、calendar gap 不得记零，factor 状态为 incomplete；
- factor `available_at=max(all basis available_at, calculation published_at)`；
- 保存 20 个 basis observation hashes、calendar/rule/state hashes、currency 和 formula version。

## 5. Beta120 推荐口径

建议 KB 发布版本化 `beta120.v1`，而不是让每个消费者自行选择 benchmark/复权方法：

- fixed benchmark：推荐全市场 total-return benchmark；优先选择可合法公开交付的中证全指全收益等宽基准，最终 ID 由 owner 确认；
- frequency：daily、同一 120-session calendar；
- window：decision session 之前恰好 120 个 exchange sessions，不含 decision session；
- estimator：带截距 OLS slope，等价于 paired return covariance / benchmark variance；
- returns：security 和 benchmark 的 PIT one-session total returns；
- company action：从未复权 marks + 当期有效 action terms 形成 one-session total return，禁止未来 backward adjustment；
- suspension：只有状态证明全日停牌、前后 mark lineage 完整时才允许 carry-forward 并产生零 return；未知/missing 不得填零；
- limit up/down：使用实际合法 close return，同时保留状态供执行层判断，不从 Beta window 删除；
- listing history 不足 120 pairs、benchmark variance 为零或任一 pair 不可证明时，`beta120` 为 incomplete，不外推、不缩短窗口；
- 保存 120 对 return/basis hashes、benchmark identity、calendar、formula、available_at 和 revision lineage。

## 6. Universe 与最低覆盖

### 数据交付硬门

- root/source Release、Manifest、Schema 和 dependency closure：`100%` identity verified；
- 2019—2025 exchange calendar 与 MarketRuleSet interval：`100%` session covered；
- in-scope security 的 listing/delisting/code/ST history：`100%` entity lifecycle identified；
- unknown/missing、退市、失败证券必须显式存在，不能通过 survivor universe 降低分母。

mark、state、action、financial 和 factor coverage 不使用一个高比例掩盖局部缺口；逐 security/session/candidate 保存 missing reason。真实候选形成后仍执行已批准门：

- aggregate candidate support `>=80%`；
- 每个 2022—2025 fold/year `>=70%`；
- material category coverage `>=60%`；
- target 和至少 5 个 selected peers 均须完整支持，否则候选 unsupported；
- 至少 30 个真实、可成交、已结束且完整对账交易，每 fold 至少 5 个；synthetic golden 不计数。

## 7. Release 架构裁决

### Root aggregate Release（新增，P0）

`historical-stage6-public-input-2019-2025.v1`

只在三个 source families 全部 published、PIT/Schema/closure producer validation 通过后发布。root Manifest 必须显式引用 source Release IDs、Manifest hashes、Schema artifacts 和所有承重 artifacts；撤回任一 source 必须使新 IS run fail closed。

### Source family 1：public evidence

保留独立：文档/证据/事件、entity links、PIT/revision/conflict。它与财务/market 的 grain、审核方式和 source lineage 不同，不建议合并。

### Source family 2：security market reference + common factors

合并原建议的第 2 和第 4 family，包含 security master/history、calendar、MarketRuleSet、SecuritySessionState、unadjusted marks、corporate actions、benchmark basis、ADV20/Beta120 factors。factor artifacts 必须绑定同 family 或精确 child raw Release closure。

### Source family 3：public financials

保留独立：财务数据量、period/restatement/available semantics 和审核节奏与证据/市场不同。

## 8. Schema 与 transport 建议

首批新增 artifact Schema 均从 `1.0.0` 开始，建议至少包括：

- `historical-public-evidence.v1`
- `company-security-history.v1`
- `trading-calendar.v1`
- `market-rule-set.v1`
- `security-session-state.v1`
- `unadjusted-market-daily.v1`
- `corporate-action.v1`
- `historical-public-financials.v1`
- `benchmark-total-return-daily.v1`
- `common-reference-factor.v1`（含 `adv20`/`beta120` typed variants）
- `historical-stage6-public-input-manifest.v1`

如果仍使用现有 Release/Manifest/Status/artifact endpoints、响应 envelope、认证和强制 headers，transport protocol 保持现有 v1，不为新增 artifact 类型升级 API v2。

KB 必须在一个新的 public-contract commit 中冻结 Schema bytes、catalog、official fixtures 和 producer validation。IS repin 时点固定为：

1. KB source families 和 root Release candidate 已物化；
2. 所有新 Schema/catalog/fixtures 已提交且 producer tests 通过；
3. 尚未签发真实 handoff Token、尚未开始 IS HTTP 验收；
4. IS 从该 exact KB commit 重建 vendor snapshot/catalog lock；
5. 若 transport envelope/endpoint/header/auth 语义未变，继续绑定 `aab36fe` transport implementation identity，同时新增 historical-contract commit/lock；
6. 只有 transport 语义改变才形成版本化 transport v2，并完整重跑 Stage 3A—3C 兼容验收。

## 9. Provider-neutral 最小消费契约草案

一次 IS run 只绑定一个 root `strategy_input_ref`。root closure 至少提供：

```text
Stage6HistoricalPublicInputContract
  schema_version
  contract_id / contract_hash
  strategy_input_ref
  root_release_id / root_manifest_hash / knowledge_cutoff
  transport_source_commit / historical_contract_commit / snapshot_lock
  source_releases[] = release_id / manifest_hash / status_event_hash
  artifacts[] = artifact_id / role / schema_version / bytes_hash / size / record_count
  domain_profiles[] = domain / grain / keys / date_range / required_nulls
                       duplicate_count / orphan_count / pit_result / lineage_result
  universe_identity = exchanges / security_types / effective-dated membership hash
  market_basis_identity = calendar / rule / state / mark / action / benchmark hashes
  factor_identity = ADV20/Beta120 formula/window/basis hashes
  financial_identity = statement/metric/restatement/PIT hashes
  declared_missing_items[] / unrecoverable_items[]
  contains_holdout_content = false
  contains_outcome_content = false
  authority_eligible = false
```

契约只允许进入 IS `HistoricalDataReadinessReport` 和 outcome-blind candidate inventory。不得携带 strategy candidate、support flag、returns summary、NAV/P&L、completed-trade count、coverage 或 champion 结果。

## 10. Blocker 优先级

1. `P0-ROOT-RELEASE`：没有单一 2019—2025 root Published Release/完整 closure。
2. `P0-PIT-LINEAGE`：主要域 `available_at`/历史 revision 可见性尚不可证明。
3. `P0-MARK-STATE-RULE`：未复权 marks、MarketRuleSet、SecuritySessionState 缺失。
4. `P0-SECURITY-LIFECYCLE`：survivor-only，缺退市/失败/ST/代码变化历史。
5. `P0-CORPORATE-ACTION`：公司行动事实和 total-return basis 缺失。
6. `P0-FINANCIAL-PIT`：回顾性财务不能冒充 decision-time PIT。
7. `P0-REFERENCE-FACTOR`：ADV20/Beta120 raw basis、benchmark、公式与 lineage 不完整。
8. `P1-COVERAGE-PROFILE`：各域实际 missing/duplicate/orphan/PIT coverage 尚未形成。
9. `P1-PRODUCER-VALIDATION`：新 Schema、fixtures、Release family 和 root producer validation 尚未完成。
10. `P1-IS-REPIN-HANDOFF`：尚无 exact public-contract commit、snapshot lock、handoff JSON 或 Token。

## 11. Owner 待确认问题

以下决定当前保持 `pending`，不得由实现者静默选择：

1. 首版 universe 是否批准仅 SSE/SZSE 普通 A 股，BSE deferred；
2. Beta benchmark 的精确公开 ID，推荐宽基 total-return benchmark；
3. Beta 是否批准 exactly 120 paired daily total returns + OLS slope，缺一不算；
4. ADV20 是否批准 previous 20 exchange sessions 的 CNY turnover mean，证明停牌才记零；
5. 是否批准 KB 同时发布 raw basis 与 versioned ADV20/Beta120，IS 抽样重算；
6. 是否批准将 common-reference-factors 合并进 security-market-reference family；
7. 是否批准新增单一 root aggregate Release 以满足一个 strategy_input_ref；
8. 公司行动 P0 是否采用 Stage 5D 五类完整事实范围；
9. entity/calendar/rule lifecycle 是否采用 100% identity coverage 硬门；
10. transport v1 保持不变、只有 artifact Schema/catalog 新增时不升级 API v2。

## 12. KB 下一轮最优实现顺序

1. 冻结 stable company/security identity 和完整 survivor/delist/ST/code-change universe；
2. backfill calendar、MarketRuleSet、SecuritySessionState、unadjusted marks 和 corporate actions，并建立 PIT/revision lineage；
3. 形成 benchmark one-session total-return basis，再生成可复核 ADV20/Beta120；
4. backfill evidence/event/entity links 和历史财务 available/restatement lineage；
5. 分别发布并验证三个 immutable source families；
6. 生成单一 root aggregate Release 与完整 producer validation；
7. 冻结新 public-contract commit/Schema/catalog/fixtures；
8. 由 IS 在真实 Token/handoff 前完成 repin；
9. 最后才生成 handoff JSON、producer report 和短期只读 Token。

本草案不修改 KB，不执行真实验收、候选、收益、coverage、统计或持久化，也不接触 2026 holdout。
