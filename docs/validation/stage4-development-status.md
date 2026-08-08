# Stage 4 开发状态

> 状态日期：`2026-08-08`
>
> 分支：`codex/stage4a4`
>
> 阶段状态：`in_progress / 4A-1—4A-4 completed；4B draft_for_owner_approval`
>
> Stage 3：`in_progress / 3A—3B completed；3C—3D not_started`
>
> 当前授权：`4A-1—4A-4 exact local synthetic research-validation capabilities；完整 Stage 4 capability 仍关闭；4B 为零权限待批准草案`

## 1. 当前结论

Stage 2 进入门已通过[复核](stage2-reentry-audit.md)。Stage 3A—3B 已完成，3C—3D 与 Stage 4 可在严格边界下继续独立推进。owner 已分别批准 4A-1、4A-2 第 8 节全部 16 项、4A-3 第 9 节全部 20 项和 4A-4 第 10 节全部 24 项；各批批准均严格限于 `stage4_synthetic_research_validation`，不授权 backtest、paper、shadow、live、仓位或订单。

4A-1—4A-4 均已形成独立的精确 machine bundle、approval record、局部 evaluator 和四类业务测试，14 项 P0 inventory 已全部 `approved`。这只证明四个局部批次各自在精确批准范围内可验证，不自动批准它们的完整编排。完整 Stage 4 capability 仍失败关闭；[4B 完整引擎集成与合成验收包](../../产业卡点及事件驱动系统/03_规则与规格/Stage4_4B完整引擎集成与合成验收规则包_v0.1.md)现为 16 项全 `pending` 的零权限草案。

## 2. 治理基线

- [Stage 4 完整 P0 规则清单与批准包 v0.1](../../产业卡点及事件驱动系统/03_规则与规格/Stage4完整P0规则清单与批准包_v0.1.md)；
- 14 项 Stage-4-owned P0 inventory，与 Stage 3 transport 和 Stage 5 execution/risk/portfolio 明确分离；
- `stage4_synthetic_research_validation` 专属 scope，不产生默认 capability；
- `Stage4RuleInventory` 机器模型和 draft JSON Schema；
- `require_stage4_rule_capability` 完成门：14 项全批准、四类测试齐全、精确 inventory hash、完整 rule modules、精确 registry approval 和零交易权限缺一不可；
- Stage 2B scope、inventory 漂移、权限漂移、缺项、重复项和默认 registry 均失败关闭。

当前 inventory canonical SHA-256 为 `fc07b10bb17d91b3447504fe7f5b2e346023fd98bb14da991e1a1dd85381bf53`；draft Schema 文件 SHA-256 为 `4a00d6e49e36e81e14f28ebe19ba75bef16eafaab29679e885f9b7f76189f795`。inventory hash 只固定当前阶段快照；每个局部批次的业务身份仍由各自的精确 bundle/approval record 固定。任一规则变化都必须产生新版本和批准。

## 3. 4A-1 已完成内容

- [4A-1 文字规格](../../产业卡点及事件驱动系统/03_规则与规格/Stage4_4A1上下文与产业映射规则包_v0.1.md)；
- canonical machine bundle SHA-256：`5224e8e6d600b8f613d6dfaf4dd486d6caafdcf5fe3d8d3db29af2f25462a32d`；
- owner approval record canonical SHA-256：`84d47caa4b8226dd4e9c4dee31645214938e7321e25e93f368bf1ecc167b5e1a`；
- `FR-CTX-001/002`：十个上下文覆盖域、预注册、三类历史绑定、PIT、左闭右开有效区间和禁止后见回填；
- `FR-IND-001/002`：五项严格 AND、至少两个独立证据组，以及 `technical_link → qualified_supplier → profit_beneficiary` 严格晋级；
- `stage4_context_industry.py`：按 `CTX-002 → CTX-001 → IND-001 → IND-002` 短路，全部交易权限恒为 false。

## 4. 4A-2 已完成内容

- [原 4A-2 draft 文字规格](../../产业卡点及事件驱动系统/03_规则与规格/Stage4_4A2事件状态与审计分层规则包_v0.1.md)，文档 SHA-256：`673e7b65425cfda19561b3e3ac97ffd624e9d9770fa2d8dc80f458a4fd23468f`；原 draft machine proposal 保持不可执行且不原位改写；
- [4A-2 owner 批准记录](../../产业卡点及事件驱动系统/03_规则与规格/Stage4_4A2事件状态与审计分层批准记录_v0.1.md)，文件 SHA-256：`ae4434dfcaa11f6c49244d5675ebc875b743367230db9b09b7997b8e1510f0ee`；
- approved canonical machine bundle SHA-256：`9f9f5cf843347a1918a894be1151c0ef720bd6318daa1077657e97e9324d6560`，rules SHA-256：`574dd4273c60081b099cf2c2427a2f264521f57ff16aa70b5ce1138ea9e8f228`；
- owner approval record canonical SHA-256：`57c5147ab93c7cf547f72347a7550f951c9ca2ad0cf97cb0755148bfa0d155ac`；
- `FR-EVT-001`：E0—E7/E3.5 事实护照、显式终态、重复观测、降级和规则迁移重放；
- `FR-EVT-002`：E4 六项严格 AND、权威原件、两个独立证据链和保密金额语义；
- `FR-EVT-003`：五类主体角色、适用性、PIT 与确定性最早事实选择；
- `FR-EVT-004`：Fact/Assumption/Derived/Judgment/Audit 分层、合法依赖方向、DAG/时间约束、append-only supersedes 和人工覆盖批准；
- `stage4_event_semantics.py`：按 `EVT-004 → EVT-003 → EVT-002 → EVT-001` 失败关闭，只输出不可变局部研究评估，零交易权限。

## 5. 4A-3 已完成内容

- [4A-3 文字规格](../../产业卡点及事件驱动系统/03_规则与规格/Stage4_4A3四道门利润分母与情景规则包_v0.1.md)，文档 SHA-256：`f2eef18f1a4c85fbc0587893beee4aea25f1d373a7f3482f23c0fbf08e08ea4c`；
- 原 draft canonical machine bundle SHA-256：`03e0f6f4afb7de84185ee345b1a654fcaec48f4182a13ad8fbf65a2eae996393`，rules SHA-256：`62dcf735e166dfe49935ac5a325237716e931b5ec1cd166b0b949122fb5dd5e2`；原 proposal 保持不可执行且不原位改写；
- [4A-3 owner 批准记录](../../产业卡点及事件驱动系统/03_规则与规格/Stage4_4A3四道门利润分母与情景批准记录_v0.1.md)，文件 SHA-256：`bfe9f9fb11ade5f6c1ebebf86f1366b34e3ab3ccc352b987002ebf7afbffea12`；
- approved canonical machine bundle SHA-256：`e6936e9c236fd7ed3a67eb8c5e01cb02d23d8fa20c8fcd7a3ccbd615220619b2`，rules SHA-256：`146c8c497f529a0b7c675882522f4928877c96093449b5e0245fb6cfb71a05f0`；
- owner approval record canonical SHA-256：`786944b9263a7571632dbc5a2c92dcb1deb1431f8946f113ee883495dac5281a`；
- `FR-GATE-001`：精确组合 4A-1/4A-2 结果，固定 Gate 1 结果映射和短路，Gate 3—4 保持未评估；
- `FR-GATE-002`：PIT 反事实 NTM 标准化归母利润桥、确定性区间、`standard/fragile` 轨、精确 `0.10` 门槛和事件增量利润/FCF；
- `FR-GATE-003`：base/downside/upside/stress 四情景、十四项显式 driver、PIT/外汇/哈希/版本防线、压力一致性与可选概率校准；
- `stage4_gate_profit_scenarios.py` 只接受精确 approved capability，执行顺序为 Gate 1 → 情景验证 → Gate 2，所有交易权限恒为 false。

## 6. 4A-4 已完成内容

- [4A-4 市场预期、估值与退出文字规格](../../产业卡点及事件驱动系统/03_规则与规格/Stage4_4A4市场预期估值与退出规则包_v0.1.md)，文档 SHA-256：`7f2f1238ff5d9bae1c7a96b212b87dd56a04ac8a9013715e46d2b6cc9d864a62`；
- draft canonical machine bundle SHA-256：`2d6ebeafeb93fd0d799ab31c1a93e88639e7979fc6416179a18158a9a4450055`，rules SHA-256：`5692fae5ab76c233d2f3d3ff3c0e23002062a179426de843c46d5439c09d543c`；
- [4A-4 owner 批准记录](../../产业卡点及事件驱动系统/03_规则与规格/Stage4_4A4市场预期估值与退出批准记录_v0.1.md)，文件 SHA-256：`c793c776a309b418f9ec7de760a26899ce609b3541d71e957ad56cdbfa0d0724`；
- approved canonical machine bundle SHA-256：`6ad34d6534b646eb0eb4fcab73c9da13e0738af0d3ae0d296143a48129ee1762`，rules SHA-256：`d1d2e03d78f0a78c63e073916da87f9177bb2e7151bd1d4d9ec959cd865545e2`；
- owner approval record canonical SHA-256：`8b75674537a9b8939cd259e2efb5a46752282714f19b23e181d9509ae09b919e`；
- `FR-GATE-004`：分离公开经济预期与市场价格反推，以严格区间关系评估 `unexpected/partially_priced/fully_priced/unknown` 和市场是否已充分反映；
- `FR-GATE-005`：基础业务与 E4 有限期增量 FCF 分开、组件唯一归属和防重复计价；合成 Gate 4 固定 `0.15` 净基础剩余收益、`2.00` reward/downside 与最多 `120` 个交易日 proof window；
- `FR-EXIT-001`：evidence/risk/time/value 四类退出与重新承保只形成策略判断；已实现六类证据触发、等号风险/时间/价值边界和 unknown/confirmed 优先级；
- `stage4_expectation_valuation_exit.py` 只接受精确 approved capability 和 4A-1—4A-3 上游身份，所有输出均为匿名合成 validation，真实价格、KB 内部读取或跨版本 holding 失败关闭，全部交易权限恒为 false。

## 7. 4B 当前草案

- [4B 完整引擎集成与合成验收规则包](../../产业卡点及事件驱动系统/03_规则与规格/Stage4_4B完整引擎集成与合成验收规则包_v0.1.md)精确绑定四个 approved batch 和完整 inventory；
- draft machine proposal 固定单一 case/截止时间、禁止注入局部 PASS、`4A-1 → 4A-2 → 4A-3 → 4A-4 → 退出汇总`、统一结论优先级和 replay 合同；
- 16 项 approval item 全部为 `pending`，运行模式为空，`authorizes_complete_stage4_capability=false`；没有 4B approval record、完整编排器或完整 capability。

## 8. 当前明确不能做

- 不能运行完整 Stage 4 策略引擎；4A-4 的 Gate 3—4 或退出结果仍只是局部研究结论；
- 不能把 Stage 2B 或任一 4A 局部 capability 相互复用或外推为完整 Stage 4；
- 不能把 4B draft proposal 作为完整规则 bundle 加载，也不能在 owner 批准前实现完整编排器；
- 不能读取 KB 工作树、SQLite、raw、staging 或本地活动库补齐 Stage 3C—3D；
- 不能进入 backtest、paper、shadow、live、仓位、组合或订单。

## 9. 下一完成门

下一步由 owner 审阅 4B 第 9 节十六项并明确批准、修改或拒绝。只有全部获批后才能另行生成 approved 4B artifacts、完整编排器和合成 golden/replay 验收；4B 获批也只可能签发 `stage4_synthetic_research_validation` capability，不会开启任何真实运行或交易权限。

## 10. 当前验证

- 4A-4 approved evaluator 与 Stage 4 governance 定向测试覆盖精确 artifact/hash、Gate 3—4、四类退出、短路、边界、`ABSTAIN`、防伪和 replay；
- 4B draft-only 治理测试覆盖精确 inventory、四批 hash、16 项 pending、零权限、文档绑定、无 approval record 和无完整编排器；
- 全仓 pytest、Ruff lint/format、mypy、compileall 和 `git diff --check` 的本提交结果记录在[4A-4 验收报告](stage4-4a4-acceptance.md)；
- `pip check` 仍只报告共享环境安装前已登记的 OpenCV/NumPy 冲突；本阶段未安装、升级、降级或卸载任何包；
- 4 个 skip 仍仅来自本地 Windows symlink/junction 权限，不是 Stage 4 逻辑跳过。
