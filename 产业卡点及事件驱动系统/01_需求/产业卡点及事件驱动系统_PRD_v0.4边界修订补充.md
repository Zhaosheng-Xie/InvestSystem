# 产业卡点及事件驱动系统 PRD v0.4 边界修订补充

状态：`draft_for_owner_confirmation / zero_runtime_authority`

版本：`v0.4-boundary-addendum-draft`

形成日期：`2026-08-28`

修订范围：`KB provider contract / IS consumer ownership only`

## 1. 文档关系

本文件不是对完整 PRD 的重写。它保留 [PRD v0.3](产业卡点及事件驱动系统_PRD_v0.3.md)原始字节，只修订其中与 [ADR-0002](../../docs/adr/ADR-0002-kb-provider-contract-consumer-profile-boundary.md)冲突的跨仓所有权条款。

- PRD v0.3 raw SHA-256：`0f7e6489ee0c5c17d638534337a73c389e70794cf41b821eec7cc92a242c6b03`
- ADR-0002 raw SHA-256：`e18e91423066589b636edd0ca793e6949f45dcf272ce0f81661aa33c3982f22e`
- Stage 6 Consumer Profile v0.3 raw SHA-256：`79abfe814577dd2da644f5a59310021e6151e1c3a585cc6fa69aa69424e6bbad`
- Stage 6 provider/consumer approval record raw SHA-256：`83d8053fa5dc0593a4c5ab7205560512f89eb39a7dbd61eb4157badb0a0046af`

在 owner 批准前，本补充不生效。批准后，阅读顺序为：

```text
PRD v0.3 主体
  + PRD v0.4 边界补充（只覆盖本文件列出的冲突条款）
  + 已批准 ADR/规则/机器契约
```

未列入本文件的 v0.3 需求、数值 `hypothesis`、策略状态、风险和执行规则均保持不变。

## 2. 修订原因

PRD v0.3 在形成时使用了 KB legacy `strategy-input-ref.v1`，因此把 `strategy_input_ref` 描述为“KB 定义公共子契约”。后续两仓已批准并完成以下架构调整：

1. KB 发布通用 `ReleaseReference`、可变 dependency closure、data profile、benchmark/factor registry；
2. IS 固定 KB 公共提交和原始字节，通过 Adapter 构造 IS 自有 `StrategyInputRef`；
3. H00985 选择、ADV20/Beta120 接受与重算、holdout、candidate/coverage、authority 和运行权限属于 IS；
4. KB legacy `strategy-input-ref.v1` 只保留兼容读取，不再作为新 provider 输出模板。

当前固定基线：

- KB `main@4352c10c6c639e25d4c190dfc9ec58ee9e76aa86`；
- IS `main@4fc55976181fc72737dd64bab5bbd59d2826a8b4`；
- IS generic provider-contract snapshot lock：`513b3e8728fc299780bbd3205f0fa049a63bb4946b5eaa8193fc51447b5b333a`。

这些提交只证明通用 draft contract 与离线 synthetic Adapter 已闭合，不证明真实历史数据 ready。

## 3. 生效替换条款

### 3.1 替换 v0.3 §5.1 首段

原表述“每次 run 绑定符合 KB `strategy-input-ref.v1` 的输入引用”替换为：

> 首版每次 run 必须且只能保存一个 IS 自有 `strategy_input_ref`。IS Adapter 从一个精确 KB root `ReleaseReference` 的 Release ID、Manifest Schema version、Manifest hash 和 knowledge cutoff 构造该五字段对象。KB 不需要输出或拥有 `strategy_input_ref`。legacy `strategy-input-ref.v1` 只用于旧 Release/fixture 的只读兼容。

KB 可以发布多个 source/aggregate Release；“一次 run 只选择一个 root input”是 IS 运行约束，不限制 KB 的通用 dependency closure 能力。

### 3.2 替换 v0.3 §5.3 第 3 步

Manifest 校验顺序修订为：

1. 按 KB 公共契约验证 ReleaseReference、Release、Manifest Schema 和字节；
2. 对排除 `manifest_hash` 自身后的 Manifest 重算 provider 语义 hash；
3. 将 Release ID、Manifest Schema version、重算且匹配的 Manifest hash、knowledge cutoff 投影为 IS `StrategyInputRef`；
4. 后续 Receipt、Observation、RetentionClosure 和 StrategyRunManifest 必须绑定该 IS 投影；
5. legacy 输入如携带 `strategy-input-ref.v1`，必须与新投影逐字段相等，否则 `BLOCKED`。

不得先信任 provider 给出的策略引用，再用它反向证明 Manifest 正确。

### 3.3 替换 v0.3 §18.1 对象所有权中的一行

| 对象 | 权威项目 | 职责 |
|---|---|---|
| KB ReleaseReference / Release / Manifest / Status / Artifact / Context Pack | KB | 发布通用、版本化、不可变、策略无关的身份与数据 |
| `strategy_input_ref` | InvestSystem | 从已验证的一个 root ReleaseReference 确定性构造，并在 run 中保存 |
| KB Adapter / provider-neutral projection | InvestSystem | 固定 KB contract commit/Schema/hash，验证并映射为 IS 对象 |
| H00985、ADV20/Beta120 消费选择 | InvestSystem | 从 KB 通用 registry 选择、验证、抽样重算并决定是否接受 |
| `authority_eligible`、holdout、candidate、coverage | InvestSystem | 根据当前状态证据、批准范围和策略时点判定 |

Document/Evidence/Fact/CandidateEvent、Context Pack 和 Release 等原有 KB 所有权行继续有效；KB CandidateEvent 仍是知识事实候选，不是 IS 投资候选或 E 状态。

### 3.4 补充 v0.3 §22 阶段 C1

阶段 C1 分成两个明确门：

1. `C1a / draft contract compatibility`：从精确 KB Git commit 固定通用 Schema/catalog/registry/synthetic fixture，完成纯离线 Adapter 验证；不需要 Published Release，不产生 authority。
2. `C1b / published Release consumption`：只有 KB 数据来源、PIT、许可、immutable Release candidate 和 producer validation 完成后，IS 才固定正式发布身份并进行真实只读 handoff。

当前 `C1a` 已按 `completed_with_scope_limits` 验收；`C1b` 尚未开始。

artifact Schema/catalog 更新不自动等于 transport repin。只有 endpoint、HTTP envelope、headers 或 auth 语义改变时，才需要新的 transport version 与完整重验。

## 4. 仍然有效的 IS 对象

以下 v0.3 字段使用不属于矛盾，不删除：

- StrategyRunManifest 中保存 `strategy_input_ref`；
- Receipt、Observation、DecisionRecord、RetentionClosure 绑定 `strategy_input_ref`；
- `available_at <= strategy_input_ref.knowledge_cutoff <= decision_at`；
- 首版每个 run 只允许一个 root `strategy_input_ref`；
- Release 撤回或状态不可确认时阻止新 run；
- KB CandidateEvent 与 IS E0—E7、candidate/decision state 分离。

修订的是对象所有权和构造顺序，不是取消 IS 的运行身份。

## 5. KB 通用输入与 IS 消费责任

| KB 通用输出 | IS 消费责任 |
|---|---|
| ReleaseReference | 构造 `StrategyInputRef` |
| variable dependency closure | 构造并验证 IS 留存闭包 |
| release data profile | 形成数据准备度、缺失和 blocker |
| benchmark identity/observation | 精确选择 H00985；不得 fallback |
| factor definition/observation + raw basis | 验证 ADV20/Beta120 并抽样重算 |
| PIT facts/evidence/context | 映射为 provider-neutral strategy input |
| Release Status event chain | 形成 IS Observation/Confirmation/authority 判定 |

KB 不输出 E0—E7、四道门、利润桥、估值、candidate coverage、ABSTAIN/BLOCKED、仓位或订单。

## 6. Legacy 兼容

- 已固定的 KB v1 snapshot 和 `strategy-input-ref.v1` 原始字节保持不变；
- Stage 3D/6B 专用 handoff 继续作为历史 validation-only 证据；
- 新 Adapter 不要求旧 Published Release 被重写；
- legacy 引用只能通过兼容校验映射到 IS 对象，不能成为新 provider 生产模板；
- 禁止静默 alias、字段猜测、默认值或运行时跨仓读取。

## 7. 当前完成与阻塞

已经完成：

- ADR-0002 / Consumer Profile v0.3；
- KB generic draft Schema/catalog/registry/synthetic fixture；
- IS 19 文件 snapshot lock 和纯离线 Adapter；
- ReleaseReference、closure、data profile、H00985、ADV20/Beta120 合成契约验证。

继续阻塞：

- H00985 完整历史、historical PIT 和再分发许可；
- factor 官方 fixture 的 raw basis records；
- scope-eligible Published historical Release；
- 真实 handoff、candidate/coverage、historical run 和 2026 holdout。

## 8. 权限边界

本补充即使获批准，也不授权：

- KB 数据源、backfill、数据库、Release 或生产操作；
- IS transport repin、真实 handoff 或 Token；
- candidate、coverage、historical run、holdout；
- migration、backtest、paper、shadow、live、仓位或订单；
- 旧 Stage 6B 重构或根目录 spike 清理。

## 9. 待 owner 原子确认

- [ ] `PRD04-BND-01`：批准 v0.4 作为 v0.3 的边界修订补充，不重写 v0.3 原始字节。
- [ ] `PRD04-BND-02`：批准 `StrategyInputRef` 由 IS 从已验证 KB ReleaseReference 构造。
- [ ] `PRD04-BND-03`：批准 KB legacy `strategy-input-ref.v1` 只兼容读取。
- [ ] `PRD04-BND-04`：批准 Manifest 先独立验证，再构造并绑定 IS 输入引用。
- [ ] `PRD04-BND-05`：批准单一 root input 是 IS run 约束，不是 KB 发布约束。
- [ ] `PRD04-BND-06`：批准 C1 分为 draft 离线兼容与 Published Release 消费两个完成门。
- [ ] `PRD04-BND-07`：批准 H00985/factor 接受、holdout、authority、candidate/coverage 继续属于 IS。
- [ ] `PRD04-BND-08`：确认本补充为零数据、运行和交易权限。

八项必须原子批准；部分批准不生效。
