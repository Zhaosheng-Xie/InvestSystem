# 规则与规格

下一阶段在此冻结可机器执行的规则。首个纵向切片应先批准最小规则包，再扩展完整策略。建议顺序：

Stage 2B 已完成并通过[正式验收](../../docs/validation/stage2b-acceptance.md)。owner 明确确认首个最小规则包全部 22 项，并以精确 canonical machine bundle 和 `RuleApprovalRecord` 登记；策略组合点只接受该记录签发的精确 capability，通用默认 registry 继续为空。批准严格限于 `stage2b_synthetic_validation`，只允许 `research` + `validation_only=true`，不授权 backtest、paper、shadow、live、仓位或订单。

- [最小订单合同纵向切片规则包 v0.1](最小订单合同纵向切片规则包_v0.1.md)：`approved / implemented for stage2b_synthetic_validation only`。
- [机器 rule bundle](机器制品/industrial_event_minimum_order_contract_slice_v0.1.0.rule-bundle.json)：完整确定语义和授权边界的 canonical 运行制品；Markdown binding 只供追踪，运行时不得解析 Markdown。
- [RuleApprovalRecord](机器制品/industrial_event_minimum_order_contract_slice_v0.1.0.approval.json)：精确绑定 strategy、bundle、version、hash、批准人、时间、scope 和来源记录。

Stage 4 已完成四个局部执行批次和独立 4B 完整合成编排：

- [Stage 4 完整 P0 规则清单与批准包 v0.1](Stage4完整P0规则清单与批准包_v0.1.md)：`all_14_p0_rules_approved`；
- [4A-1 上下文与产业映射规则包](Stage4_4A1上下文与产业映射规则包_v0.1.md)：四条规则已绑定精确 [machine bundle](机器制品/industrial_event_stage4_4a1_context_industry_v0.1.0.rule-bundle.json) 和 [approval record](机器制品/industrial_event_stage4_4a1_context_industry_v0.1.0.approval.json)；
- [4A-2 事件状态与审计分层规则包](Stage4_4A2事件状态与审计分层规则包_v0.1.md)及 [draft machine proposal](机器制品/industrial_event_stage4_4a2_event_semantics_v0.1.0-draft.rule-bundle.json)：作为获批前的不可变提案保留；
- [4A-2 批准记录](Stage4_4A2事件状态与审计分层批准记录_v0.1.md)、[approved machine bundle](机器制品/industrial_event_stage4_4a2_event_semantics_v0.1.0.rule-bundle.json)和 [approval record](机器制品/industrial_event_stage4_4a2_event_semantics_v0.1.0.approval.json)：精确固定全部 16 项批准及零交易权限；
- [4A-3 四道门、利润分母与情景规则包](Stage4_4A3四道门利润分母与情景规则包_v0.1.md)及 [draft machine proposal](机器制品/industrial_event_stage4_4a3_gate_profit_scenarios_v0.1.0-draft.rule-bundle.json)：作为获批前的不可变提案保留；
- [4A-3 批准记录](Stage4_4A3四道门利润分母与情景批准记录_v0.1.md)、[approved machine bundle](机器制品/industrial_event_stage4_4a3_gate_profit_scenarios_v0.1.0.rule-bundle.json)和 [approval record](机器制品/industrial_event_stage4_4a3_gate_profit_scenarios_v0.1.0.approval.json)：精确固定全部 20 项批准、4A-1/4A-2 上游身份和零交易权限；
- [4A-4 市场预期、估值与退出规则包](Stage4_4A4市场预期估值与退出规则包_v0.1.md)及 [draft machine proposal](机器制品/industrial_event_stage4_4a4_expectation_valuation_exit_v0.1.0-draft.rule-bundle.json)：作为获批前的不可变提案保留；
- [4A-4 批准记录](Stage4_4A4市场预期估值与退出批准记录_v0.1.md)、[approved machine bundle](机器制品/industrial_event_stage4_4a4_expectation_valuation_exit_v0.1.0.rule-bundle.json)和 [approval record](机器制品/industrial_event_stage4_4a4_expectation_valuation_exit_v0.1.0.approval.json)：精确固定全部 24 项批准、4A-1—4A-3 上游身份和零交易权限；
- [Stage 4 P0 machine inventory](机器制品/industrial_event_stage4_p0_rule_inventory_v0.1.0-draft.json)：14 项完整清单现均为 `approved`；
- [4B 完整引擎集成与合成验收规则包](Stage4_4B完整引擎集成与合成验收规则包_v0.1.md)及 [draft machine proposal](机器制品/industrial_event_stage4_4b_complete_engine_integration_v0.1.0-draft.rule-bundle.json)：作为获批前的不可变提案保留；
- [4B 批准记录](Stage4_4B完整引擎集成与合成验收批准记录_v0.1.md)、[approved machine bundle](机器制品/industrial_event_stage4_4b_complete_engine_integration_v0.1.0.rule-bundle.json)和 [approval record](机器制品/industrial_event_stage4_4b_complete_engine_integration_v0.1.0.approval.json)：精确固定全部 16 项批准、四批上游身份、完整 inventory 与零真实/交易权限；
- `stage4_synthetic_research_validation` 是独立 scope，Stage 2B capability 不能复用；只有精确 4B capability 可编排完整匿名合成 Stage 4，四个局部 capability 不能替代它。

1. `KB输入引用与失败关闭规格_v0.1.md`
2. `StrategyRunManifest与决策审计规格_v0.1.md`
3. `E3.5_E4状态机与阻断规则_v0.1.md`
4. `产业卡点字段与利润传导_v0.1.md`
5. `四道门与ABSTAIN规则_v0.1.md`
6. `情景估值与证伪规则_v0.1.md`
7. `风险与目标仓位政策_v0.1.md`
8. `A股成交规则版本表_v0.1.md`

规则只有在标记为 `approved`、通过对应测试且 approval scope 明确包含目标运行模式时，才可进入该模式。本规则包的 scope 不包含回测。

KB 只提供已发布事实、证据引用和 Context Pack，不提供 E0—E7、Gate、利润桥或估值结论。任何规则不得依赖 KB SQLite、`raw/`、`staging/` 或内部实现，也不得把策略判断写回 KB。

