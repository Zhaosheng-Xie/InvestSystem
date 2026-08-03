# 规则与规格

下一阶段在此冻结可机器执行的规则。首个纵向切片应先批准最小规则包，再扩展完整策略。建议顺序：

Stage 2B 已完成并通过[正式验收](../../docs/validation/stage2b-acceptance.md)。owner 明确确认首个最小规则包全部 22 项，并以精确 canonical machine bundle 和 `RuleApprovalRecord` 登记；策略组合点只接受该记录签发的精确 capability，通用默认 registry 继续为空。批准严格限于 `stage2b_synthetic_validation`，只允许 `research` + `validation_only=true`，不授权 backtest、paper、shadow、live、仓位或订单。

- [最小订单合同纵向切片规则包 v0.1](最小订单合同纵向切片规则包_v0.1.md)：`approved / implemented for stage2b_synthetic_validation only`。
- [机器 rule bundle](机器制品/industrial_event_minimum_order_contract_slice_v0.1.0.rule-bundle.json)：完整确定语义和授权边界的 canonical 运行制品；Markdown binding 只供追踪，运行时不得解析 Markdown。
- [RuleApprovalRecord](机器制品/industrial_event_minimum_order_contract_slice_v0.1.0.approval.json)：精确绑定 strategy、bundle、version、hash、批准人、时间、scope 和来源记录。

Stage 4 已完成首个规则批次，完整 capability 仍关闭：

- [Stage 4 完整 P0 规则清单与批准包 v0.1](Stage4完整P0规则清单与批准包_v0.1.md)：`partially_approved / 4A-1 completed`；
- [4A-1 上下文与产业映射规则包](Stage4_4A1上下文与产业映射规则包_v0.1.md)：四条规则已绑定精确 [machine bundle](机器制品/industrial_event_stage4_4a1_context_industry_v0.1.0.rule-bundle.json) 和 [approval record](机器制品/industrial_event_stage4_4a1_context_industry_v0.1.0.approval.json)；
- [Stage 4 P0 machine inventory](机器制品/industrial_event_stage4_p0_rule_inventory_v0.1.0-draft.json)：14 项完整清单，前 4 项 `approved`，其余 10 项 `draft`；
- `stage4_synthetic_research_validation` 是独立 scope，Stage 2B capability 不能复用；4A-1 只允许局部合成验证，不能签发完整 Stage 4 runtime capability。

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

