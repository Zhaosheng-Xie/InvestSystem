# Stage 4 开发状态

> 状态日期：`2026-08-03`
>
> 分支：`codex/stage4`
>
> 阶段状态：`in_progress / 4A rule governance`
>
> Stage 3：`deferred by owner / not completed`
>
> 当前授权：`development only；无 Stage 4 runtime capability`

## 1. 启动结论

Stage 2 进入门已通过[复核](stage2-reentry-audit.md)，Stage 4 可以在不等待 Stage 3 或 KB 部署的前提下启动。首个切片只建立完整 P0 规则清单、专属 approval scope、机器 inventory 和 fail-closed capability 边界，不实现未批准业务参数。

## 2. 4A 已建立内容

- [Stage 4 完整 P0 规则清单与批准包 v0.1](../../产业卡点及事件驱动系统/03_规则与规格/Stage4完整P0规则清单与批准包_v0.1.md)；
- 14 项 Stage-4-owned P0 inventory，与 Stage 3 transport 和 Stage 5 execution/risk/portfolio 明确分离；
- `stage4_synthetic_research_validation` 专属 scope；它只表达未来授权类型，不自动签发 capability；
- `Stage4RuleInventory` 机器模型和 draft JSON Schema；
- checked-in draft inventory，14 项全部为 `draft`，无 approval ID、machine rule 或测试完成声明；
- `require_stage4_rule_capability` 完成门：14 项全批准、四类测试齐全、精确 inventory hash、完整 rule modules、精确 registry approval 和零交易权限缺一不可；
- Stage 2B scope、inventory 漂移、权限漂移、缺项、重复项和默认 registry 均失败关闭。

当前 draft inventory canonical SHA-256 为 `c60936301d307c3adb06bedf61dd1e24f0af3463b15a630551d77f49899b8f37`；draft Schema 文件 SHA-256 为 `4a00d6e49e36e81e14f28ebe19ba75bef16eafaab29679e885f9b7f76189f795`。这些哈希只固定当前开发快照，不构成 owner approval；任一条规则变化都必须产生新的精确身份和审批记录。

## 3. 当前明确不能做

- 不能运行完整 Stage 4 策略引擎；
- 不能把 Stage 2B 规则或 capability 外推到 Stage 4；
- 不能实现 PRD 中仍为 `hypothesis/TBD` 的阈值；
- 不能读取 KB 工作树、SQLite、raw、staging 或本地活动库补齐 Stage 3；
- 不能进入 backtest、paper、shadow、live、仓位、组合或订单。

## 4. 下一完成门

owner 需要按 4A-1 至 4A-4 批准 14 项规则。每项批准须绑定规格、machine rule 和正例/反例/边界/`ABSTAIN` 测试；只有 14 项全部完成后，完整 Stage 4 capability 才可能签发并进入合成 research validation。

## 5. 当前验证

- Stage 4 governance 与 Schema 定向测试：`39 passed`；
- 全仓 pytest：`634 passed, 4 skipped`；
- Ruff lint、format、mypy（60 个源文件）、compileall、`git diff --check`：通过；
- wheel 构建通过，并确认包含 `invest_system/strategies/industrial_event/stage4_governance.py`；
- 4 个 skip 仍仅来自本地 Windows symlink/junction 权限，不是 Stage 4 逻辑跳过。
