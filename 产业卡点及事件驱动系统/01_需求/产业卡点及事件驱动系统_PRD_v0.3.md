# 产业卡点及事件驱动系统 PRD v0.3

文档状态：`approved_requirements_baseline`

决策基础：`requirements_confirmed through 2026-07-22；repository boundary review and owner approval through 2026-07-31`

规则状态：`rule_spec_pending`

版本日期：`2026-07-30`

批准日期：`2026-07-31`

目标市场：`中国 A 股`

第一用户：`个人投资者 / PM，人工最终批准`

版本关系：`supersedes` [PRD v0.2](产业卡点及事件驱动系统_PRD_v0.2.md)；v0.2 仅作历史追溯

边界决策：[ADR-0001：InvestmentResearchKB 与 InvestSystem 边界及 Release 消费政策](../../docs/adr/ADR-0001-kb-investsystem-boundary.md)

研究边界：`2019—2026 历史回放；2024—2026 为 AI 驱动主验证期`

生产边界：`当前只允许研究、回测、paper/shadow；不得自动实盘`

> 本文是自包含的产品需求基线。它描述计划建设的能力，不代表这些能力已经实现，也不证明策略有效或承诺收益。只有 `03_规则与规格/` 中标记为 `approved` 且通过对应验证的规则，才可进入正式回测；任何 `hypothesis`、`draft`、`placeholder` 或 `TBD` 参数均禁止用于 live。

---

## 1. 产品裁决

本项目把产业研究框架改造成一套可证伪、可重放的策略与决策系统：

`经验证的 KB Published Release → StrategyRunManifest → 产业卡点 → 可投资受益公司 → E0—E7 → 四道门 → 利润桥与估值 → 可成交价格 → 决策与风险仓位 → 验证和退出`

系统不负责采集互联网信息或生产基础事实；它只消费 `InvestmentResearchKB` 发布的确定版本数据集，并在固定知识截面上形成策略判断。

系统输出以下决策状态之一：

- `RESEARCH`：值得继续研究，但未取得真实仓位资格。
- `SHADOW_ONLY`：只允许影子记录，不允许真实仓位。
- `TRADE_READY`：在当前证据、规则和可成交价格下通过全部门槛。
- `REJECT`：信息足够，但至少一道准入门确定未通过。
- `ABSTAIN`：关键事实、经济参数、预期或成交条件无法可靠判断。
- `BLOCKED`：触发输入验证、治理、合规、流动性或组合硬否决。

`E4` 只是首次获得真实仓位候选资格的必要条件之一，也是一次强制重新承保点。即使订单真实，若利润不重要、市场已定价或价格不可接受，仓位仍为零。

---

## 2. 两个项目的职责边界

### 2.1 InvestmentResearchKB 的唯一职责

`InvestmentResearchKB` 是独立的信息与证据平台，负责：

- 授权来源的信息采集、`raw`、`staging` 和修订血缘；
- PIT 时间、结构化 `Document / Evidence / Fact / CandidateEvent`；
- 事实审核、冲突处理、质量状态和撤回；
- `Context Pack`、Published Release、Release Manifest 和 Schema；
- 为消费者提供精确制品、哈希、版本和知识截止时间。

这些对象的权威定义、状态和发布生命周期只属于 KB。InvestSystem 不复制其采集管线，也不把策略判断写回 KB。

### 2.2 InvestSystem 的唯一职责

InvestSystem 是策略、决策、组合与执行验证系统，负责：

- 按精确 `dataset_release_id` 只读取得 Published Release；
- 独立校验 Release Manifest、制品哈希、Schema、Release 当前状态、制品可取得性和知识截止时间；
- 保存 `strategy_input_ref`、确定性 `ArtifactConsumptionReceipt`、append-only `ArtifactFetchObservation` / `ReleaseStatusObservation` 和完整 `StrategyRunManifest`；
- 基于已发布事实形成策略局部映射、E0—E7、四道门和证伪条件；
- 实现利润桥、市场预期、情景估值、Decision、目标组合、人工批准、paper/shadow、成交回放和 P&L；
- 保存每次通过、拒绝、回避和阻断的确定性重放证据。

### 2.3 硬禁止项

InvestSystem 不得：

1. 直接读取 KB 的 SQLite、`raw/`、`staging/`、内部缓存或工作目录；
2. 通过兄弟目录 `PYTHONPATH`、editable install、submodule、符号链接或内部 Python import 依赖 KB 实现；
3. 调用 KB 的内部 repository/service，绕过 Published Release 接口或导出面；
4. 修改、补写或撤回 KB 的 Document、Evidence、Fact、Context Pack 或 Release；
5. 把 E0—E7、Gate、利润桥、估值、仓位、执行或 P&L 逻辑写回 KB；
6. 使用 `latest` 或运行时漂移的非精确引用作为正式输入；
7. 要求 KB 为了让某个策略案例通过而制造、改写或选择事实。

唯一允许的跨项目影响是：当指定 Release 不存在、已撤回、Schema 不兼容或校验失败时，InvestSystem 的新运行必须失败关闭为 `BLOCKED`。两边的代码、环境、数据库、缓存、迁移、CI、发布和历史运行记录互不修改。

---

## 3. 北极星目标与资金约束

### 3.1 北极星

长期愿景是“从 10 万元到 1,000 万元”，但 100 倍目标不是产品验收指标。系统优先优化：

`长期生存概率 × 可重复优势 × 扣费后复利 × 扩容能力`

禁止用高杠杆、单票豪赌、未来信息、不可成交价格或回测调参代替真实优势。

### 3.2 已确认资金与风险边界

| 项目 | 已确认要求 |
|---|---|
| 初始资金基数 | 10 万元 |
| 最大可承受账户回撤 | 20%，属于生存上限而非操作触发点 |
| 追加资金 | 系统验证有效后最多追加 20 万元 |
| 杠杆与方向 | 首版不使用杠杆、融资融券或做空 |
| 交易品种 | 中国 A 股普通股；MVP 排除 ST/*ST、上市初期新股、长期停牌和无法可靠成交证券 |
| 下单权限 | 人工最终批准；研究 Agent 不得持有券商凭证或提交订单 |
| 持有逻辑 | 中低频事件交易，以可验证催化点为时钟，最长验证窗口暂定 120 个交易日 |

20% 不能用作单笔止损或单笔风险预算。系统必须在达到该上限前分层降险和停机。

---

## 4. 状态、权威与版本治理

### 4.1 状态含义

| 标签 | 含义 | 能否进入 live |
|---|---|---:|
| `requirements_confirmed` | 用户已经确认的产品需求 | 否 |
| `hypothesis` | 需通过历史与前瞻验证的数值或方法 | 否 |
| `draft` | 尚未完成规格化或评审 | 否 |
| `placeholder` | 仅占位，不能成为实现默认值 | 否 |
| `TBD` | 缺少必要选择或数据 | 否 |
| `approved` | 规则经评审并满足进入对应验证的前置条件 | 仅可进入对应验证阶段 |

`approved` 不等于已证明有效，也不等于允许 live。

### 4.2 权威层级

1. `原始文档/` 和历史归档是不可变来源与设想记录，不是可执行规格；
2. `01_需求/` 定义产品目标、边界和验收；
3. `03_规则与规格/` 中 `approved` 的版本化规则定义可执行语义；
4. `contracts/`、配置和代码必须实现已批准规格，不得自行补全业务决策；
5. `06_测试与验证/` 和运行 Manifest 证明具体版本是否通过验证；
6. 文档描述不得冒充已实现、已测试或已投产能力。

### 4.3 版本纪律

- 需求、输入契约、事件定义、数据投影、门槛、成交模型和退出规则分别版本化。
- 修改任何影响准入、仓位或退出的规则，必须升级策略版本并重跑受影响验证。
- KB Release 不可被 InvestSystem 覆盖；策略判断修订通过新的 run 和 `supersedes` 关系留痕。
- 不得因样本少或回测不理想而静默放宽 E4、利润门槛或成交约束。
- 一次正式 run 必须固定代码提交、规则版本、配置哈希、输入引用和随机种子。

---

## 5. KB Release 消费契约

### 5.1 五字段 `strategy_input_ref`

首版每次 run 必须且只能绑定一个符合 KB `strategy-input-ref.v1` 的输入引用。多 Release 聚合不在当前契约内，必须另行批准 ADR、版本化契约、规范排序与哈希规则并重新验证。

~~~json
{
  "schema_version": "1.0.0",
  "dataset_release_id": "rel_example_001",
  "knowledge_cutoff": "2026-07-30T08:00:00.000000Z",
  "release_manifest_schema_version": "1.0.0",
  "manifest_hash": {
    "algorithm": "sha256",
    "value": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  }
}
~~~

语义约束：

- `dataset_release_id` 必须是确切 ID，禁止 `latest`；
- `knowledge_cutoff` 是该输入可用于策略判断的知识截止时间，不得由运行时当前时间替代；
- `release_manifest_schema_version` 必须在 InvestSystem 明确支持的版本集合内；
- `manifest_hash` 是 `{algorithm, value}` 对象，不是裸字符串；首版只接受小写十六进制 `sha256`；
- 五字段必须原样保存，不得只保留 `context_pack_version`、路径或下载时间。

### 5.2 确定性消费回执与观察记录

InvestSystem 为每个经验证的精确 Release 生成内容确定的 `ArtifactConsumptionReceipt`。首版字段与 KB 公共参考消费者对齐，至少记录：

~~~text
schema_version
consumer_contract_version
strategy_input_ref
artifacts[] = {artifact_id, item_type, artifact_hash, size_bytes, record_count}
receipt_hash
~~~

`artifacts` 必须按 `artifact_id` 排序；所有哈希使用 `{algorithm, value}` 对象，`receipt_hash` 对排除 `receipt_hash` 字段自身后的规范化 receipt 计算。相同 Release 内容与 consumer contract 必须生成相同 receipt；同一 `dataset_release_id` 若生成不同内容，必须报幂等冲突。

获取时间、端点、传输字节和当前状态属于易变观察，不得进入确定性 receipt identity。每次动作另写 append-only 记录：

~~~text
ArtifactFetchObservation = {observation_id, release_id, observed_at, transport,
  source_endpoint, response_or_export_bytes_hash?, schema_validation_result,
  failure_reasons, local_cache_keys, supersedes}
ReleaseStatusObservation = {observation_id, release_id, observed_at, status,
  status_event_id, status_event_hash, authorization_result,
  failure_reasons, supersedes}
~~~

HTTP `/manifest` 返回 API envelope 中的 Manifest 对象，不等同于 sealed `manifest.json` 文件字节；只有传输面实际提供 sealed export 时才记录可选的 export 物理字节哈希。HTTP response 或 export 字节哈希都只是传输观察，不参与语义 `manifest_hash` 或确定性 receipt identity。receipt 与 observations 均属于 InvestSystem，不得修改或替代 KB Manifest 和状态事件。

StrategyRunManifest 必须引用本次启动所用的 `ArtifactFetchObservation` 与 `ReleaseStatusObservation` ID 以供审计，但 observation 的时间、端点和 ID 不进入策略的确定性 `replay_hash`。`replay_hash` 只覆盖已验证内容身份、规则、代码、配置、参数、注入时钟和随机种子；因此重复获取可以新增 observations，同时保持 receipt 和策略结果幂等。

### 5.3 消费步骤与失败关闭

1. 通过版本化只读 HTTP API 或授权的不可变导出包，按精确 `dataset_release_id` 取得 Release 与 Manifest，并核对二者身份、发布状态和引用关系；
2. 校验 Manifest Schema 版本、必填字段和 `manifest_hash` 对象结构；
3. 严格按 KB 公共契约，对排除 `manifest_hash` 字段自身后的不可变 Manifest 做规范化序列化并重算语义 `manifest_hash`，再与声明值和 `strategy_input_ref` 比较；
4. 保存用于验证的规范化 Manifest 快照及语义哈希；若传输面提供 HTTP response 或 sealed export 字节，可在 `ArtifactFetchObservation` 中另记可选物理字节哈希，但不得把它误当语义 `manifest_hash`；
5. 按 Manifest 中的精确 `artifact_id` 获取制品；
6. 校验每个制品的字节哈希、Schema 和声明的知识边界；
7. 检查 Release 的当前追加式状态事件，并确认精确制品可按 Release、授权和法律状态取得；不得创造公共契约中不存在的 artifact-level withdrawn 状态；
8. 将已验证字节复制到 InvestSystem 自有 `var/cache/kb-releases/` 内容寻址缓存；缓存软上限为 `20 GiB`，不得自动删除被历史 run 或审计记录引用的制品；
9. 写入确定性 receipt 和 append-only `ArtifactFetchObservation` / `ReleaseStatusObservation`，再建立 `StrategyRunManifest`；
10. 只有全部 P0 校验通过，策略引擎才可读取投影后的 provider-neutral DTO。

出现以下任一情况，新运行必须 `BLOCKED`：

- Release 或精确制品不存在，Release 已撤回或无法确认当前状态，或精确制品因 Release/授权/法律状态被拒绝；
- Manifest/制品哈希不匹配；
- Schema 未锁定、不受支持或验证失败；
- `knowledge_cutoff` 晚于 run 的允许知识截止时间；
- 关键制品缺失、内容冲突未处理或 receipt 不完整；
- 代码尝试访问 KB 内部路径、数据库或实现模块。

历史 run 的输入字节、receipt 和结果保留用于审计；撤回会阻断全部新 run，不得悄悄改写历史结果。撤回后的固定材料只允许标记为 `audit_replay` 的历史审计重放，不得生成新的当前判断、仓位、批准、订单或 paper/live 行为。

### 5.4 Fixture 政策

测试 fixture 分三类：

1. **KB 官方契约 fixture**：原始字节保持不可变，用于验证 Schema、哈希、published 状态、游标、下载和幂等，不预设策略结论；当前官方 fixture 不被表述为已覆盖撤回负例；
2. **InvestSystem 自有合成策略 fixture**：覆盖 `TRADE_READY / SHADOW_ONLY / REJECT / ABSTAIN`，仅验证已批准的策略语义；
3. **失败注入 fixture**：从确定输入构造 Manifest/制品篡改、撤回、不兼容 Schema、缺失制品和未来信息等故障，仅验证严格失败关闭。

KB 正式 Published Release/Context Pack 不属于 fixture，只用于真实只读 smoke/E2E；结论由事实自然决定，允许并应预期出现 `ABSTAIN`。

不得推动 KB 为策略正例定制事实，也不得把合成 fixture 伪装为真实 Release 或研究证据。

---

## 6. 首个产业切片与历史分期

首个独立研究切片为：

> `AI 算力基础设施—高速光互连产业链`

历史样本必须按当时产业语义分期，不得用 2026 年产业地图回填历史：

| 时期 | 历史标签 | 用途 |
|---|---|---|
| 2017—2018 | 标准与技术背景 | 不计入交易样本 |
| 2019—2020 | `cloud_dc_100g_400g_transition` | 云数据中心、100G/400G 升级的反事实样本 |
| 2021—2022 | `400g_scale_800g_qualification` | 400G 规模化、800G 认证与早期交付 |
| 2023 | `genai_network_inflection` | 单列为生成式 AI 网络需求转折期 |
| 2024—2026 | `AI-driven optical demand` | 当前主要验证期，尚未覆盖完整下行周期 |

详细历史证据见[高速光互连产业历史可回溯性核查 v0.1](../02_研究/高速光互连产业历史可回溯性核查_v0.1.md)。该核查证明产业和公开资料可以回溯，不证明卡点或策略 Alpha 成立。

第一条最小纵向切片聚焦“订单/合同及其前置公开事件”，但正式 KB Release 不保证存在可过门正例。没有满足 E4 的事实时，正确结果是 `SHADOW_ONLY`、`REJECT`、`ABSTAIN` 或 `BLOCKED`，而不是修改输入。

---

## 7. 产业上下文与决策池

### 7.1 上下文来源

产业事实、来源、证据图和 Context Pack 由 KB 生产、审核和发布。InvestSystem 不再自行采集或归档原文，只能：

- 验证 Published Release 中 Context Pack 和事实投影的完整性；
- 保存其 ID、版本、证据引用和五字段输入引用；
- 在策略命名空间内建立可重放的 `IndustryContextView`；
- 对事实适用性、卡点、受益路径和交易含义作策略判断。

`IndustryContextView` 是某次 run 的派生视图，不是新的权威 Fact，也不能回写 KB。

### 7.2 最低上下文覆盖

允许公司进入 `decision_pool` 前，指定 Release 应至少提供或明确标记未知：

1. 产品、技术代际、关键指标和产业术语；
2. 产品—部件—设备—材料—供应商—客户—替代路线关系；
3. 需求来源、采购模式、部署节奏和领先指标；
4. 认证、送样、定点、中标、扩产、量产、交付和验收周期；
5. 产能、良率、交期、价格、成本和库存的可得事实；
6. 竞争格局、客户集中度、切换成本和潜在新供给；
7. 产业利润池和上市公司归属链条所需事实；
8. 历史阶段、反例、不可恢复字段和冲突；
9. 来源、发布时间、可用时间、版本、置信度和审核状态；
10. 公司标识、排除理由及下一复核触发器所需事实。

缺失不得由 LLM、行业均值或后见信息补写。缺失会进入 `UNKNOWN/ABSTAIN`，或因 P0 输入不足而 `BLOCKED`。

### 7.3 决策池

- 全 A 股可用于 `discovery_radar`，但发现本身由 KB 发布的 CandidateEvent/事实驱动；
- 只有预注册、拥有当时版本 Context Pack 的公司进入 `decision_pool`；
- 池外候选进入 InvestSystem 的 `research_quarantine`；补齐后只能按最新可成交价格重跑四道门，禁止按原事件价格回填；
- `research_quarantine` 只保存策略处理状态和输入引用，不保存或修改 KB 原始证据。

---

## 8. 从产业节点到可投资公司

### 8.1 产业卡点门

产业节点必须同时回答：

- 需求是否可核验，而非只有市场空间故事；
- 供给响应是否因认证、设备、工艺、良率、牌照或客户切换而变慢；
- 替代路线是否真实受限；
- 稀缺是否可能持续到下一验证窗口；
- 瓶颈消失的领先信号是什么。

这些结论属于 InvestSystem 的策略判断，必须引用 Release 中的 Fact/Evidence ID，并保存规则版本和反例。

### 8.2 可投资卡点门

产业卡点成立后，还必须证明稀缺利润能归属于目标上市公司：

| 层级 | 定义 | 投资资格 |
|---|---|---:|
| `technical_link` | 技术或产品与节点相关 | 无 |
| `qualified_supplier` | 已进入认证、定点、供应商或交付体系 | 仅研究 |
| `profit_beneficiary` | 份额、价格、增量毛利、现金回收和所有权路径可核验 | 才可进入四道门 |

产业位置、供应商资格或收入增长均不能单独证明股东利润增加。关键字段未知时输出 `UNKNOWN`，不得由实现或模型补写。

---

## 9. 商业事件状态机

首版真实仓位准入只由 `E4_public` 启动。业绩预告、认证、扩产、供需和价格信息可以更新 E0—E3、E5/E6 研究状态，但不能在 E4 前独立产生真实仓位。未来增加其他入场路径，必须建立独立规则版本并重新验证。

### 9.1 E0—E7

| 状态 | 最低含义 | 允许动作 |
|---|---|---|
| `E0` | 产业需求或技术叙事，尚无公司级商业验证 | 观察 |
| `E1` | 产品研发、样品、标准或技术可行性证据 | 观察 |
| `E2` | 客户测试、认证、定点或供应商资格 | 研究 |
| `E3` | 招标、采购意向、框架、预计份额或商业谈判 | 研究、影子准备 |
| `E3.5` | 中标候选/结果/通知等强商业线索，但最低经济义务或生效条件未闭合 | 只允许 paper/shadow |
| `E4` | 已生效且存在可核验最低经济义务的订单或合同 | 首次获得真实仓位候选资格 |
| `E5` | 实际交付、验收或可核验履约进展 | 可重估、持有、加减仓或退出 |
| `E6` | 收入、增量利润和现金回收得到财务验证 | 可重估或转为基本面仓位 |
| `E7` | 复购/规模化、周期成熟、合同终止或论点完成 | 持有、退出或结束跟踪 |

KB 的 `CandidateEvent` 是事实候选，不等于 InvestSystem 的 E 状态。E0—E7 必须由策略版本在固定 Release 上派生并记录 `supporting_fact_ids`。

### 9.2 事件状态与持仓状态分离

- `E0—E3` 的真实仓位恒为零；
- `E3.5` 只能进行影子交易；
- `E4` 只代表接受四道门审查，实际仓位仍可为零；
- `E5—E7` 不自动加仓，任何动作都需重新估值和风险审批。

持仓使用独立状态：

| 持仓状态 | 含义 |
|---|---|
| `FLAT` | 实际仓位为零，包括研究、影子、拒绝和等待 |
| `STARTER` | E4 后通过四道门形成的风险受限初始仓 |
| `CORE` | E5/E6 新证据确认后重新审批的持仓 |
| `TRIM` | 因价值兑现、风险或证据减弱而进入减仓 |
| `EXIT` | 目标仓位归零，等待实际成交和对账完成 |

### 9.3 E4_public 正式定义

`E4_public` 必须同时满足：

1. 引用 KB Release 中审核状态合格的授权公开证据；
2. 法律主体和上市公司归属关系可核验；
3. 合同/订单已经签署或正式下达；
4. 已经生效，或实质性生效条件均已完成；
5. 存在可核验的最低金额、数量或不可任意撤销的经济义务；
6. 取消、退货、验收等条款没有把最低义务实质清零。

`公告 ≠ E4`，`无公告 ≠ 无 E4`。中标公示、框架协议、“以实际订单为准”或仍需签署合同的材料最多进入 `E3.5`。

若事实足以确认 E4 已发生，但金额、价格或最低数量因保密无法核验，可记录“事件成立”；利润门为 `UNKNOWN`，结论必须为 `ABSTAIN`。一个权威合同可以建立 E4 候选；进入 `TRADE_READY` 仍需至少两条独立公开证据链，其中至少一条为权威原文。同一材料的重复转述不构成第二条证据。

---

## 10. PIT 时间、证据引用与合规

### 10.1 时间字段

InvestSystem 消费 KB 已发布的 PIT 字段，至少使用：

~~~text
event_at
source_published_at
first_seen_at
verified_at
available_at
~~~

`available_at` 是 KB 按版本化 `AvailabilityPolicy` 计算并发布的最早消费者可见时间。InvestSystem 必须原样保留并将其作为提供方 PIT 权威值，不得在策略侧用其他原始时间重新计算、提前或改写；`event_at`、`source_published_at`、`first_seen_at` 和 `verified_at` 仅用于解释、审计和按获批规则判断时间质量。

每条被策略使用的知识至少满足：

`available_at <= strategy_input_ref.knowledge_cutoff <= decision_at`

若 InvestSystem 的获批流程另有策略复核时点，则只可增加消费者侧约束：

`strategy_usable_at = max(available_at, strategy_reviewed_at)` 且 `strategy_usable_at <= decision_at`

`strategy_usable_at` 是策略运行元数据，不是新的 KB 事实时间。日期精度不足、时间质量过低或缺少 `available_at` 时，按已批准规则 `ABSTAIN` 或 `BLOCKED`，不得在策略侧自行假定“下一交易日可用”。事实更正和补充通过新的 superseding KB Release 进入新的 run；撤回则通过原 `release_id` 上 append-only Release 状态事件阻断新 run，不修改原 Manifest，也不要求创建新 Release。任何变化都不得回溯修改旧决策。

### 10.2 合规边界

- 真实仓位资格只使用 Published Release 中授权公开信息；
- 疑似 MNPI、权限不清或审核未完成的数据不得进入可交易 run；
- 聚合器、研报和媒体可作为 KB 已发布事实中的线索或预期来源，但不能在策略侧绕过 KB 直接抓取；
- 研究 Agent 无券商凭证、KB 写权限或自由文本下单权限。

---

## 11. 决策漏斗与四道门

所有候选逐层计数：

`KB CandidateEvent/Fact → E3/E3.5 → E4_public → 关键字段完整 → Gate 1—4 → 实际可成交 → 独立完整交易`

每层同时记录通过、拒绝、`ABSTAIN`、`BLOCKED` 和缺失原因，避免只统计最终赢家。

| Gate | 问题 | 失败结果 |
|---|---|---|
| Gate 1：真实性 | 是否为真实、已生效、最低义务可核验的 E4_public | `REJECT/ABSTAIN/BLOCKED` |
| Gate 2：利润重要性 | 对未来 12 个月归母标准化利润和自由现金流是否足够重要 | `REJECT/ABSTAIN/SHADOW_ONLY` |
| Gate 3：预期差 | 此新增经济信息是否尚未被市场充分定价 | `fully_priced→REJECT；unknown→ABSTAIN` |
| Gate 4：可成交收益 | 首次真实可成交价格下是否仍有足够净收益和赔率 | `REJECT/ABSTAIN` |

只有四门同时通过才能进入 `TRADE_READY`。Gate 不得用加权总分相互补偿。Gate 1—2 形成公司/事件论点，Gate 3—4 形成股票论点，两者分别保存。每个 `TRADE_READY` 至少登记两个可观察证伪条件及 proof window。

---

## 12. Gate 2：利润重要性与情景

### 12.1 NTM 利润与现金流桥

每个情景使用同一传导链：

`NTM 归母增量利润 = NTM 可确认收入 × 增量毛利率 − 增量费用 − 税费 − 少数股东损益`

`NTM 增量自由现金流 = 增量利润 + 非现金项 − 增量营运资金 − 增量资本开支`

关键输入至少包括合同义务、交付节奏、验收、实际价格、增量毛利率、良率/利用率、费用、资本开支、回款、税率和归属比例。合同金额、收入占比或历史综合毛利率只能用于筛选，不能替代利润桥。

### 12.2 10% 正式分母

`利润重要性 = E4 基准情景 NTM 归母标准化增量利润 ÷ E4 前反事实 NTM 归母标准化利润`

分母必须是：

- 截至 E4 首次公开时点，仅使用当时可用且在 Release 截面内的信息；
- 假设事件未发生时的未来 12 个月归母标准化利润；
- 剔除资产处置、补贴、公允价值变动等非经常性项目；
- 由公司级利润桥建立，一致预期只作交叉验证；
- TTM 只作参考，不直接替代反事实 NTM。

无法可靠建立分母时为 `ABSTAIN`。

### 12.3 情景定义

| 情景 | 定义 | 约束 |
|---|---|---|
| 基准 | 当前公开证据下概率最大的执行路径 | 不是上下行情景机械中点 |
| 下行 | 有合同、历史或产业依据的合理不利路径 | 不得为了过门美化 |
| 上行 | 需要明确触发器才能实现的积极路径 | 无约束力复购不得提前计入 |
| 压力 | 极端但现实的资本损失/流动性路径 | 用于仓位和停机，不替代下行 |

每个关键假设保存：

`source_fact_ids｜as_of｜base｜downside｜upside｜trigger｜falsifier｜confidence`

三情景改变少数承重变量并保持经济关系一致。不得对每个变量独立挑选最有利数值。

### 12.4 通过规则

- 基准情景利润重要性达到 `10% [hypothesis]`；完整但低于门槛时为 `REJECT`；
- 只有上行情景达到 10% 时不得通过；
- 下行情景不强制达到 10%，但必须量化并进入仓位与退出判断；
- 概率加权不能稀释 Gate 2；
- 关键经济字段缺失时不得用行业平均或 LLM 推断，直接 `ABSTAIN`。

首版 `standard_track` 要求反事实 NTM 标准化利润为正且稳健。利润为负、接近零或易翻正/翻负的公司进入 `fragile_profit_shadow_track`，只建立增量毛利、现金流和融资需求模型，不取得真实仓位资格。

### 12.5 概率使用

首版不强迫为信息不足的情景赋予精确概率。只有当概率有历史基准、来源和校准方法时，Gate 4 才可显示概率加权结果；一旦使用，互斥情景概率必须合计 100%。主准入仍由基准收益和下行赔率决定。

---

## 13. Gate 3：重建市场预期

E4 按首次公开前的 PIT 信息分类：

| 分类 | 含义 | 是否进入 Gate 4 |
|---|---|---:|
| `unexpected` | 业务、金额、客户、期限或经济义务显著超出公开预期 | 是 |
| `partially_priced` | 市场预期有订单，但最低义务或利润贡献更高 | 是 |
| `fully_priced` | 此前公开材料和价格已反映相近经济结果 | 否 |
| `unknown` | 无法可靠重建先验预期 | `ABSTAIN` |

预期重建至少使用指定 Release 中 E4 前公告、公司指引、当时研究预期、相对异常收益与成交量，以及 E4 新增的信息量。E4 后上涨不能反证此前已定价，但会抬高成交价格，必须在 Gate 4 重算剩余收益。

---

## 14. Gate 4：价值、赔率与验证时钟

### 14.1 估值方法

`情景价值 = 未包含 E4 的基础业务价值 + E4 有限期增量自由现金流现值`

- 基础业务使用 E4 时点可得的标准化盈利和保守估值；
- 单次订单只按可执行期限计入，不赋予无证据永续价值；
- Gate 2 只使用 NTM；Gate 4 只有在最低义务、金额和时间具有合同约束力时，才可折现计入 NTM 以后有限期现金流；
- 复购只有在公开且有约束力后才进入基准，否则只属于上行情景；
- 基准情景不加入概念热度或无依据估值扩张；
- 禁止把订单利润和“新业务估值”重复计价；
- 基础业务或增量现金流不可可靠估计时为 `ABSTAIN`。

### 14.2 首次可成交价格

`剩余收益空间 = 基准情景价值 ÷ 首次实际可成交价格 − 1`

以下为 `hypothesis`：

- 扣除费用和滑点后，基准剩余收益空间 `≥15%`；
- `基准收益空间 ÷ |下行情景损失| ≥2`；
- 买入前登记下一个公开可验证催化点；
- 最长验证窗口 `120 个交易日`；
- 只有上行情景满足收益门槛时不得买入。

---

## 15. 成交与回测真实性

`decision_time = 知识可用时间 + InvestSystem 处理/核验延迟`

- 收盘后事件最早在下一交易日成交；
- 盘中事件只有在精确时间戳和分钟数据可靠时才允许盘中模拟，否则顺延；
- 一字涨停、无卖盘、停牌或成交量不足均视为不可成交；
- 首次恢复可成交时重跑 Gate 3 和 Gate 4；
- 连续 `3 个交易日 [hypothesis]` 仍不能成交，放弃信号；
- 优先使用可成交窗口 VWAP 并加入佣金、税费、滑点和冲击；
- 只有日线时使用下一交易日 VWAP，并标记低精度；
- 禁止在开盘、最低或收盘价格中事后择优；
- 模拟订单不超过对应窗口成交金额的 `5% [hypothesis]`；
- A 股 T+1、涨跌停、停牌、最小一手、公司行动和历史费用按生效版本回放。

若 100 股最小订单已超过风险允许仓位，交易必须跳过。

---

## 16. 仓位与组合风险

### 16.1 E4 初始仓位

`initial_position_value = min（账户净值 × 0.5% ÷ 压力损失率，账户净值 × 5%，流动性容量金额，风险簇剩余容量金额，组合剩余容量金额）`

其中：

- `0.5%` 为单笔账户计划损失预算；
- 压力损失率至少按 `10%` 计算；
- 所有约束先换算为人民币仓位金额，禁止直接比较异构单位；
- E4 首次权重不超过 `5%`；
- 只有 E5/E6 新证据增强并重新通过估值与风险门，才可加仓；
- 单一公司总权重不超过 `10%`；
- 跳空和跌停超额损失必须记录。

以上数值均为 `hypothesis`。

### 16.2 风险簇与市场状态

| 约束 | 首版假设 |
|---|---:|
| 同一产业/客户/产品价格/政策催化风险簇的计划损失 | ≤1.5% NAV |
| 同一风险簇市值权重 | ≤20% NAV |
| 全部未平仓交易计划损失 | ≤4% NAV |
| 单一公司总权重 | ≤10% NAV |

行业分类不同但依赖同一客户、产品价格或政策结果的持仓仍属同一风险簇。

| 市场状态 | 动作 |
|---|---|
| `NORMAL` | 单笔风险预算可用 0.5% |
| `DEFENSIVE` | 单笔风险降至 0.25%，禁止追加 |
| `CRISIS` | 暂停全部新真实仓位，只保留研究和影子信号 |

具体指标与阈值是 `hypothesis/TBD`，必须预注册和回测。市场状态只调整风险，不改变 E4 真实性或四道门。

### 16.3 回撤停机

| 回撤 | 强制动作 |
|---:|---|
| 8% | 新交易风险由 0.5% 降至 0.25% |
| 12% | 暂停新开仓，只处理已有持仓 |
| 15% | 停止真实运行、按可成交条件退出并强制复盘 |
| 20% | 生存上限，不得作为等待触发线 |

`8%/12%/15%` 是运营 `hypothesis`；`20%` 是用户确认的生存硬约束。恢复必须有书面归因、规则检查和人工批准。

---

## 17. 退出与重新承保

任一条件满足即可触发动作：

1. `evidence_exit`：合同取消、验收失败、显著延期、价格/数量下调、客户信用恶化或利润桥失效；
2. `risk_budget_exit`：单笔实际亏损达到建仓时登记的账户损失预算；
3. `time_exit`：120 个交易日内没有预登记验证事件，不得临时更换催化点；
4. `value_exit`：价格达到或超过当前基准价值，若无 E5/E6 新证据提升价值则退出。

继续持有前必须回答：“如果现在没有仓位，是否会在当前价格重新买入？”价格上涨不能自动提高估值，价格下跌不能降低事实门槛。

---

## 18. InvestSystem 自有对象与审计

### 18.1 对象所有权

| 对象 | 权威项目 | InvestSystem 可做什么 |
|---|---|---|
| Document / Evidence / Fact / CandidateEvent | KB | 只读引用已发布 ID 和字段 |
| Context Pack / Release / Release Manifest | KB | 下载、验证、缓存不可变字节 |
| `strategy_input_ref` | KB 定义公共子契约 | 在 run 中原样保存 |
| ArtifactConsumptionReceipt | InvestSystem | 确定性固定已接受的精确内容和消费者契约 |
| ArtifactFetchObservation / ReleaseStatusObservation | InvestSystem | 追加记录传输、状态和授权观察，不改变 receipt identity |
| StrategyRunManifest | InvestSystem | 固定输入、代码、规则、配置和运行身份 |
| IndustryContextView / StrategyEvent E0—E7 | InvestSystem | 在固定输入上派生策略语义 |
| GateResult / ProfitBridge / Expectation / Valuation | InvestSystem | 形成可解释判断 |
| DecisionRecord / TargetPortfolio / ApprovalRecord | InvestSystem | 决策、风控和人工批准 |
| ExecutionReplay / PositionLedger / P&L | InvestSystem | 回测、paper/shadow 和对账 |

### 18.2 StrategyRunManifest 最小字段

~~~json
{
  "strategy_run_manifest_schema_version": "TBD",
  "run_id": "...",
  "created_at": "...",
  "strategy_id": "industrial_bottleneck_event",
  "strategy_version": "...",
  "code_commit": "...",
  "rule_bundle_version": "...",
  "config_hash": {"algorithm": "sha256", "value": "..."},
  "strategy_input_ref": {
    "schema_version": "1.0.0",
    "dataset_release_id": "rel_example_001",
    "knowledge_cutoff": "2026-07-30T08:00:00.000000Z",
    "release_manifest_schema_version": "1.0.0",
    "manifest_hash": {"algorithm": "sha256", "value": "..."}
  },
  "artifact_consumption_receipt_hash": {"algorithm": "sha256", "value": "..."},
  "artifact_fetch_observation_id": "...",
  "release_status_observation_id": "...",
  "random_seed": 0,
  "run_mode": "research|backtest|paper|shadow",
  "runtime_environment_lock_hash": {"algorithm": "sha256", "value": "..."}
}
~~~

### 18.3 DecisionRecord 最小字段

~~~text
decision_id, run_id, decision_at, strategy_input_ref,
strategy_version, event_state, decision_state, position_state,
supporting_fact_ids, conflicting_fact_ids,
gate_results, facts_used, assumptions, judgments,
profit_bridge, scenarios, expectation_class,
first_executable_at, first_executable_price, execution_window,
price_method, estimated_cost_rate, estimated_slippage_rate,
market_regime, risk_cluster_ids, planned_account_risk,
risk_limits, target_weight, approved_weight, actual_weight,
falsifiers, next_verification, block_reasons,
approver, supersedes, replay_hash
~~~

`target_weight`、`approved_weight` 和 `actual_weight` 不得互相覆盖；事件、决策和持仓状态分别变化并分别留痕。

### 18.4 不可变审计要求

系统必须保存：

- 输入的规范化 Manifest 快照、制品字节/哈希、确定性 receipt、`ArtifactFetchObservation` / `ReleaseStatusObservation` 和五字段引用；
- 所有通过、拒绝、`ABSTAIN` 和 `BLOCKED` 候选；
- 理论信号、实际可成交价格、模拟成交、费用、滑点和退出；
- 规则版本、参数、代码、环境锁、人工覆盖与批准；
- 失败实验、被否决样本和无法成交样本。

这些是 InvestSystem 的消费与运行审计，不复制 KB 的 raw/staging 数据库。

---

## 19. 功能需求

### 19.1 KB 输入与隔离

| ID | 优先级 | 需求 | 验收 |
|---|---|---|---|
| FR-KB-001 | P0 | 按精确 ID 消费 Published Release | `latest`、本地 KB 路径和内部 import 全部被拒绝 |
| FR-KB-002 | P0 | 校验五字段输入引用、Manifest 和全部所需制品 | 哈希、Schema、截止时间任一失败均 `BLOCKED` |
| FR-KB-003 | P0 | 生成确定性 receipt、append-only observations 和 StrategyRunManifest | 每个决策可追到固定 Release 内容、消费者契约及启动前状态观察 |
| FR-KB-004 | P0 | 处理撤回和不兼容 Schema | 新 run 失败关闭，历史 run 不被改写 |
| FR-KB-005 | P0 | 使用 `var/cache/kb-releases/` 内容寻址缓存和自有 SQLite 索引 | `20 GiB` 软上限；历史引用制品不自动删除；不共享 KB 数据库、缓存、迁移或 volume |
| FR-KB-006 | P0 | 契约 fixture、策略 fixture、正式 Release 分离 | 合成事实不能冒充 KB 正式数据 |

### 19.2 产业与事件

| ID | 优先级 | 需求 | 验收 |
|---|---|---|---|
| FR-CTX-001 | P0 | 从指定 Release 建立带 `as_of` 的策略上下文视图 | 无合格 Context Pack 的公司不能进入 decision_pool |
| FR-CTX-002 | P0 | 历史时点使用当时 Release 中的产业图 | 不得用后见公司标签回填 |
| FR-IND-001 | P0 | 区分产业卡点与可投资卡点 | 两道门分别留事实引用、判断和否决原因 |
| FR-IND-002 | P0 | 公司映射分 technical/qualified/profit beneficiary | 只有 profit beneficiary 可进入四道门 |
| FR-EVT-001 | P0 | 实现 E0—E7 与 E3.5 | 状态可重放且不可跳过必填事实 |
| FR-EVT-002 | P0 | 独立判定 E4_public | KB CandidateEvent、标题或关键词不能直接升级 |
| FR-EVT-003 | P0 | 关联供应商、客户和采购端公开事实 | 每个候选记录最早合法公开事实 ID |
| FR-EVT-004 | P0 | Fact/Assumption/Derived/Judgment 分离 | 四类字段不可混写，策略 Derived 不回写 KB |

### 19.3 决策、风险与执行

| ID | 优先级 | 需求 | 验收 |
|---|---|---|---|
| FR-GATE-001 | P0 | 四道门全部为 AND | 任一失败不能被总分补偿 |
| FR-GATE-002 | P0 | 建立反事实 NTM 利润分母 | 无可信分母时 `ABSTAIN` |
| FR-GATE-003 | P0 | 建立基准/下行/上行/压力情景 | 假设、触发器、证伪和事实引用完整 |
| FR-GATE-004 | P0 | 重建四档市场预期 | `fully_priced/unknown` 不得进入交易 |
| FR-GATE-005 | P0 | 基础业务价值与事件增量 FCF 分开 | 无重复计价和无证据永续价值 |
| FR-GATE-006 | P0 | 在首次可成交价格重跑 Gate 3/4 | 涨停后不得沿用公告前结论 |
| FR-RISK-001 | P0 | 从压力损失反推仓位 | 每笔显示账户损失预算和绑定约束 |
| FR-RISK-002 | P0 | 单票、风险簇、总风险与回撤取最严约束 | 任一硬约束可阻断仓位 |
| FR-RISK-003 | P0 | 市场状态只缩放风险 | 不得改变四道门事实判断 |
| FR-EXEC-001 | P0 | 回放 T+1、涨跌停、停牌、费用和容量 | 不可成交场景误成交为 0 |
| FR-EXIT-001 | P0 | 实现证据/风险/时间/价值四类退出 | 每次退出可追到规则和当时输入 |
| FR-AUDIT-001 | P0 | 保存目标、批准、模拟、实际和人工差异 | 每个 run 产生可验证对账记录 |

---

## 20. 样本量、验证与有效定义

### 20.1 样本充分性

- 独立 `E4_public` 少于 30 个：不足以评价 E4 识别体系；
- 任一关键子组少于 15 个：只作描述，不下统计结论；
- 声称策略有效前，至少需要 30 个相互独立、真实可成交并已结束的完整交易；
- 独立性按公司、客户、产业催化和时间风险簇检查，不能把同一订单多份材料当多个样本。

`30/15` 是预登记门槛；正式验证开始后冻结。样本不足时按“修复覆盖→扩展年份/来源→扩展同机制相邻产业→共同评审定义”的顺序处理。

### 20.2 偏差控制

- 2019—2022、2023、2024—2026 分段报告；
- 股票池包含当时全部候选、失败者、退市和被否决公司；
- PIT 强制 `available_at <= decision_at` 且不超过 `knowledge_cutoff`；
- 使用历史有效交易规则、税费和证券状态；
- 报告 `ABSTAIN`、`BLOCKED`、假阳性、假阴性和无法成交；
- 对行业、成长、质量、动量、市值和市场 Beta 做归因；
- 记录全部参数搜索，执行参数邻域、消融和过拟合审计。

已参与规则设计的历史年份只能算次级验证；规则冻结后的前瞻数据才是真正未知样本。

### 20.3 Golden cases 与 fixture

首个合成纵向切片至少固定五类结果；前四类来自合成策略 fixture，`BLOCKED` 来自独立失败注入 fixture：

- 四道门全部通过：`TRADE_READY`；只证明决策路径可达，不代表允许 paper、live 或真实仓位；
- E3.5 经济义务未闭合：`SHADOW_ONLY`；
- E4 成立但利润不重要或已定价：`REJECT`；
- E4 已可确认，但金额、价格、最低数量、利润分母、预期或估值关键字段未知：`ABSTAIN`；
- Release 撤回、哈希不匹配或 Schema 不支持：`BLOCKED`。

任何 `TRADE_READY` 合成正例须在最小规则包批准后才能加入。真实公司案例用于检验规则边界，不能预设交易结论；正式 KB Release 的 smoke test 允许全部不通过。

### 20.4 验证阶梯

1. `research_calibration`：早期样本开发规则，所有修改留版本；
2. `locked_historical_replay`：冻结字段、门槛和退出后做时间顺序回放；
3. `forward_shadow`：规则冻结日起登记全部买入、拒绝、回避和阻断；
4. `small_live_canary`：仅在另行明确授权后，以较低风险验证延迟、滑点和人工执行。

历史通过线暂定：至少 30 个独立交易、扣费后平均期望收益为正、按风险簇重采样后 95% 置信区间下限大于 0、样本外最大回撤不超过 15%、最大盈利交易不超过总净利润 25%，并报告绝对和基准超额收益。全部为 `hypothesis`，进入验证后冻结。

前瞻要求暂定：shadow 至少 6 个月且不少于 10 个合格信号；任何小额 canary 需再次批准，至少 6 个月且不少于 10 笔结束交易、最大回撤不超过 8%、成本和延迟未系统性超模、无未记录人工挑选。

### 20.5 追加资金与停机

额外 20 万元不得一次投入：

| 阶段 | 新增资金 | 前置条件 |
|---|---:|---|
| 第一批 | 5 万元 | 第 20.4 节全部验证门通过 |
| 第二批 | 5 万元 | 新增后再运行至少 3 个月并完成至少 10 笔交易，无规则、成本或回撤恶化 |
| 第三批 | 10 万元 | 再运行至少 3 个月并再完成至少 10 笔交易，结果仍在合理验证区间 |

- 资金增加不提高单笔风险比例；
- 组合回撤达到 12% 时冻结后续追加；
- 达到 15% 停机线时，未投入资金全部冻结；
- 追加资金只能扩大同一已验证策略，不能同时引入新产业或新规则。

---

## 21. 非功能、安全与项目隔离

| 维度 | 要求 |
|---|---|
| 可重现 | 同一代码、规则、配置、固定 Release、环境锁和随机种子产生一致结果 |
| 可解释 | 所有状态、仓位、退出和拒绝可回到事实引用、假设、规则与价格 |
| 失败关闭 | 输入、撤回、Schema、数据冲突或风险引擎故障时禁止新仓 |
| 安全 | 研究 Agent 无券商凭证、KB 写权限和自由文本下单权限 |
| 合规 | 只使用 KB 正式发布的授权公开信息；疑似 MNPI 禁止进入策略 run |
| 可观测 | 记录输入验证、处理延迟、缺失、冲突、滑点、成本和人工覆盖 |
| 可维护 | 输入适配器、规则、阈值、费用和状态机版本化 |
| 人工控制 | 任何未来 live 输出均需固定输入、规则版本、测试报告和人工批准 |

工程隔离必须满足：

- 本地开发按已确认方案复用工作站级 Python 3.12 Conda 环境 `E:\Conda\envs\Data_Analysis`，但它只提供解释器和受控共享包，不构成 KB/InvestSystem 代码依赖；
- InvestSystem 独立拥有 `pyproject.toml`、带哈希的 runtime/dev lock、TOML 配置、`var/cache/kb-releases/` 缓存、`var/state/invest_system.sqlite3` SQLite 索引和运行目录；缓存软上限为 `20 GiB`，历史引用制品不得自动删除；CI 必须在干净 Python 3.12 环境中按本项目 lock 安装；
- InvestSystem 只以 editable `--no-deps --no-build-isolation` 注册。缺包可在精确锁定、保存安装前基线且不改变既有共享包的前提下加入 `Data_Analysis`；安装后必须验证 `pip check` 不新增冲突并运行本项目测试；
- 不复用 KB 的项目包、项目虚拟环境、数据库、缓存、迁移或部署 volume；即使 KB editable 包已存在于共享解释器中，策略代码和测试也不得导入；
- 消费凭证若存在，只授予发布面只读权限，不得获得 KB 管理写权限；
- 两个项目 required CI 各自只构建和测试本仓库；
- InvestSystem 固定已发布的 Schema、lock 和 fixture 字节/哈希，升级通过显式依赖更新；
- HTTP API 与不可变导出包兼容验收由 InvestSystem 或独立任务发起，只读 KB，不阻塞 KB 主线发布；
- KB 暂时不可用时，已验证缓存可支持固定历史 Release 的离线重放，但不能解析新的 `latest` 或改变输入。

---

## 22. 分阶段交付顺序

### 阶段 A：边界和需求冻结

- 用户已于 `2026-07-31` 审阅并批准本 PRD；
- 修正产业项目中残留的采集、raw/staging 和原文归档职责描述；
- 冻结 KB/InvestSystem 边界、术语和权威层级；
- 把最小纵向切片所需 `hypothesis` 转写为规则规格。

完成门：文档无职责矛盾，未知项全部显式标记，用户批准需求基线。该门已随 Stage 0 边界 ADR、仓库文档同步和 Git remote 护栏验证一并关闭；规则规格仍须另行批准。

### 阶段 B：独立工程与契约骨架

- 复用 `Data_Analysis` 作为本地解释器，同时建立 InvestSystem 自有 `pyproject.toml`、`requirements-build.in`、带哈希的 runtime/dev lock、锁生成脚本、环境基线、TOML 配置、`contracts/`、`src/`、`tests/` 和运行目录；
- 项目使用 editable `--no-deps` 注册，记录共享环境安装前后差异；独立 CI 从本项目 lock 创建干净环境；
- 定义 StrategyRunManifest、receipt/observation Schema、DecisionRecord、provider-neutral DTO 和 fixture/test harness；
- 本阶段不导入 KB 官方 Schema/fixture，也不生成真实 receipt；这些属于阶段 C1；
- 用合成输入验证确定性重放和失败关闭。

完成门：独立 CI 可在没有 KB 源码、数据库和服务的情况下通过契约/单元测试。

### 阶段 C1：KB Adapter 契约验收

- 通过显式依赖更新固定 KB 公共 Schema、lock、官方 fixture 字节和来源哈希；
- 实现精确 ID 的只读 Release 客户端、Manifest/制品验证、自有缓存和 receipt；
- 将确定性 receipt 与 append-only `ArtifactFetchObservation` / `ReleaseStatusObservation` 分开；
- 用失败注入 fixture 验证撤回、哈希错误和 Schema 不兼容，用官方 fixture 验证 published 正常路径与幂等；
- 对 KB 官方 fixture 执行黑盒兼容测试。

### 阶段 C2：合成策略纵向切片

- 批准最小 E3.5/E4、四道门、利润桥、预期和估值规则；
- 使用 InvestSystem 自有合成策略 fixture 覆盖 `TRADE_READY/SHADOW_ONLY/REJECT/ABSTAIN`，并用独立失败注入 fixture 覆盖 `BLOCKED`；
- 生成 StrategyRunManifest、DecisionRecord 和 replay hash。

`C1` 与 `C2` 可以并行；策略内核开发不等待 KB 部署节奏。

### 阶段 D：真实 KB Release 端到端验收

- 锁定一个可公开复现的正式 Release；
- 从独立 HTTP/导出面完成下载、验证、receipt、run 和决策；
- 不改变事实以追求正例；真实结果允许 `ABSTAIN`；
- 证明同一输入、规则和版本重复运行得到相同 receipt 与 `replay_hash`；新的 Fetch/StatusObservation 只追加，不要求 observation ID 相同。

### 阶段 E：完整产业策略和执行开发

- 扩充 E0—E7、四道门、利润桥、估值、组合风险和退出；
- 回放 A 股交易规则、费用、滑点、容量和无法成交；
- 阶段 C1/C2 完成后即可开始；完整 P0 规则在本阶段逐项冻结、批准和实现，本阶段完成门要求完整规则包均为 `approved` 且可追踪到测试；
- 可与阶段 D 的正式 KB Release E2E 并行；
- 只有阶段 D 与本阶段的策略/执行开发都完成后，才运行正式 golden、walk-forward、冻结 holdout、shadow 和人工 go/no-go。

当前 PRD 只定义需求；以上代码、测试和运行能力均不得在实际交付前标记为完成。

---

## 23. 下游待规格化事项

以下治理项已由 [ADR-0001](../../docs/adr/ADR-0001-kb-investsystem-boundary.md) 冻结：首版单一 `strategy_input_ref`；HTTP API 与不可变导出包双传输面；InvestSystem 自有 SQLite；`var/cache/kb-releases/` 与 `20 GiB` 软上限；历史引用制品不自动删除；撤回阻断新 run，历史材料仅供 `audit_replay`。

以下内容仍必须在 `03_规则与规格/`、公共契约或 `06_测试与验证/` 中明确，不能由代码或 LLM 自行决定：

1. StrategyRunManifest 完整 Schema 和 receipt 生命周期；
2. 缓存未引用制品的 GC 宽限期、并发保护和操作流程；
3. `standard_track` 的利润稳健性判定；
4. E0—E7 的状态转换、降级、冲突和证据覆盖规则；
5. Gate 2 情景变量的历史误差校准；
6. Gate 3 观察窗口、量化阈值、最低信息覆盖和冲突处理；
7. Gate 4 保守估值方法、倍数/折现率、价值区间和版本规则；
8. 市场 `NORMAL/DEFENSIVE/CRISIS` 指标与阈值；
9. 盘中延迟、VWAP 窗口、滑点、冲击和容量模型；
10. 基准、风险簇、独立样本和 P&L 归因算法；
11. E5—E7 财务验证、加减仓和退出规则；
12. 人工批准、paper/shadow 操作和未来 live 合规评审。

---

## 24. 最终验收口径

本需求阶段完成的标准是：

1. 明确区分 KB 事实平台与 InvestSystem 策略系统；
2. 所有正式 run 精确保存五字段 `strategy_input_ref`、确定性 `ArtifactConsumptionReceipt`、append-only Fetch/StatusObservation 和 StrategyRunManifest；
3. 系统不直接访问 KB SQLite、raw、staging 或内部实现，也不向 KB 写策略逻辑；
4. 产业上下文、商业状态、四道门、利润桥、估值、仓位和退出形成闭环；
5. E4 不被误解为自动买点，KB CandidateEvent 不被误解为 E 状态；
6. 三情景、利润分母、市场预期和首次可成交价格可在固定 Release 上重放；
7. 合成策略 fixture 与正式 KB Release 清晰隔离，KB 不为策略正例定制事实；
8. 所有数值参数的 `hypothesis` 身份清晰；
9. 验证有效、追加资金和任何未来 live 都有预先冻结的证据门槛；
10. 本 PRD 已获批准，可以推进工程骨架；最小规则包仍须逐项批准后才能实现或进入回测。

系统在任何阶段都不能声称能够保证从 10 万元增长到 1,000 万元。它只能通过严格的样本外和前瞻证据，逐步证明或否定是否存在可执行的正期望。
