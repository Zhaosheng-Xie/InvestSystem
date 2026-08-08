# Stage 4 开发状态

> 状态日期：`2026-08-08`
>
> 分支：`codex/stage4`
>
> 阶段状态：`in_progress / 4A-1 completed；4A-2 completed；4A-3 completed；4A-4 next`
>
> Stage 3：`deferred by owner / not completed`
>
> 当前授权：`4A-1—4A-3 exact synthetic research-validation capabilities；Gate 3—4 与完整 Stage 4 runtime capability 仍关闭`

## 1. 当前结论

Stage 2 进入门已通过[复核](stage2-reentry-audit.md)，Stage 4 可以在不等待 Stage 3 或 KB 部署的前提下开发。owner 已分别批准 4A-1、4A-2 第 8 节全部 16 项和 4A-3 第 9 节全部 20 项；各批批准均严格限于 `stage4_synthetic_research_validation`，不授权 backtest、paper、shadow、live、仓位或订单。

4A-1—4A-3 均已形成独立的精确 machine bundle、approval record、局部 evaluator 和四类业务测试。4A-3 原 owner-review draft 与零权限 proposal 继续作为不可变谱系保留。14 项 P0 inventory 当前十一项 `approved`、三项 `draft`，因此完整 Stage 4 capability 仍必须失败关闭。

## 2. 治理基线

- [Stage 4 完整 P0 规则清单与批准包 v0.1](../../产业卡点及事件驱动系统/03_规则与规格/Stage4完整P0规则清单与批准包_v0.1.md)；
- 14 项 Stage-4-owned P0 inventory，与 Stage 3 transport 和 Stage 5 execution/risk/portfolio 明确分离；
- `stage4_synthetic_research_validation` 专属 scope，不产生默认 capability；
- `Stage4RuleInventory` 机器模型和 draft JSON Schema；
- `require_stage4_rule_capability` 完成门：14 项全批准、四类测试齐全、精确 inventory hash、完整 rule modules、精确 registry approval 和零交易权限缺一不可；
- Stage 2B scope、inventory 漂移、权限漂移、缺项、重复项和默认 registry 均失败关闭。

当前 inventory canonical SHA-256 为 `6ccef82fc77ca73135bdfbebceca196728d02e6491033425fe903e4d60267fc2`；draft Schema 文件 SHA-256 为 `4a00d6e49e36e81e14f28ebe19ba75bef16eafaab29679e885f9b7f76189f795`。inventory hash 只固定当前阶段快照；每个局部批次的业务身份仍由各自的精确 bundle/approval record 固定。任一规则变化都必须产生新版本和批准。

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

## 6. 当前明确不能做

- 不能运行完整 Stage 4 策略引擎；4A-3 的 Gate 2 通过只产生 `gate2_research_qualified` 局部结论；
- 不能把 Stage 2B 或任一 4A 局部 capability 相互复用或外推为完整 Stage 4；
- 不能实现 4A-4 中尚未批准的预期、估值、退出或完整决策语义；
- 不能读取 KB 工作树、SQLite、raw、staging 或本地活动库补齐 Stage 3；
- 不能进入 backtest、paper、shadow、live、仓位、组合或订单。

## 7. 下一完成门

下一步以同样的先规格、后逐项批准流程完成 4A-4 的 `FR-GATE-004/005` 与 `FR-EXIT-001`。只有 14 项全部完成、完整 machine bundle 与完整合成 replay 验收通过后，完整 Stage 4 capability 才可能签发。

## 8. 当前验证

- `FR-EVT-001—004` 4A-2 定向业务测试：`32 passed`；
- 4A-3 approved evaluator 定向测试：`28 passed`；
- Stage 4 governance、4A-1—4A-3 approved evaluator 与 draft 谱系定向测试：`117 passed`；
- 全仓 pytest：`736 passed, 4 skipped`；
- Ruff lint、format、mypy（70 个源文件）、compileall、`git diff --check`：通过；
- wheel 构建通过，并确认同时包含 `stage4_gate_governance.py` 与 `stage4_gate_profit_scenarios.py`；
- `pip check` 仍只报告共享环境安装前已登记的 OpenCV/NumPy 冲突；本阶段未安装、升级、降级或卸载任何包；
- 4 个 skip 仍仅来自本地 Windows symlink/junction 权限，不是 Stage 4 逻辑跳过。
