# Stage 6 历史公共数据消费与验收 Profile v0.3 草案

状态：`draft_for_owner_confirmation / zero_runtime_authority`

版本：`0.3.0-draft`

形成日期：`2026-08-26`

依赖提议：[ADR-0002](../adr/ADR-0002-kb-provider-contract-consumer-profile-boundary.md)

## 1. 目的

本文件完整表达 IS 如何选择、验证和映射 KB 通用 Release。它不是 KB Schema，不要求 KB 使用 IS 字段名，也不证明 KB 已有合格历史数据。

本草案保留 [v0.2 正式消费契约](stage6-minimum-public-data-consumption-contract-v0.2.md)及 `S6DATA-01—10` 的批准结果，只将职责重新分层：

- v0.2：已批准的消费者需求和验收口径；
- v0.3：待批准的通用 KB 输入到 IS 内部对象的映射；
- KB public contract：独立版本化的通用提供方契约。

## 2. 固定历史谱系

- v0.2 Markdown raw SHA-256：`ea82f2e17b99ecaec0cafde7ce5fe0fdb5d6d6855f6348891369cd0b2f02db43`
- v0.2 machine raw SHA-256：`a7fd65c0d955d4e3610dcbefbaf6a2ec600689986aee0aa80123d167f8c88f6a`
- v0.2 canonical contract SHA-256：`4063575384771228433fb8849c0fedd9fac2ba78f704ce5551bb4e23fe8c3557`
- v0.2 approval raw SHA-256：`ab40ae5392a8c9d22e507c59066d20d84df7cec78ffcc77ff4aac4ce4a616b31`
- v0.2 approved decisions SHA-256：`211f046282cb31f046db2fa382af38457810cbb03c20dfd60fb41162c84c5da4`

上述对象保持原始字节，不由本草案回写。

## 3. IS 接受的 KB 通用输入

IS Adapter 只从固定 KB public contract 读取：

1. root Release identity：Release ID、Manifest hash、knowledge cutoff、Schema version；
2. 通用、可变长度的 source Release dependency closure；
3. Artifact ID、Schema ID/version/hash、bytes hash、size、record count；
4. 各数据域的 grain、keys、date range、missing、duplicate、orphan、PIT 和 revision Profile；
5. `benchmark_identities[]` 和 benchmark observations/methodology；
6. `factor_definitions[]`、factor observations、completeness 和 raw basis hashes；
7. Company/Security/Calendar/Rule/Session/Mark/Action/Financial/Industry 通用事实；CorporateAction type 和行业分类层级可版本化扩展；
8. declared missing、unrecoverable、conflict 和 correction lineage；
9. Release Status event chain 和公开传输响应身份。

KB 不需要输出 `strategy_input_ref`、`authority_eligible`、IS holdout/outcome 或运行批准字段。

## 4. Adapter 映射

| KB 通用输入 | IS 生成对象 | 所有权 |
|---|---|---|
| root Release ID + Manifest hash + cutoff + Schema version | `StrategyInputRef` | IS |
| dependency closure | `ReleaseRetentionClosure` | IS |
| Artifact descriptors 与下载字节 | `ArtifactConsumptionReceipt` | IS |
| Status event chain 与响应字节 | `ReleaseStatusObservation` | IS |
| producer data-quality Profile | `HistoricalDataReadinessReport` | IS |
| `benchmark_identities[]` | H00985 精确选择结果 | IS |
| `factor_definitions[]` + raw basis | ADV20/Beta120 接受与抽样重算结果 | IS |
| PIT facts/evidence/context | provider-neutral strategy input | IS |
| IS status confirmation + approval capability | `authority_eligible` 与准入结果 | IS |

Adapter 对未知 Schema/字段失败关闭；不得用字段名猜测、默认值或 KB 本机路径补齐。

## 5. S6DATA-01—10 职责映射

| 决定 | KB 通用能力 | IS 消费与验收责任 |
|---|---|---|
| `S6DATA-01` | 发布完整 Security lifecycle、exchange 和状态事实 | 选择 SSE/SZSE 普通 A 股，BSE deferred，并保留 ST/退市/失败/代码变化分母 |
| `S6DATA-02` | 发布通用 benchmark identity/observation/methodology | 选择 CSI `H00985` gross total return，禁止 fallback |
| `S6DATA-03` | 发布 raw returns/session basis 与参数化 factor definition | 接受 previous exactly 120、带截距 OLS、no imputation 的 Beta120 |
| `S6DATA-04` | 发布 turnover/calendar/session-state raw basis | 接受 previous exactly 20-session CNY turnover mean 的 ADV20 |
| `S6DATA-05` | 发布 raw basis 和版本化通用 factor observation | 抽样重算并决定是否用于策略 |
| `S6DATA-06` | 在通用 market-reference closure 中发布 factor artifact 或其 child dependency | Adapter 通过 closure 定位，不要求 KB 使用 IS 内部字段名 |
| `S6DATA-07` | 提供通用 aggregate dependency closure | 一次 run 只选择一个 root `StrategyInputRef` |
| `S6DATA-08` | CorporateAction Schema 支持通用、可扩展 action types | 最低要求现金分红、送股、拆并股、配股、退市/现金退出五类 |
| `S6DATA-09` | 报告完整 Release identity 与逐域质量 Profile | 应用 closure 100% 和目标 universe/calendar/rule/lifecycle 验收门 |
| `S6DATA-10` | 保持 versioned transport 与 artifact Schema | 仅传输语义变化才 repin transport v2 |

## 6. IS 固定消费口径

### 数据范围

- development/walk-forward data scope：`2019-01-01—2025-12-31`；
- `2026` 是 IS holdout；KB 只发布客观日期范围，IS 负责隔离；
- target universe：SSE/SZSE ordinary CNY A shares，BSE deferred。
- 行业消费口径：首版使用 PIT 一级行业；KB 行业分类本体不得因此被永久锁死为一级。

### H00985 与 Beta120

- IS 从通用 benchmark identities 中精确选择 `H00985`；
- provider=`CSI`，return type=`gross_total_return`，currency=`CNY`；
- previous exactly 120 exchange sessions，不含 decision session；
- daily paired PIT total returns，OLS slope with intercept；
- 缺失、短窗口、零方差或 PIT 不可证明时 incomplete；
- 不缩短、不插值、不填零、不用未来公司行动向后复权；
- `000985`、`N00985`、`H00300` 和自建成分历史均不是 fallback。

### ADV20

- previous exactly 20 exchange sessions，不含 decision session；
- CNY turnover arithmetic mean；
- 证明全天停牌才允许零 turnover；
- missing/unknown state 使 factor incomplete。

## 7. Provider 核心 Schema 禁止项

IS 不再要求新 KB 核心 artifact 包含：

- `stage6` 或 `investsystem` 专用命名；
- `strategy_input_ref`；
- `authority_eligible` 或 `authorizes_*`；
- `contains_holdout_content`、`contains_outcome_content`；
- `h00985_benchmark_identity` 单一字段；
- `adv20_beta120_factor_identity` 单一字段；
- H00985 常量化的 benchmark 基础 Schema；
- 只允许五类 CorporateAction 或只允许一级行业的封闭 provider ontology；
- candidate、coverage、champion、ABSTAIN/BLOCKED、position、order；
- 固定恰好三个 source Release；
- IS `snapshot_lock`。

KB 可以在通用数组/registry 中包含 H00985、ADV20/Beta120 定义，但不能把它们写成基础 Schema 唯一常量。

## 8. Legacy 兼容

- 已固定 `strategy-input-ref.v1`：继续验证并映射，不要求 KB 修改 Published v1；
- Stage 3D/6B 专用 handoff：只用于历史 validation-only replay；
- 旧 v0.2 envelope：保留审计，不作为未来 KB 输出模板；
- 新 KB generic fixture：必须由 IS 固定公共提交后进行离线映射测试；
- 无静默 alias、自动 fallback 或运行时跨仓读取。

## 9. 当前权限与下一门

本草案没有读取 KB artifact、Token 或 holdout，没有实现 parser/Adapter，也没有 repin。以下全部保持 false：

- real handoff；
- backfill/Release；
- parser/repin；
- candidate/coverage/historical run；
- migration/backtest/paper/shadow/live；
- positions/orders；
- KB writes。

下一门是 owner 原子批准 ADR-0002 `S6BOUND-01—10` 和本 Profile；随后由 KB 先形成通用 draft Schema/catalog/fixture，再由 IS 固定公共提交并实现离线 Adapter 测试。
