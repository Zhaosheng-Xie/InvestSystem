# Stage 4 / 4B 完整引擎集成与合成验收规则包 v0.1

文档状态：`draft_for_owner_approval`

适用范围：`stage4_synthetic_research_validation`

前置状态：`4A-1—4A-4 的 14 项 P0 规则均已分别批准并实现局部 evaluator`

当前权限：`本草案不签发完整 Stage 4 capability；不授权 backtest、paper、shadow、live、仓位或订单`

## 1. 目的

本包只决定如何把四个已经批准的局部 evaluator 组合为一个确定性的完整 Stage 4 合成研究引擎，以及如何验收该组合。它不修改 4A-1—4A-4 的业务语义，不从文档运行规则，也不把局部批准自动外推为完整能力。

只有 owner 明确批准第 9 节全部 16 项后，才能生成独立的 approved 4B machine bundle、approval record 和完整引擎代码。即使 4B 获批，输出也仍只是匿名合成 research-validation 结论。

## 2. 精确上游基线

| 批次 | approved bundle SHA-256 | rules SHA-256 | approval record SHA-256 |
|---|---|---|---|
| `4A-1` | `5224e8e6d600b8f613d6dfaf4dd486d6caafdcf5fe3d8d3db29af2f25462a32d` | `2e16e87585bccc1df735e33feed4b72e3160d7bb1c415320bed31ee01c1d264a` | `84d47caa4b8226dd4e9c4dee31645214938e7321e25e93f368bf1ecc167b5e1a` |
| `4A-2` | `9f9f5cf843347a1918a894be1151c0ef720bd6318daa1077657e97e9324d6560` | `574dd4273c60081b099cf2c2427a2f264521f57ff16aa70b5ce1138ea9e8f228` | `57c5147ab93c7cf547f72347a7550f951c9ca2ad0cf97cb0755148bfa0d155ac` |
| `4A-3` | `e6936e9c236fd7ed3a67eb8c5e01cb02d23d8fa20c8fcd7a3ccbd615220619b2` | `146c8c497f529a0b7c675882522f4928877c96093449b5e0245fb6cfb71a05f0` | `786944b9263a7571632dbc5a2c92dcb1deb1431f8946f113ee883495dac5281a` |
| `4A-4` | `6ad34d6534b646eb0eb4fcab73c9da13e0738af0d3ae0d296143a48129ee1762` | `d1d2e03d78f0a78c63e073916da87f9177bb2e7151bd1d4d9ec959cd865545e2` | `8b75674537a9b8939cd259e2efb5a46752282714f19b23e181d9509ae09b919e` |

14 项 P0 inventory canonical SHA-256 固定为 `fc07b10bb17d91b3447504fe7f5b2e346023fd98bb14da991e1a1dd85381bf53`。任一上游 bundle、rules、approval record 或 inventory hash 变化，都必须拒绝旧 4B capability 并形成新版本。

## 3. 完整合成输入合同

完整输入必须是一个 InvestSystem 自有、provider-neutral、匿名的 `Stage4CompleteSyntheticCase`，并至少满足：

- 只允许一个 `case_id`、一个 `knowledge_cutoff` 和一条不可变输入版本链；四批输入不得各自指向不同研究对象。
- 4A-1 与 4A-2 接受各自原始 typed case；4A-3 的 `context_result`、`event_result` 和 `knowledge_graph` 必须由本次完整运行产生或直接绑定，调用方不得注入伪造的局部 PASS 结果。
- 4A-4 的 `upstream_gate_result` 必须由本次 4A-3 运行产生；调用方不得绕过 Gate 1—2 或替换结果。
- `case_id`、公司、产业节点、事件身份、主体、币种、单位、经济期间、`knowledge_cutoff` 和 E4 首次公开时间必须在适用输入之间一致；无法证明一致时为 `BLOCKED`。
- 输入只能来自匿名合成 fixture；不得携带 KB Release authority、真实市场可成交价、真实持仓、账户或订单状态。

完整输入投影必须使用规范 JSON 计算 `input_hash`。哈希覆盖四批全部原始输入及其版本/内容哈希，不覆盖运行时间、日志路径或进程信息。

## 4. 唯一执行顺序与短路

执行顺序固定为：

```text
校验 4B + 4A-1—4A-4 精确 capability
→ 校验完整输入身份与哈希
→ 运行 4A-1 上下文/产业映射
→ 运行 4A-2 事件/审计分层
→ 用本次两项结果运行 4A-3 Gate 1、情景与 Gate 2
→ 用本次 4A-3 结果运行 4A-4 Gate 3、Gate 4
→ 独立汇总 4A-4 退出判断
→ 生成完整合成结果与 replay hash
```

4A-1 与 4A-2 是同一输入快照上的独立前置评估，可以依次计算，但不得互相改写。4A-3 负责固定的 Gate 1 → 情景 → Gate 2 短路；4A-4 只能在上游允许时评估 Gate 3 → Gate 4。未评估的规则必须显式输出 `not_evaluated` 和原因，不能以默认 PASS 补齐。

4A-3 结果中的 Gate 3—4 占位只表示“尚未由该批次评估”。完整输出必须以本次 4A-4 的 Gate 3—4 结果替换显示层占位，但不得改写 4A-3 的历史局部结果。

## 5. 完整结果与结论优先级

完整结果至少保存：

- `case_id`、`input_hash`、完整 bundle/approval 身份和四个局部 bundle/approval 身份；
- 四个不可变局部结果及其 canonical hash；
- Gate 1—4 的统一视图、情景验证、利润轨、预期分类、估值指标与退出判断；
- `overall_outcome`、`research_decision_label`、原因码、`replay_hash`；
- 所有交易权限恒为 false，仓位恒为 `FLAT`，订单意图和实际权重恒为空。

进入结论的优先级固定为：结构/治理/身份/哈希错误 `BLOCKED`；否则任一道已评估 Gate 为 `BLOCKED` 时 `BLOCKED`；否则任一道为 `REJECT` 时 `REJECT`；否则任一道为 `ABSTAIN` 时 `ABSTAIN`；只有 Gate 1—4 全部 `PASS` 才可输出研究标签 `TRADE_READY`。`SHADOW_ONLY` 只保留既有 fragile profit 研究语义，不授权 shadow 运行，也不能等价于四门全 PASS。

退出判断与新进入结论分开汇总：退出输入无持仓时为 `NOT_APPLICABLE`；退出输入自身无效只阻断退出判断，不能追溯改写同次 Gate 1—4。任何 `EXIT_CANDIDATE` 都只是研究标签，不生成减仓、卖单或 P&L。

## 6. 确定性 replay

`replay_hash` 必须至少绑定：

- 4B 完整 bundle hash、approval record hash 和 inventory hash；
- 四个局部 bundle、rules、approval record hash；
- 完整 `input_hash`；
- 四个局部结果 hash 和最终统一结果中除 `replay_hash` 自身之外的规范内容。

相同规范输入、相同五个 capability 与相同代码版本必须得到相同结果和 replay hash。规则、事实、假设、价格、估值、proof window、holding snapshot 或任一上游结果变化都必须改变相应哈希。时间戳、进程号、机器路径、字典插入顺序不得影响结果。

## 7. 合成验收矩阵

验收必须覆盖全部 14 项规则及集成边界，至少包括：

- 正例：四门精确 PASS、`TRADE_READY` 仅为研究标签，退出分别为 `NOT_APPLICABLE` 与 `HOLD`；
- 反例：4A-1、4A-2、Gate 1—4 各自失败的短路位置和最终 `REJECT/BLOCKED`；
- 边界例：`0.10`、`0.15`、`2.00`、`120` 等已批准等号边界，以及区间接触和零 downside loss；
- `ABSTAIN`：材料缺失、冲突、不可比较、未知预期、估值不可靠和适用退出输入未知；
- 防伪：伪造局部 PASS、错误 capability/hash、跨 case、跨截止时间、真实价格、KB 内部依赖和交易权限漂移全部失败关闭；
- replay：相同输入确定性一致，每类承重输入变化均改变 hash；
- 回归：4A-1—4A-4 全部现有专项测试保持通过，完整集成不改变局部 evaluator 输出。

本阶段只运行 synthetic golden/replay，不运行历史行情回测，不使用真实 KB Release，不计算成交、仓位、组合、P&L 或订单。

## 8. 权限与仓库边界

- 运行模式唯一允许值为 `research`，且同时要求 `synthetic=true`、`validation_only=true`、`not_a_published_release=true`。
- 4B 不能签发 KB current-status authority，也不能保存为正式 `StrategyRunManifest`；正式 Release 消费仍由 Stage 3D 及后续运行合同负责。
- 不读取 KB SQLite、`raw/`、`staging/`、工作树或内部 Python 包，不向 KB 写回任何策略逻辑。
- 不实现首次可成交价、交易日历维护、风险预算生成、账户账本、仓位、组合、成交、P&L 或订单；这些属于 Stage 5 及更晚且需单独授权。
- 4B approved capability 必须是独立批准的完整 bundle capability。四个局部 capability、全 approved inventory 或本草案本身均不能替代它。

## 9. Owner 批准项

请逐项批准、修改或拒绝：

1. `4B-01`：完整引擎精确固定第 2 节四个 approved bundle、rules、approval record hash 和 inventory hash；任一漂移均失败关闭。
2. `4B-02`：4B 只编排既有 14 项语义，不修改、合并或自行补充 4A-1—4A-4 业务规则。
3. `4B-03`：必须另有独立的 approved 4B machine bundle、approval record 和 capability；局部批准不能自动外推。
4. `4B-04`：完整输入只允许一个 case/截止时间/版本链，并强制公司、产业节点、事件、主体、币种、单位和期间一致。
5. `4B-05`：4A-3 的上下文/事件结果和 4A-4 的上游 Gate 结果必须由本次运行产生，禁止调用方注入局部 PASS。
6. `4B-06`：执行顺序固定为 4A-1 → 4A-2 → 4A-3 → 4A-4 → 退出汇总，并保留已批准短路语义。
7. `4B-07`：未评估规则必须显式 `not_evaluated`，不得用默认值、得分或其他门补偿为 PASS。
8. `4B-08`：完整显示层使用 4A-4 Gate 3—4 结果，但不改写 4A-3 的不可变局部结果。
9. `4B-09`：最终 Gate 结论优先级固定为 `BLOCKED → REJECT → ABSTAIN → PASS`；四门全 PASS 才能输出研究标签 `TRADE_READY`。
10. `4B-10`：`SHADOW_ONLY` 仅保留 fragile-profit 研究语义，不授权 shadow，也不等价于四门全 PASS。
11. `4B-11`：退出判断独立汇总；退出输入失败不追溯改写 Gate，`EXIT_CANDIDATE` 不产生仓位或订单动作。
12. `4B-12`：完整结果固定保存五层 capability 身份、四个局部结果、统一 Gate 视图、`input_hash` 与 `replay_hash`。
13. `4B-13`：相同规范输入必须确定性重放；承重规则或输入变化必须改变相应哈希，运行环境噪声不得进入哈希。
14. `4B-14`：完整验收覆盖正例、反例、边界、`ABSTAIN`、防伪、replay 和局部回归，且全部 14 项可追溯。
15. `4B-15`：仅允许匿名合成 `research` validation，不使用真实 KB Release、真实市场可成交价、真实持仓、账户或订单状态。
16. `4B-16`：backtest、paper、shadow、live、仓位、组合、成交、P&L 和订单继续全部不授权，Stage 5 不因 4B 获批而自动开始。

## 10. 批准后才允许执行的工作

若第 9 节 16 项全部获批，下一提交才可以：

1. 保留本 draft 和 draft machine proposal 不变，另建 approved 4B bundle 与 approval record；
2. 实现 `Stage4CompleteSyntheticCase`、精确 capability verifier、完整编排器和统一结果；
3. 建立第 7 节完整 golden/replay 验收并运行全仓回归；
4. 更新 Stage 4 状态为“完整合成研究引擎已验收”，但仍明确没有任何真实运行或交易权限。
