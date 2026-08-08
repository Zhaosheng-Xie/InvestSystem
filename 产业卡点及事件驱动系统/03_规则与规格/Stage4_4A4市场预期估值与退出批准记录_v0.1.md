# Stage 4 / 4A-4 市场预期、估值与退出批准记录 v0.1

文档状态：`approved`

批准日期：`2026-08-08`

批准范围：`stage4_synthetic_research_validation`

批准对象：[Stage 4 / 4A-4 市场预期、估值与退出规则包 v0.1](Stage4_4A4市场预期估值与退出规则包_v0.1.md)

原 draft 规格 SHA-256：`7f2f1238ff5d9bae1c7a96b212b87dd56a04ac8a9013715e46d2b6cc9d864a62`

原 draft canonical bundle SHA-256：`2d6ebeafeb93fd0d799ab31c1a93e88639e7979fc6416179a18158a9a4450055`

原 draft rules SHA-256：`5692fae5ab76c233d2f3d3ff3c0e23002062a179426de843c46d5439c09d543c`

## 1. Owner 明确批准

owner 在收到下列完整批准边界后，于 `2026-08-08` 明确回复“批准”：

> 批准《Stage 4 / 4A-4 市场预期、估值与退出规则包 v0.1》第 10 节全部 24 项，仅授权 `stage4_synthetic_research_validation`，不授权 backtest、paper、shadow、live、仓位或订单。

该批准只覆盖原 draft 规格第 10 节的二十四项精确语义。原 draft 文档和 draft machine proposal 保持不变；approved machine bundle 和 approval record 另行生成，禁止原位改写 draft。

## 2. 批准边界

```text
scope = stage4_synthetic_research_validation
run_mode = research
validation_only = true
input = InvestSystem-owned anonymous synthetic fixture
runtime_capability = exact 4A-4 bundle only
full_stage4_capability = false until separate 14-rule integration approval
backtest = false
paper = false
shadow = false
live = false
positions = false
orders = false
```

`TRADE_READY`、`EXIT_CANDIDATE` 只能作为合成研究结果标签。所有 position、weight、approver、order、execution 和 P&L 字段保持空或零；标签不构成运行模式、资金权限或策略有效性证据。

## 3. 批准项

### FR-GATE-004

- [x] `4A4-APPROVAL-001`：E4 前 append-only `ExpectationSnapshot` 的字段、PIT 和“未找到不等于明确为零”语义。
- [x] `4A4-APPROVAL-002`：事件、主体、产品、币种、单位、期间、义务、利润/FCF 和实质条件的严格可比口径。
- [x] `4A4-APPROVAL-003`：`PreE4MarketContext` 必留、无校准阈值前不得单独改变分类、缺失为 `ABSTAIN`、E4 后信息不得回填。
- [x] `4A4-APPROVAL-004`：基础价值区间反推公告前隐含事件价值及三态严格区间关系。
- [x] `4A4-APPROVAL-005`：`unexpected` 只限先验明确无绑定事件且 E4 带来正的绑定义务及正的基准增量利润/FCF。
- [x] `4A4-APPROVAL-006`：`partially_priced/fully_priced/unknown` 的利润/FCF 区间语义、跨维度不可排序和叙事不得替代经济增量。
- [x] `4A4-APPROVAL-007`：Gate 3 聚合、短路、冲突/缺失/硬失败和禁止分数补偿。

### FR-GATE-005

- [x] `4A4-APPROVAL-008`：基础业务价值排除目标 E4，并固定 equity/currency/unit/tax/minority/ownership/fully-diluted-shares 口径。
- [x] `4A4-APPROVAL-009`：版本化主估值方法、显式倍数/折现/长期增长/净债务/股数、无行业默认值及交叉方法不得择优替换。
- [x] `4A4-APPROVAL-010`：E4 有限期增量 FCF 现值、显式折现因子及单次事件无终值/永续增长。
- [x] `4A4-APPROVAL-011`：NTM 后 base/downside 只纳入公开绑定最低义务，无约束增长只进入 upside。
- [x] `4A4-APPROVAL-012`：base/downside/upside/stress 价值区间的一致口径、逐端顺序、缺失和失败语义。
- [x] `4A4-APPROVAL-013`：`valuation_component_id` 唯一归属和基础业务/事件现金流防重复计价图。
- [x] `4A4-APPROVAL-014`：Stage 4 只接受显式 `SyntheticResearchPriceAssumption`，真实价格和摩擦机制留在 Stage 5。
- [x] `4A4-APPROVAL-015`：Gate 4 使用 base/downside 下界及仅限合成研究的 `0.15` 净基准收益、`2.00` 赔率、`downside_loss>0`、等号通过和只有 upside 达标为 `REJECT`。
- [x] `4A4-APPROVAL-016`：两个 falsifier、一个不超过 `120` 交易日的预登记验证点、Gate 4 聚合及合成 `TRADE_READY` 始终 FLAT/零权限。

### FR-EXIT-001

- [x] `4A4-APPROVAL-017`：退出为独立策略判断，只接受 `no_position` 或匿名 `SyntheticHoldingSnapshot`，不产生卖单、权重、成交或 P&L。
- [x] `4A4-APPROVAL-018`：取消/义务清零、验收失败、越窗延期、价格数量下调、客户信用恶化和利润桥失效六类 evidence exit。
- [x] `4A4-APPROVAL-019`：risk-budget exit 只比较外部不可变快照，实际损失大于等于登记预算即触发，不生成预算或账本。
- [x] `4A4-APPROVAL-020`：`elapsed_trading_days>=120` 且预登记验证事件未确认触发 time exit，禁止临时更换催化点。
- [x] `4A4-APPROVAL-021`：current market cap 大于等于当前基准价值区间下界且无 E5/E6 价值提升证据时触发 value exit。
- [x] `4A4-APPROVAL-022`：E5/E6 新证据 append-only 重新承保，以当前 PIT 证据/价格重跑适用 Gate，价格变化本身不改价值或事实门槛。
- [x] `4A4-APPROVAL-023`：`blocked → confirmed exit → unknown/ABSTAIN → reunderwrite → hold → not applicable` 聚合，未知不能抵消已确认触发器。
- [x] `4A4-APPROVAL-024`：4A-4 制品 append-only/version/hash/supersedes/replay、禁止 KB 写回及零 backtest/paper/shadow/live/仓位/订单权限。

## 4. 实现约束

- runtime 只读取 approved machine bundle，不解析本 Markdown；
- typed capability 必须绑定精确 bundle hash、approval ID、approval record hash、scope 和 4A-1—4A-3 上游 bundle；
- 默认 registry 保持为空，调用方必须显式注入 approval record；
- 任一 hash、scope、依赖、PIT、单位、估值图、合成身份或 replay 漂移均失败关闭；
- 每项规则必须有正例、反例、边界例和 `ABSTAIN`，并覆盖 `BLOCKED`、确定性和隔离；
- 本批准不证明 `0.15`、`2.00`、`120` 或估值/退出语义具有历史有效性。

## 5. 仍未批准

- 完整 14 项 Stage 4 machine bundle、完整引擎 capability 和统一 DecisionRecord；
- 真实 KB Context Pack 输入、backtest、paper、shadow、live、TargetPortfolio、仓位、订单、成交和 P&L；
- Stage 5 的首次实际可成交价格、交易日历、风险预算、账本与执行；
- 对题材扩散与资金轮动系统的任何信号或规则复用。
