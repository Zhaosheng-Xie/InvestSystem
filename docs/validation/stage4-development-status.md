# Stage 4 开发状态

> 状态日期：`2026-08-03`
>
> 分支：`codex/stage4`
>
> 阶段状态：`in_progress / 4A-1 completed；4A-2 next`
>
> Stage 3：`deferred by owner / not completed`
>
> 当前授权：`4A-1 exact synthetic research-validation capability；无完整 Stage 4 runtime capability`

## 1. 启动结论

Stage 2 进入门已通过[复核](stage2-reentry-audit.md)，Stage 4 可以在不等待 Stage 3 或 KB 部署的前提下启动。治理切片先建立完整 P0 清单、专属 approval scope、机器 inventory 和 fail-closed capability 边界；owner 随后批准继续 4A-1，其四条规则已精确固化并实现，不包含收益、仓位或交易参数。

## 2. 4A 已建立内容

- [Stage 4 完整 P0 规则清单与批准包 v0.1](../../产业卡点及事件驱动系统/03_规则与规格/Stage4完整P0规则清单与批准包_v0.1.md)；
- 14 项 Stage-4-owned P0 inventory，与 Stage 3 transport 和 Stage 5 execution/risk/portfolio 明确分离；
- `stage4_synthetic_research_validation` 专属 scope；它只表达未来授权类型，不自动签发 capability；
- `Stage4RuleInventory` 机器模型和 draft JSON Schema；
- checked-in inventory，4A-1 四项为 `approved`，其余 10 项为 `draft`；
- `require_stage4_rule_capability` 完成门：14 项全批准、四类测试齐全、精确 inventory hash、完整 rule modules、精确 registry approval 和零交易权限缺一不可；
- Stage 2B scope、inventory 漂移、权限漂移、缺项、重复项和默认 registry 均失败关闭。

当前 inventory canonical SHA-256 为 `da1284feb6015db167853fdb07f00132ef34634d689a185cbb680fe35ee3ec46`；draft Schema 文件 SHA-256 为 `4a00d6e49e36e81e14f28ebe19ba75bef16eafaab29679e885f9b7f76189f795`。inventory hash 只固定当前阶段快照；4A-1 的业务批准身份由下列精确 rule bundle/approval record 单独固定，任一规则变化都必须产生新版本和批准。

## 3. 4A-1 已完成内容

- [4A-1 文字规格](../../产业卡点及事件驱动系统/03_规则与规格/Stage4_4A1上下文与产业映射规则包_v0.1.md)；
- canonical machine bundle SHA-256：`5224e8e6d600b8f613d6dfaf4dd486d6caafdcf5fe3d8d3db29af2f25462a32d`；
- owner approval record canonical SHA-256：`84d47caa4b8226dd4e9c4dee31645214938e7321e25e93f368bf1ecc167b5e1a`；
- `FR-CTX-001`：十个上下文覆盖域、预注册、`decision_pool/research_quarantine`；
- `FR-CTX-002`：三类历史绑定、PIT 与左闭右开有效区间、禁止后见回填；
- `FR-IND-001`：五项严格 AND、消失领先信号、至少两个独立证据组；
- `FR-IND-002`：`technical_link → qualified_supplier → profit_beneficiary` 严格晋级；
- `stage4_context_industry.py`：按 `CTX-002 → CTX-001 → IND-001 → IND-002` 短路，只输出局部研究资格和审计身份，全部交易权限恒为 false。

## 4. 当前明确不能做

- 不能运行完整 Stage 4 策略引擎；4A-1 的 `four_gate_eligible=true` 仅表示可以进入尚未实现的后续门；
- 不能把 Stage 2B 规则或 capability 外推到 Stage 4；
- 不能实现 PRD 中仍为 `hypothesis/TBD` 的阈值；
- 不能读取 KB 工作树、SQLite、raw、staging 或本地活动库补齐 Stage 3；
- 不能进入 backtest、paper、shadow、live、仓位、组合或订单。

## 5. 下一完成门

下一步是 4A-2 的 `FR-EVT-001—004`。每项批准须绑定规格、machine rule 和正例/反例/边界/`ABSTAIN` 测试；只有 14 项全部完成后，完整 Stage 4 capability 才可能签发并进入完整合成 research validation。

## 6. 当前验证

- Stage 4 governance 与 4A-1 定向测试：`40 passed`；
- 全仓 pytest：`659 passed, 4 skipped`；
- Ruff lint、format、mypy（62 个源文件）、compileall、`git diff --check`：通过；
- wheel 构建通过，并确认包含 `invest_system/strategies/industrial_event/stage4_context_industry.py`；
- `pip check` 仍只报告共享环境安装前已登记的 OpenCV/NumPy 冲突，本阶段没有安装、升级、降级或卸载任何包；
- 4 个 skip 仍仅来自本地 Windows symlink/junction 权限，不是 Stage 4 逻辑跳过。
