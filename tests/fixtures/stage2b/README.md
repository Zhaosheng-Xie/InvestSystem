# Stage 2B 合成策略黄金资产

状态：`approved-rule test vectors / implementation API independent`

本目录固定“高速光互连订单/合同”匿名合成切片的输入语义、预期路径和失败层级。它只服务 `research` 且 `validation_only=true` 的确定性验证，不是 KB Published Release、真实事实、策略有效性证据、仓位批准或订单权限。

## 目录隔离

- `normal/`：正常合成输入、四类策略 golden 和业务边界向量。
- `failure-injection/`：独立的输入/治理硬失败，不从正常 fixture 原件改写或复用其身份。
- `replay/`：replay hash 的同一性、敏感性和拒绝关系；不固定仍在并行生成的规则包文档哈希。
- `synthetic-fixture-registry.v0.1.0.json`：严格登记 24 个可执行策略向量与 10 个仅准入失败向量；只有完整身份和内容哈希精确匹配的策略记录才能取得引擎 capability。

三类文件不得互相改标。所有正常结果，包括 `TRADE_READY`，都必须保持：

```text
run_mode = research
validation_only = true
position_state = FLAT
target_weight = 0 or null
approved_weight = 0 or null
actual_weight = 0 or null
approver = null
authorizes_positions = false
authorizes_orders = false
```

`SHADOW_ONLY` 在本阶段也只是 research 决策标签，不授权 `run_mode=shadow` 或影子执行。

## 文件

| 文件 | 用途 |
|---|---|
| `normal/synthetic-order-contract-base.v0.1.0.json` | 完整匿名合成基准输入；不绑定任何具体 Python 构造器 |
| `normal/strategy-golden-cases.v0.1.0.json` | `TRADE_READY`、`SHADOW_ONLY`、`REJECT`、`ABSTAIN` 的输入变异与完整预期路径 |
| `normal/strategy-boundary-cases.v0.1.0.json` | Gate 2/4 等号与邻域、Decimal、Gate 3、PIT、证据独立性和短路边界 |
| `failure-injection/admission-blocked-cases.v0.1.0.json` | 哈希、撤回、Schema、未来信息、Decimal 类型和合成权限标记硬失败 |
| `replay/replay-hash-relations.v0.1.0.json` | replay hash 必须相同、必须变化或必须拒绝的关系向量 |
| `synthetic-fixture-registry.v0.1.0.json` | 24+10 条可信登记的机器可读快照、内部 aggregate hash 与引擎 pin 来源 |

同名 `.canonical.sha256` 文件是对相应 JSON **解析后按 InvestSystem canonical profile 重编码所得字节**的 SHA-256，而不是对带缩进和末尾换行的物理文件直接求哈希。

## 向量解释规则

JSON 文件是测试向量契约，不是运行时 Schema。未来测试 harness 应：

1. 严格解析 JSON，拒绝重复键、非有限数和未知向量结构。
2. 从 `base_input_ref` 读取不可变基准值，为每个 case 建立深拷贝。
3. 按 `mutations` 顺序执行 JSON Pointer 操作；本版只允许 `replace`。
4. 无 mutation 的 `SYN-TRADE-001` 必须精确保留 base/批准 machine bundle 的 baseline `fixture_id`、`input_id` 和 `dataset_release_id`；其余每个变体必须重新物化独立身份，不得把变异值写回基准文件。
5. 金额、价格、数量、比例、率和计算结果必须保留为十进制字符串；JSON 整数只用于随机种子、计数和交易日窗口。
6. 中间计算使用任意精度 Decimal，不做中间舍入；阈值比较使用 `raw`，`display_6dp` 只作 `ROUND_HALF_EVEN` 展示。
7. 后续 Gate 短路时使用 `evaluation_state=not_evaluated`、`outcome=null` 和明确的 `short_circuit_reason_code`，不得伪造 PASS 或 ABSTAIN。
8. `BLOCKED` 在策略入口之前发生：`strategy_evaluator_calls=0`，不生成正常 StrategyRunManifest 或 DecisionRecord，只保存准入/运行失败审计。
9. 每个 `classification=Assumption` 的原始字段必须同时保存非空 `assumption_id`、`as_of`、`scenario`、`source_reason` 和字段相关 `falsifier`；本基准的 `as_of` 精确等于 `knowledge_cutoff`。`Derived`、`Fact`、`Judgment` 不得冒用 `assumption_id`。

`base_input_ref` 和 replay 关系文件中的 case 引用均相对此 README 所在目录解析。任何引用或 JSON Pointer 不存在都应令资产校验失败。

可信 registry 对每个正常向量分别固定四个互不重叠的身份：`input_envelope_hash` 是完整 `SyntheticValidationInput` wrapper，`verified_input_hash` 是完整 VKI，`strategy_case_input_hash` 是 typed semantic payload，`strategy_case_envelope_hash` 是完整 `IndustrialEventCase`。任一身份、版本或内容漂移都不得复用旧 capability。

## 黄金矩阵

| Case | 终止点 | 预期 |
|---|---|---|
| `SYN-TRADE-001` | Gate 4 PASS | `TRADE_READY + FLAT + zero authority` |
| `SYN-SHADOW-001` | E3.5 / Gate 1 | `SHADOW_ONLY`，Gate 2—4 不评估 |
| `SYN-REJECT-001` | Gate 2 | 利润重要性 `0.02`，`REJECT` |
| `SYN-ABSTAIN-001` | Gate 2 | E4 由最低数量确认但价格/金额不可核验，`ABSTAIN` |
| `INJECT-BLOCK-*` | 输入/治理准入 | `BLOCKED`，策略调用为零 |

## 必须保持的边界

- Gate 2：`0.10` 等号 PASS；原始值略低但展示为 `0.100000` 仍 REJECT，并包含超过 100 位有效数字的相邻值。
- Gate 4：净基准收益 `0.15`、赔率 `2.00` 和验证窗口 `120` 等号 PASS；任一略低或 `121` 均 REJECT，并包含超过 100 位有效数字的相邻值。
- `downside_loss=0` 为 ABSTAIN，不产生无穷赔率。
- 先验最低义务为零/严格较小/完全相同/未知分别为 `unexpected`、`partially_priced`、`fully_priced`、`unknown`。
- 第一可成交观察的 `available_at == knowledge_cutoff` 可用；任何使用事实晚于 cutoff 都在策略前 BLOCKED。
- 两条 E4 证据链必须具有不同原始文档、发布责任主体和取得链，且至少一条为权威原文；转载或同源摘要不算独立。
- replay hash 覆盖规范输入、规则身份和状态、可信 fixture registration/registry 身份、代码、配置、显式时钟、随机种子及确定性输出；run/decision/observation ID、墙上时钟、端点和临时路径不进入。

## 规则包绑定

向量固定规则包 ID `industrial_event_minimum_order_contract_slice` 和版本 `0.1.0`，但故意不硬编码规则包 canonical hash。测试执行时必须从受信批准登记表解析精确文档哈希，并将它纳入 replay envelope；登记表为空、身份不符或哈希不符均失败关闭。
