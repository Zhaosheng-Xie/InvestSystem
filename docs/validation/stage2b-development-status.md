# Stage 2B 开发状态（已关闭）

> 状态日期：`2026-08-02`
>
> 分支：`codex/stage2b`
>
> 阶段状态：`completed`
>
> 实现提交：`d5d60033f7190a70004802d975909247005cc862`
>
> 本文性质：历史开发状态；正式结论以 [Stage 2B 验收记录](stage2b-acceptance.md)为准

## 1. 关闭结论

Stage 2B 已完成 `2B-0` 批准安全契约和 `2B-1` 最小合成策略纵向切片。用户于 `2026-08-02` 明确批准《最小订单合同纵向切片规则包 v0.1》全部 22 项，批准范围严格为 `stage2b_synthetic_validation`。

实现只允许匿名 InvestSystem 合成输入、`run_mode=research` 且 `validation_only=true`。它不授权 `backtest`、`paper`、`shadow`、`live`、仓位、TargetPortfolio、订单或资金部署；`TRADE_READY` 和 `SHADOW_ONLY` 都只是合成结果标签。

## 2. 2B-0 交付

- `SyntheticValidationInput` 固定合成 provenance、验证标记、零权限和独立命名空间；
- `RuleBundleDocument`、`RuleApprovalRecord` 与不可伪造 capability 精确绑定整包 canonical hash；
- `ReplayEnvelope` 覆盖语义输入、规则、代码、配置、显式时钟和输出，同时排除 run/decision/observation ID 等审计身份；
- `StrategyRunManifest`、`GateResult`、`DecisionRecord` 和 Replay draft Schema 已提升到 Stage 2B 所需契约；
- 通用默认批准 registry 保持空，策略组合点只接受显式注入的精确批准 capability。

## 3. 2B-1 交付

- scope-limited machine rule bundle 与 `RuleApprovalRecord`；
- 24 个正常策略向量、10 个独立 admission failure 向量和不可变 fixture registry；
- E3/E3.5/E4 窄路径、四道门、严格短路、利润桥、预期分类和情景估值；
- `TRADE_READY`、`SHADOW_ONLY`、`REJECT`、`ABSTAIN` 正常结果，以及 evaluator 前的 `BLOCKED`；
- typed research-validation runner、完整 `DecisionRecord` 和确定性 replay；
- Fact/Assumption/Derived/Judgment 分层、Assumption 五元审计字段和 PIT 限制；
- Manifest/rule/case/capability/fixture/audit 任一错配均失败关闭。

## 4. 固定锚点

- rule bundle canonical SHA-256：`8e5c4a9da107d4ea4834bce2498b5315e7f5aa2013d3dd7fa1f7ea66e381bbe4`；
- approval record canonical SHA-256：`25f464a6b15cb8fb944c014aeb4d9d72bbd21129275e5102d84f2a2391f9469e`；
- fixture registry semantic snapshot：`9c746809cf9d56bf54419dead7dbe33331b0fce9e17899993d1307795fb629d7`；
- fixture registry sidecar：`89e593e1e0d595ed97115c2ea5aa35ab9cc4d312c31e32eac42e90771ab3a0ac`；
- 实现提交：`d5d60033f7190a70004802d975909247005cc862`。

## 5. 验证摘要

- pytest：`617 passed, 4 skipped`；
- Ruff lint/format、mypy、compileall、`git diff --check`：通过；
- wheel 构建与策略包内容检查：通过；
- 两轮独立审阅：`P0=0 / P1=0`。

4 个跳过项均来自当前 Windows 账户缺少 symlink/junction 权限，不是 Stage 2B 逻辑跳过。

## 6. 后续边界

真实 HTTP/export/current-status transport 和正式 Context Pack smoke 属于 Stage 3；完整产业事件策略属于 Stage 4。Stage 2B runner 当前不写 SQLite，保持零 I/O 和零副作用；durable DecisionRecord 持久化须在后续以独立契约和失败语义获批，不能从本阶段授权推导。
