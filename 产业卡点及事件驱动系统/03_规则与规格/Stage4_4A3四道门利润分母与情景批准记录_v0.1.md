# Stage 4 / 4A-3 四道门、利润分母与情景批准记录 v0.1

文档状态：`approved`

批准日期：`2026-08-08`

批准范围：`stage4_synthetic_research_validation`

批准对象：[Stage 4 / 4A-3 四道门、利润分母与情景规则包 v0.1](Stage4_4A3四道门利润分母与情景规则包_v0.1.md)

原 draft 规格 SHA-256：`f2eef18f1a4c85fbc0587893beee4aea25f1d373a7f3482f23c0fbf08e08ea4c`

原 draft canonical bundle SHA-256：`03e0f6f4afb7de84185ee345b1a654fcaec48f4182a13ad8fbf65a2eae996393`

原 draft rules SHA-256：`62dcf735e166dfe49935ac5a325237716e931b5ec1cd166b0b949122fb5dd5e2`

## 1. Owner 明确批准

owner 于 `2026-08-08` 明确批准：

> 批准《Stage 4 / 4A-3 四道门、利润分母与情景规则包 v0.1》第 9 节全部 20 项，仅授权 stage4_synthetic_research_validation，不授权 backtest、paper、shadow、live、仓位或订单

该批准只覆盖原 draft 规格第 9 节的二十项精确语义。原 draft 文档和 draft machine proposal 保持不变；approved machine bundle 和 approval record 另行生成，禁止原位把 draft 改写为 approved。

## 2. 批准边界

```text
scope = stage4_synthetic_research_validation
run_mode = research
validation_only = true
input = InvestSystem-owned anonymous synthetic fixture
runtime_capability = exact 4A-3 bundle only
full_stage4_capability = false
backtest = false
paper = false
shadow = false
live = false
positions = false
orders = false
```

`SHADOW_ONLY` 只能作为研究结果标签，不能解释为 shadow 运行权限。4A-3 只允许局部运行 Gate 1—2 和利润/情景规则；Gate 3—4 固定为 `not_evaluated`，不得产生 `TRADE_READY`、完整 DecisionState、仓位或订单。

## 3. 批准项

### FR-GATE-001

- [x] `4A3-APPROVAL-001`：四道门固定顺序、前门非 PASS 后短路及“未评估不等于失败/通过”。
- [x] `4A3-APPROVAL-002`：Gate 1 只组合精确 4A-1/4A-2 结果，不重新解释或补写 KB Fact。
- [x] `4A3-APPROVAL-003`：Gate 1 的 `BLOCKED/REJECT/ABSTAIN/SHADOW_ONLY/PASS` 映射和两条独立证据链条件。
- [x] `4A3-APPROVAL-004`：GateResult 分离 `evaluation_state` 与 `outcome`，固定结果优先级和 reason/evidence lineage。
- [x] `4A3-APPROVAL-005`：4A-3 只运行 Gate 1—2；Gate 3—4 固定未评估，禁止 `TRADE_READY` 和完整 Stage 4 capability。

### FR-GATE-002

- [x] `4A3-APPROVAL-006`：从 E4 首次公开日开始的连续十二个月半开 NTM 区间、PIT 截面、列报币种/外汇换算、统一单位和固定点十进制。
- [x] `4A3-APPROVAL-007`：公司级 bottom-up 反事实利润逐项公式、非负减项和有符号净财务成本口径；一致预期/TTM 只作交叉验证。
- [x] `4A3-APPROVAL-008`：排除目标事件和非经常项目、禁止重复计价；计算图确定包含事件/重复计价为 `BLOCKED`，合法材料不足以量化剔除额为 `ABSTAIN`。
- [x] `4A3-APPROVAL-009`：用确定性区间算术得到的 base/downside/支持区间 lower 均严格大于零定义 `standard_track`，不设跨公司固定“接近零”阈值。
- [x] `4A3-APPROVAL-010`：完整但区间触零/跨零/为负进入 `fragile_profit_shadow_track`，不计算重要性比率；区间不可建立为 `ABSTAIN`。
- [x] `4A3-APPROVAL-011`：事件 NTM 增量归母标准化利润与增量 FCF 的精确公式，并把融资成本纳入利润桥。
- [x] `4A3-APPROVAL-012`：`0.10` 仅作为 Stage 4 合成研究验证 Gate 2 阈值，等号通过、只有上行达标为 `REJECT`。
- [x] `4A3-APPROVAL-013`：Gate 2 PASS 还要求基准增量利润和 FCF 均严格大于零；利润达标但 FCF `<=0` 为研究标签 `SHADOW_ONLY`。

### FR-GATE-003

- [x] `4A3-APPROVAL-014`：base/downside/upside/stress 四情景必需且定义互不替代。
- [x] `4A3-APPROVAL-015`：统一 driver schema、显式继承、变化项因果依据以及禁止逐变量挑选最有利值。
- [x] `4A3-APPROVAL-016`：四情景公式/口径一致、upside/base/downside 利润顺序，以及压力情景至少一个指定资本风险指标严格恶化和其他表面改善的显式 reason code。
- [x] `4A3-APPROVAL-017`：无约束复购、扩产、份额或涨价在新约束事实出现前只能进入上行情景。
- [x] `4A3-APPROVAL-018`：情景概率默认可空；一旦使用，base/downside/upside 全有、合计 `1.000000`、有校准来源，stress 无概率且概率不得补偿 Gate。
- [x] `4A3-APPROVAL-019`：四情景/必需 driver 缺失为 `ABSTAIN`，未来信息、隐藏默认、单位/hash/依赖硬失败为 `BLOCKED`。
- [x] `4A3-APPROVAL-020`：情景集 append-only 版本、supersedes、固定输入迁移重放和零 KB 写回/零交易权限。

## 4. 实现约束

- runtime 只读取 approved machine bundle，不解析本 Markdown；
- typed capability 必须绑定精确 bundle hash、approval ID、approval record hash、scope 和已批准 4A-1/4A-2 上游 bundle；
- 默认 registry 保持为空，调用方必须显式注入 approval record；
- 任一 hash、scope、依赖、PIT、单位、公式、scenario set 或 replay 漂移都必须失败关闭；
- 每项规则必须有正例、反例、边界例和 `ABSTAIN`，并覆盖 `SHADOW_ONLY/BLOCKED`；
- 本批准不证明 `0.10` 或其他规则具有历史有效性，也不授权使用真实 KB 输入、回测或交易。

## 5. 未批准事项

- `FR-GATE-004/005`、`FR-EXIT-001`；
- 完整 Stage 4 bundle、完整策略引擎和完整 DecisionState；
- backtest、paper、shadow、live、TargetPortfolio、仓位、订单、成交和 P&L；
- Stage 3 真实 KB transport/current-status/Context Pack smoke；
- 对题材扩散与资金轮动系统的任何信号或规则复用。
