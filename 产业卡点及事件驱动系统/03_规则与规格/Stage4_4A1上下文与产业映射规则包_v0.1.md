# Stage 4 / 4A-1 上下文与产业映射规则包 v0.1

文档状态：`approved`

批准范围：`stage4_synthetic_research_validation`

批准来源：本仓库 owner 于 `2026-08-03` 在当前 Codex 任务中确认“批准继续”

包含规则：`FR-CTX-001`、`FR-CTX-002`、`FR-IND-001`、`FR-IND-002`

权限：仅允许显式合成输入上的 `research / validation_only`；不授权 `backtest`、`paper`、`shadow`、`live`、仓位、组合、订单或资金部署

## 1. 目的与边界

本包把 Stage 4 的首批四条规则固定为可执行、可重放、可审计的机器语义。它只回答：

1. 指定时点的产业上下文能否进入 `decision_pool`；
2. 是否发生历史语义或 PIT 污染；
3. 产业节点是否构成卡点；
4. 目标上市公司处于 `technical_link`、`qualified_supplier` 或 `profit_beneficiary` 哪一层。

本包不实现或替代：

- Stage 3 的真实 KB HTTP/export、current-status authority 和正式 Context Pack smoke；
- E0—E7、四道门、利润桥、市场预期、估值或退出；
- Stage 5 的可成交价格、风险、组合、仓位、订单、成交和 P&L；
- Stage 6 的历史验证。

输入只能是 provider-neutral、明确标记为合成且非 Published Release 的 fixture。实现不得读取 KB SQLite、`raw/`、`staging/`、KB 源包或本地活动状态，也不得解析 Markdown 决定运行语义。

## 2. 公共语义

### 2.1 证据结论

每个判断字段必须显式处于以下四态之一：

| 状态 | 含义 |
|---|---|
| `confirmed` | 固定输入中的事实直接支持该命题 |
| `refuted` | 固定输入中的事实直接反驳该命题 |
| `unknown` | 固定输入不足以支持或反驳，不得补值 |
| `conflicted` | 固定输入中存在影响结论的相互冲突证据 |

`confirmed/refuted` 必须有 `supporting_fact_ids` 和 `independence_group_ids`；`conflicted` 必须同时有 supporting/conflicting facts。`unknown` 不是 `false`，也不是零。

`independence_group_id` 表示经消费边界确认不属于同一来源转述、同一采集链或同一派生谱系的证据组。实现只消费该 provider-neutral 标识，不自行判断 KB 内部血缘。

### 2.2 结果与优先级

| 结果 | 含义 |
|---|---|
| `PASS` | 本规则的全部准入条件成立 |
| `REJECT` | 存在足以否决的明确反证或不满足项 |
| `ABSTAIN` | 未知、冲突或证据独立性不足，无法安全判断 |
| `BLOCKED` | 输入结构、PIT、历史版本或授权边界失效，禁止继续评估 |

同一规则中优先级为 `BLOCKED > REJECT > ABSTAIN > PASS`。组合执行顺序为 `FR-CTX-002 → FR-CTX-001 → FR-IND-001 → FR-IND-002`；前一项非 `PASS` 时后续项标记 `not_evaluated`，不得在污染或不完整上下文上继续推断。

### 2.3 禁止推断

代码、LLM、行业均值、当前标签和本地 KB 状态均不得把 `unknown/conflicted` 改为 `confirmed/refuted`。任何人工覆盖都需要新的规则版本、输入和批准记录，不能修改既有 run。

## 3. IndustryContextView 准入

### FR-CTX-001

### 3.1 必需覆盖域

每个 `IndustryContextView` 必须恰好记录以下十个覆盖域，不得缺项或重复：

1. `product_technology_terms`；
2. `value_chain_relations`；
3. `demand_procurement_deployment`；
4. `commercialization_cycles`；
5. `capacity_yield_leadtime_price_cost_inventory`；
6. `competition_switching_new_supply`；
7. `profit_pool_ownership_path`；
8. `historical_stage_counterexamples_conflicts`；
9. `source_time_version_confidence_review`；
10. `company_identity_exclusion_review_trigger`。

### 3.2 判定

- 缺少 Context Pack 精确引用、版本、公司标识、`as_of` 或任一覆盖域：`BLOCKED`；
- 公司未预注册：`REJECT`，进入 `research_quarantine`；
- 任一覆盖域为 `unknown/conflicted`：`ABSTAIN`，进入 `research_quarantine`；
- 十个覆盖域全部 `confirmed` 且公司已预注册：`PASS`，进入 `decision_pool`；
- 覆盖域不得使用 `refuted`，因为本规则判断的是覆盖是否充分，而不是业务命题真假。

`decision_pool` 仅表示具备继续研究的上下文资格，不表示卡点、受益、四道门或交易资格。

## 4. 历史上下文与禁止后见回填

### FR-CTX-002

### 4.1 必需时间绑定

上下文必须恰好包含以下三类时点绑定：

- `industry_stage`；
- `company_label`；
- `supply_chain_relation`。

每个已确认绑定必须保存 `semantic_id`、`available_at`、`valid_from`、可选的排他 `valid_to`、事实引用和证据独立组。

### 4.2 判定

必须同时满足：

```text
context_pack_available_at <= knowledge_cutoff <= decision_at
as_of <= knowledge_cutoff
valid_from <= as_of < valid_to
```

当 `valid_to = null` 时表示开区间上界。边界采用半开区间：`as_of == valid_from` 合法，`as_of == valid_to` 非法。

- 时间绑定缺项、未来可用事实、`as_of` 超过知识截止、知识截止晚于决策时间、或绑定有效期不覆盖 `as_of`：`BLOCKED`；
- 任一绑定为 `unknown/conflicted`：`ABSTAIN`；
- 三类绑定均为 `confirmed` 且满足全部时间关系：`PASS`；
- 禁止选择“当前最新”标签后回填历史 run；历史不可恢复必须保留 `unknown → ABSTAIN`。

## 5. 产业卡点判定

### FR-IND-001

### 5.1 五个必需命题

1. `verifiable_demand`：需求变化有可核验事实，不是只有市场空间叙事；
2. `slow_supply_response`：认证、设备、工艺、良率、牌照或客户切换使供给响应变慢；
3. `constrained_substitution`：替代路线真实受限；
4. `persistence_to_next_window`：稀缺可能持续至下一验证窗口；
5. `dissolution_signals_identified`：已定义可观察的瓶颈消失领先信号。

### 5.2 判定

- 前四个核心命题任一 `refuted`：`REJECT`；
- 前四项或消失信号任一 `unknown/conflicted`：`ABSTAIN`；
- 消失信号为 `refuted`（无法定义可观察信号）：`ABSTAIN`，不能把不可证伪命题当作卡点；
- 五项均 `confirmed`，且支持这些命题的独立证据组并集至少为 `2`：`PASS`；
- 五项均 `confirmed` 但独立证据组少于 `2`：`ABSTAIN`。

本规则不使用综合分数，也不允许一项强证据补偿另一项失败。

## 6. 上市公司受益映射

### FR-IND-002

### 6.1 晋级阶梯

| 层级 | 必需条件 | 四道门资格 |
|---|---|---:|
| `none` | `technical_link` 未确认 | 无 |
| `technical_link` | 技术或产品与卡点节点的关系已确认 | 无 |
| `qualified_supplier` | `technical_link` 与供应商资格均确认 | 仅研究 |
| `profit_beneficiary` | 在前两层基础上，份额、实现价格、增量毛利、现金回收和所有权路径全部确认 | 才可进入四道门 |

### 6.2 判定

- 下游层级为 `confirmed`、但上游前置层级不是 `confirmed`：结构矛盾，`BLOCKED`；
- `technical_link=refuted`：`none + REJECT`；
- `technical_link=unknown/conflicted`：`none + ABSTAIN`；
- `qualified_supplier=refuted`：`technical_link + REJECT`；
- `qualified_supplier=unknown/conflicted`：`technical_link + ABSTAIN`；
- 供应商资格确认后，五个利润归属命题任一 `refuted`：`qualified_supplier + REJECT`；
- 五个利润归属命题任一 `unknown/conflicted`：`qualified_supplier + ABSTAIN`；
- 五项均 `confirmed`，但其独立证据组并集少于 `2`：`qualified_supplier + ABSTAIN`；
- 五项均 `confirmed` 且至少有 `2` 个独立证据组：`profit_beneficiary + PASS`。

`profit_beneficiary + PASS` 只允许进入后续四道门；它不表示四道门通过、可回测、可交易或可建仓。

## 7. 机器制品与批准身份

运行时只接受规范 JSON 规则包及其精确 owner approval：

- `机器制品/industrial_event_stage4_4a1_context_industry_v0.1.0.rule-bundle.json`；
- `机器制品/industrial_event_stage4_4a1_context_industry_v0.1.0.approval.json`。

批准绑定完整规则包 canonical SHA-256；身份、版本、hash、scope 或授权边界任一漂移均失败关闭。Markdown 绑定仅用于追溯，不参与运行时解析。

## 8. 测试完成门

每条规则必须至少包含：

- 正例：完整证据下得到 `PASS`；
- 反例：明确反证或时间污染得到 `REJECT/BLOCKED`；
- 边界例：时间半开区间或恰好两个独立证据组；
- `ABSTAIN`：未知、冲突或证据独立性不足；
- 授权反例：错误 scope、hash 或交易权限必须失败关闭。

四条规则的局部批准不能签发完整 Stage 4 capability。其余十条仍为 `draft` 时，`require_stage4_rule_capability` 必须继续拒绝。
