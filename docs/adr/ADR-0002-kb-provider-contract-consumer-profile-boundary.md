# ADR-0002：KB 通用提供方契约与 IS 消费规则边界

状态：`proposed / pending owner approval / zero runtime authority`

提议日期：`2026-08-26`

跨仓决策标识：`KBIS-ADR-0002`

适用范围：`InvestmentResearchKB public delivery surface and InvestSystem consumer adaptation`

## 1. 背景

[ADR-0001](ADR-0001-kb-investsystem-boundary.md)已经批准 KB 是独立数据与证据提供方，IS 是策略与决策消费者。随后批准的 [Stage 6 最小历史公共数据消费契约 v0.2](../validation/stage6-minimum-public-data-consumption-contract-v0.2.md)正确冻结了 `S6DATA-01—10`，但部分“消费者需要什么”的表达被 KB draft Schema 直接物化，形成反向耦合风险：

- KB draft 使用 `historical-stage6-public-input` 和 “for IS” 命名；
- KB draft 出现 `strategy_input_ref`、`authority_eligible`、holdout/outcome 标志；
- benchmark 日线和 factor Schema 把 `H00985`、ADV20/Beta120 和 IS 规则直接固化；
- CorporateAction 五类和一级行业被表达为封闭的 KB 永久本体，而不是 IS 首版最低消费范围；
- 单一 root、固定三个 source families 和 2019—2025 被同时当成 KB 核心模型与 IS 验收要求。

侧边会话 `01a03e25-6199-7923-941a-881d4c343b5e`只提供架构讨论方向，不是 ADR、Schema 或审批证据。本 ADR 只有在 owner 明确批准后才生效。

## 2. 已有谱系保持不变

- ADR-0001：继续有效；
- `S6DATA-01—10`：继续全部 approved；
- v0.1/v0.2 文档、机器契约和 approval record：原始字节及 SHA-256 不变；
- 已固定的 KB v1 与 Stage 6B transport snapshot：继续只读兼容；
- 已完成的 Stage 3D/6B validation-only 验收：保留历史事实，不升级为运行权限。

本 ADR 不撤销历史决策，只澄清“公共提供方契约”和“消费者验收规则”的所有权。

## 3. 提议决策

### 3.1 依赖方向

```text
KB 通用 Published Release / Artifact / Schema / Context Pack
                         ↓
              IS KB Adapter 验证与投影
                         ↓
       IS Consumer Profile / StrategyRunManifest / 决策
```

KB 不导入 IS 契约，不按 IS Stage、策略或运行状态设计核心 Schema。IS 固定并消费 KB 公共提交和不可变 Release，通过 Adapter 适配 KB，而不是要求 KB 输出 IS 内部对象。

### 3.2 KB 所有权

KB 继续拥有：

- Release、Manifest、Status、Artifact、Schema、Context Pack；
- 通用 Release identity 和可变长度 dependency closure；
- PIT、`observed_at`、`available_at`、source、revision、conflict、missing reason；
- Company、Security、Calendar、MarketRuleSet、SessionState、Mark、CorporateAction、Financial、Benchmark；
- 通用 benchmark observation、factor definition/registry、factor observation 与 raw basis；
- 可扩展 CorporateAction type 与行业分类层级；
- 通用数据质量 Profile 和合法再分发资格。

KB 的公共核心 Schema 不包含 IS Stage、策略候选、coverage、投资结论、`StrategyRunManifest`、运行准入、仓位或订单语义。

### 3.3 IS 所有权

IS 继续拥有：

- 从 KB root Release identity 构造的 `strategy_input_ref`；
- KB Adapter 与 provider-neutral projection；
- `StrategyRunManifest`、Receipt、Observation、RetentionClosure、RunReleaseStatusConfirmation；
- H00985 选择、ADV20/Beta120 接受与抽样重算；
- 2019—2025、SSE/SZSE、BSE deferred、五类公司行动最低要求；
- candidate、coverage、holdout、E0—E7、四道门、利润桥、估值和决策；
- `authority_eligible`、ABSTAIN/BLOCKED 和全部运行权限。

### 3.4 Release 与单一输入

KB 提供通用 aggregate/dependency closure 能力，不把“一个策略 run 只能有一个输入”写入核心 Schema。KB 可以拥有多个通用 source/aggregate Release 产品。

IS Consumer Profile 选择一个满足自身域闭包的 root Release，并在一次 run 中只物化一个 `strategy_input_ref`。这保留 ADR-0001 和 `S6DATA-07`，但不把 IS 运行限制反向施加到 KB 数据模型。

### 3.5 Benchmark 与 factor

KB 的基础 Schema 使用通用 `benchmark_identities[]`、`factor_definitions[]` 和参数化方法，不在基础 Schema 中把 `H00985` 写成唯一常量。

KB 可以发布一个版本化、可复用的 `H00985 + 120-session OLS` factor definition/observation；IS Consumer Profile 精确选择该定义，并按 `S6DATA-03/05` 对 raw basis 做抽样重算。KB 预计算结果不是 IS 策略接受结论。

同理，KB CorporateAction 和行业分类 Schema 必须允许版本化扩展；Stage 6 Profile 只要求首版五类公司行动和一级行业，不能把该最低集合冒充 KB 的完整事实本体。

### 3.6 Authority、holdout 与 outcome

KB 只报告 Release current status、PIT 和事实时间范围。以下概念相对于 IS run 才有意义，禁止进入新 KB 核心 artifact：

- `authority_eligible`；
- `contains_holdout_content`；
- `contains_outcome_content`；
- `authorizes_*`；
- candidate/coverage/champion/decision/trading fields。

IS 根据 Consumer Profile、decision time、status confirmation 和本地批准规则得出上述状态。

## 4. 兼容策略

1. KB 已发布的 `strategy-input-ref.v1` 不删除、不原地改写；IS 继续兼容读取。
2. 新 KB 公共契约使用通用 `ReleaseReference`/Release identity；IS Adapter 映射为 `StrategyInputRef`。
3. Stage 3D/6B 专用 handoff 保留为历史 validation-only 证据，不作为未来通用接口模板。
4. KB 已合并但未进入正式 contract lock 的 `historical-stage6-public-input-manifest.v1` 应由 KB 后续标记为 `superseded_never_published`，另建通用 Schema。
5. artifact Schema/catalog 增量仍使用 transport v1；只有 endpoint、envelope、header 或 auth 语义变化才形成 transport v2。
6. 新旧兼容由版本化 fixture 和 IS Adapter 测试证明，不通过静默字段别名或运行时猜测实现。

## 5. 不属于本 ADR 的授权

即使本 ADR 获批准，也不授权：

- KB Schema 实现、backfill、Release 或生产变更；
- IS repin、parser、handoff 或 historical run；
- 2026 holdout 读取或推断；
- migration、backtest、paper、shadow、live、仓位或订单。

## 6. 待 owner 原子确认

- [ ] `S6BOUND-01`：批准 KB public contract 与 IS Consumer Profile 使用独立版本空间。
- [ ] `S6BOUND-02`：批准新 KB 核心 Schema 不再输出 `strategy_input_ref` 或 IS run 字段。
- [ ] `S6BOUND-03`：批准 `authority_eligible`、holdout/outcome 和运行权限只由 IS 持有。
- [ ] `S6BOUND-04`：批准 KB 提供通用 aggregate dependency closure，单一 root 只作为 IS run 约束。
- [ ] `S6BOUND-05`：批准 KB benchmark/factor 基础 Schema 参数化，H00985 由 IS Profile 选择。
- [ ] `S6BOUND-06`：批准 KB 继续发布 raw basis 和版本化通用 factor，IS 保留重算与接受责任。
- [ ] `S6BOUND-07`：批准 v0.2 继续有效，但正式解释为 IS 消费需求与验收 Profile。
- [ ] `S6BOUND-08`：批准 legacy `strategy-input-ref.v1` 与专用 handoff 只兼容读取，不作为新生产模板。
- [ ] `S6BOUND-09`：批准 Schema/catalog 增量不自动升级 transport v1。
- [ ] `S6BOUND-10`：确认本批准仍为零运行权限，不授权任何数据或策略执行。

十项必须原子批准；部分批准不生效。
