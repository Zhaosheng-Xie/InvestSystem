# Stage 4 完整 P0 规则清单与批准包 v0.1

文档状态：`all_14_p0_rules_approved / 4B complete integration draft pending`

阶段：`Stage 4 / 4A rule governance`

目标批准范围：`stage4_synthetic_research_validation`

当前授权：`4A-1—4A-4 exact local approvals only；完整 Stage 4 capability 未签发`

当前运行权限：`research development only；不授权 backtest、paper、shadow、live、仓位或订单`

## 1. 目的

本包把 PRD v0.3 中由 Stage 4 负责的 P0 策略规则收敛为一个完整、可逐项审阅的清单。它只建立规则所有权、批准门和测试证据要求，不自行批准任何业务语义，也不复用 Stage 2B 的窄规则 capability。

Stage 3 已按 owner 决定暂缓；Stage 4 继续只使用 provider-neutral、明确标记的合成输入开发。真实 KB HTTP/export/current-status、正式 Context Pack smoke 和真实 authority 仍属于 Stage 3，不能从本包获得替代实现。

## 2. 权限边界

| 能力 | 当前值 |
|---|---:|
| `research` 合成规则开发 | 允许 |
| 4A-1 局部规则 capability | 已签发，仅精确合成 research validation |
| 4A-2 局部规则 capability | 已签发，仅精确合成 research validation |
| 4A-3 局部规则 capability | 已签发，仅精确合成 research validation |
| 4A-4 局部规则 capability | 已签发，仅精确合成 research validation |
| 完整 Stage 4 规则 capability | 未签发 |
| `backtest` | 不授权 |
| `paper` | 不授权 |
| `shadow` | 不授权 |
| `live` | 不授权 |
| TargetPortfolio / 仓位 | 不授权 |
| 订单 / 资金部署 | 不授权 |

新增 `stage4_synthetic_research_validation` scope 只让契约能够表达未来的精确批准，不产生任何默认权限。通用 production registry 继续为空。只有完整清单、完整 machine bundle 和 owner 对其 canonical hash 的精确批准同时成立时，才可签发 Stage 4 capability。

## 3. 阶段所有权

Stage 4 包含产业上下文、产业/可投资卡点、E0—E7、四道门的策略语义、利润桥、情景、预期、估值、证伪和退出判断。

以下内容不在本包中：

- Stage 3：真实 KB transport、current-status authority、正式 Context Pack smoke；
- Stage 5：首次可成交价格机制、T+1/涨跌停/停牌、费用、滑点、容量、风险预算、组合、仓位、订单、成交与 P&L；
- Stage 6：历史回测、walk-forward、holdout 和冠军挑战。

## 4. 批准完成门

每一项 P0 规则只有同时具备以下证据才能标记为 `approved`：

1. 精确版本的文字规格；
2. owner approval ID；
3. canonical machine rule 引用；
4. 正例、反例、边界例和 `ABSTAIN` 测试引用；
5. 明确 PIT、证据、冲突、失败和迁移语义。

完整 Stage 4 rule bundle 还必须绑定本清单的 canonical hash、全部 14 个规则 ID 和零交易权限边界。缺一项、增一项、状态不是 `approved`、清单漂移或复用 Stage 2B scope 时均失败关闭。

## 5. P0 清单

| ID | 规则域 | 当前状态 | 建议批准批次 |
|---|---|---|---|
| `FR-CTX-001` | 固定输入上的 `IndustryContextView` 准入 | `approved` | 4A-1 |
| `FR-CTX-002` | 历史产业上下文版本与禁止后见回填 | `approved` | 4A-1 |
| `FR-IND-001` | 产业卡点判定 | `approved` | 4A-1 |
| `FR-IND-002` | technical / qualified / profit beneficiary 映射 | `approved` | 4A-1 |
| `FR-EVT-001` | E0—E7 / E3.5 状态转换与迁移 | `approved` | 4A-2 |
| `FR-EVT-002` | 完整 `E4_public` 独立判定 | `approved` | 4A-2 |
| `FR-EVT-003` | 供应商、客户和采购端事实关联 | `approved` | 4A-2 |
| `FR-EVT-004` | Fact / Assumption / Derived / Judgment 分层 | `approved` | 4A-2 |
| `FR-GATE-001` | 四道门 AND、短路和三值语义 | `approved` | 4A-3 |
| `FR-GATE-002` | 反事实 NTM 标准化利润分母 | `approved` | 4A-3 |
| `FR-GATE-003` | 基准/下行/上行/压力情景 | `approved` | 4A-3 |
| `FR-GATE-004` | 市场预期重建 | `approved` | 4A-4 |
| `FR-GATE-005` | 基础业务与事件增量 FCF 估值 | `approved` | 4A-4 |
| `FR-EXIT-001` | 证据/风险/时间/价值退出判断 | `approved` | 4A-4 |

## 6. 逐项规则状态

4A-1 四项的精确语义已由 [4A-1 规则包](Stage4_4A1上下文与产业映射规则包_v0.1.md)及其 canonical machine bundle 固定。4A-2 四项由[原 draft 规则包](Stage4_4A2事件状态与审计分层规则包_v0.1.md)、[批准记录](Stage4_4A2事件状态与审计分层批准记录_v0.1.md)及其 approved canonical machine bundle 固定。4A-3 三项由[原 draft 规则包](Stage4_4A3四道门利润分母与情景规则包_v0.1.md)、[批准记录](Stage4_4A3四道门利润分母与情景批准记录_v0.1.md)及其 approved canonical machine bundle 固定。4A-4 三项由[原 draft 规则包](Stage4_4A4市场预期估值与退出规则包_v0.1.md)、[批准记录](Stage4_4A4市场预期估值与退出批准记录_v0.1.md)及其 approved canonical machine bundle 固定，并已实现局部 evaluator。14 项 inventory 现均为 `approved`；完整引擎的组合顺序、输入身份、结论优先级和 replay 合同另由[4B 规则包](Stage4_4B完整引擎集成与合成验收规则包_v0.1.md)、[批准记录](Stage4_4B完整引擎集成与合成验收批准记录_v0.1.md)及独立 approved machine bundle 固定。完整 4B capability 只允许匿名合成 research validation，不授予任何真实或交易权限。

### FR-CTX-001

冻结 `IndustryContextView` 的最低字段、证据覆盖和 `decision_pool` 准入。必须决定“字段未知但可研究”与“P0 输入不完整而阻断”的精确分界；代码不得用 LLM、行业均值或本地 KB 状态补齐。

### FR-CTX-002

冻结历史上下文版本选择、`as_of`、知识截止时间、产业分期和迁移规则。必须禁止用 2026 年产业地图、公司标签或供应链关系回填旧 run。

### FR-IND-001

冻结需求可核验、供给响应慢、替代受限、稀缺持续窗口和瓶颈消失领先信号的字段、三值逻辑、冲突处理和证据独立性。PRD 的问题清单不自动等于已批准 machine pass 条件。

### FR-IND-002

冻结 `technical_link → qualified_supplier → profit_beneficiary` 的晋级条件、所有权路径、份额/价格/增量毛利/现金回收证据和降级规则。只有 `profit_beneficiary` 可以进入四道门，但具体字段完整性仍须批准。

### FR-EVT-001

冻结 E0—E7、E3.5 的合法转换、降级、重复事件、冲突、同一事件修订、版本迁移和不允许跳级的事实覆盖。事件状态、决策状态与持仓状态必须分离。

### FR-EVT-002

在 Stage 2B 窄订单/合同路径之外，冻结完整 `E4_public` 的主体、签署、正式下达、生效条件、最低经济义务、取消/退货/验收和多证据链规则。保密导致金额未知时仍必须保留 `ABSTAIN`。

### FR-EVT-003

冻结供应商、客户、采购端、上市公司主体和最早合法公开事实之间的关联规则，明确同源转述、间接证据、主体歧义和冲突的处理。

### FR-EVT-004

冻结 Fact、Assumption、Derived、Judgment 的字段、来源、`as_of`、情景、证伪和引用规则。策略派生不得覆盖 KB Fact，也不得把 Judgment 反写为事实。

### FR-GATE-001

冻结四道门 AND、固定顺序、短路、`REJECT/ABSTAIN/SHADOW_ONLY/BLOCKED` 的层级和跨门引用。Stage 2B 行为可作为候选基线，但不能自动获得 Stage 4 批准。

### FR-GATE-002

冻结 E4 前反事实 NTM 标准化归母利润、非经常项、正且稳健的 `standard_track` 判定、接近零/易翻正负的边界和 `fragile_profit_shadow_track`。`10%` 门槛若沿用也必须在 Stage 4 scope 重新批准。

### FR-GATE-003

冻结三情景及压力情景的承重变量、经济一致性、触发器、证伪、概率使用和缺失字段语义。无约束复购不得进入基准。

### FR-GATE-004

冻结 `unexpected/partially_priced/fully_priced/unknown` 的观察窗口、最低材料、价格/成交量用途、冲突和历史不可恢复处理。无法恢复先验预期时必须 `ABSTAIN`。

### FR-GATE-005

冻结基础业务价值、有限期事件增量 FCF、倍数/折现率、价值区间、复购和防重复计价规则。首次可成交价格和真实交易成本由 Stage 5 提供，Stage 4 不自行实现成交假设。

### FR-EXIT-001

冻结 evidence/risk/time/value 四类退出判断、proof window、重新承保和价值更新语义。Stage 4 只产生策略退出判断；订单生成、可成交退出和账本属于 Stage 5。

## 7. 推荐实施顺序

1. 4A-1：上下文与产业/受益公司映射；
2. 4A-2：完整事件状态机和审计分层；
3. 4A-3：Gate 1—2、利润桥与四情景；
4. 4A-4：预期、估值、证伪与退出；
5. 审阅并批准 4B 完整引擎集成与合成验收规则包；
6. 形成独立、精确批准的完整 Stage 4 machine bundle；
7. 只在 `stage4_synthetic_research_validation` 中运行完整 synthetic golden/replay。

任何批次的局部批准只允许开发和验证该批次，不能签发完整 Stage 4 engine capability。完整 capability 必须等 14 项全部批准。
