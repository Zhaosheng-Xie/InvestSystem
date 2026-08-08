# Stage 4 / 4B 完整引擎集成与合成验收记录

> 验收日期：`2026-08-08`
>
> 验收状态：`completed_with_scope_limits`
>
> 验收分支：`codex/stage4b`
>
> 授权范围：`stage4_synthetic_research_validation`
>
> 不包含：真实 KB Release、backtest、paper、shadow、live、仓位、组合、成交、P&L 或订单

## 1. 验收结论

owner 已批准《Stage 4 / 4B 完整引擎集成与合成验收规则包 v0.1》第 9 节全部 16 项。仓库保留原 draft 与 draft machine proposal 不变，另建 approved 4B machine bundle、approval record、精确 capability verifier 和完整合成编排器。

`Stage4CompleteSyntheticCase` 只接受四批原始 typed 输入，不接受调用方提供的局部结果。编排器按固定顺序重新运行 4A-1、4A-2、4A-3、4A-4，再独立汇总退出；统一视图使用本次 4A-4 的 Gate 3—4，但不改写 4A-3 的历史局部结果。完整结果固定五层 capability 身份、四个局部结果及其 canonical hash、`input_hash`、统一 Gate 视图和排除 self-hash 的 `replay_hash`。

本验收只证明 14 项已批准规则可以在匿名、provider-neutral 合成输入上完整编排、失败关闭和确定性重放。研究标签 `TRADE_READY` 或 `SHADOW_ONLY` 不构成任何真实运行或交易授权。

## 2. 精确批准身份

| 项目 | SHA-256 |
|---|---|
| 4B owner-review 规格文件 | `d5c1ab50d76ea5d9444adcc92da24313b5ce5b51080c2e9258a5484a9417ca8d` |
| 原 draft canonical bundle | `2b845a6c4df0dc7e28779b0117409cd39b390cc304fb7bc54f9062c44697b44c` |
| 原 draft canonical rules | `1c7e8cb5acd89187e527a11be8f50baf77307b29561bf3a7fdc95bb32f3e1df9` |
| owner 批准记录文件 | `36a2d7722ee99af4c0fe90f16de0fdc978c39aadb6a7703661887dba0296964e` |
| approved canonical bundle | `ba8886cf85beef084c2a2d3b83446b499c7786fbc3f0e56066fb8cedc8e27e77` |
| approved canonical rules | `3477d237523ce84239ca1363ad1c8d2e467528ec90acb0034193aeb320740019` |
| approval record canonical hash | `d809394ef00beab2053795779878025fb1b3b0cd2a49da76302e500ef7f4b2fe` |
| 14 项全 approved inventory canonical hash | `fc07b10bb17d91b3447504fe7f5b2e346023fd98bb14da991e1a1dd85381bf53` |

approved 4B bundle 还逐批固定 4A-1—4A-4 的 bundle、rules 与 approval record hash。任一身份、scope、inventory、机器语义或权限字段漂移，均不能签发完整 capability。

## 3. 已实现行为

- 前置检查统一 `case_id`、公司、产业节点、逻辑事件、主体、`knowledge_cutoff`、E4 首次公开时间、币种、单位和经济期间；不一致时在任何局部 evaluator 前 `BLOCKED`。
- 禁止真实或可成交价格、真实 holding、KB current-status authority、KB 内部读取以及非 `research` 模式进入 4B。
- 4A-3 的上下文、事件结果与 4A-4 的上游 Gate 结果只能由本次运行产生，输入模型没有局部 PASS 注入字段。
- 结论优先级固定为 `BLOCKED → REJECT → ABSTAIN → SHADOW_ONLY → PASS`；只有四门及情景验证全部 `PASS` 才产生研究标签 `TRADE_READY`。
- Gate 2 的事件增量利润和 FCF 必须与传给 4A-4 的区间下界一致，否则在批次组合阶段失败关闭。
- 退出结果独立汇总；退出输入失败不回写 Gate，`EXIT_CANDIDATE` 不产生减仓、卖单或 P&L。
- 所有输出恒为 `FLAT`、空权重、空 approver、空订单意图、空正式 `StrategyRunManifest`，全部真实/交易权限恒为 false。

## 4. 合成验收覆盖

专项用例覆盖：

- 四批原始输入完整 PASS，以及 `0.10`、`0.15`、`2.00`、`120` 的精确等号边界；
- 4A-1、4A-2、Gate 1—4 的 `BLOCKED/REJECT/ABSTAIN/SHADOW_ONLY` 传播与短路；
- `HOLD`、`NOT_APPLICABLE` 和无效退出输入不改写 Gate；
- 跨 case、跨 cutoff、跨公司/节点/事件、KB 内部读取、非 research 模式和增量口径漂移失败关闭；
- 五层 capability 身份、四个局部结果 hash、统一规则 hash 与批准制品 hash 可追溯；
- 相同规范输入结果和 replay hash 完全一致，承重价格变化会改变 input/replay hash；
- 4A-1—4A-4 全部既有专项回归保持通过。

最终工程检查结果记录于本次提交的验证输出；Stage 4 专项为 `181 passed`，全仓为 `822 passed, 4 skipped`。四个 skip 仍来自当前 Windows 账户不能创建 symlink/junction 的既有平台限制，不是 Stage 4 逻辑跳过。

## 5. 结仓边界与后续依赖

Stage 4 现按“完整合成研究引擎已验收”结仓，但完整生产策略仍未实现。Stage 3C 需要真实 tcloud 只读传输，Stage 3D 需要精确正式 Context Pack Release、provider-neutral 映射、策略 smoke 和 authority 持久化；这些不由 4B 替代。

Stage 5 未启动。真实首次可成交价、市场规则、交易日历、风险预算、账户账本、仓位、组合、成交、P&L 和订单必须另行形成精确规则包并获得 owner 授权。
