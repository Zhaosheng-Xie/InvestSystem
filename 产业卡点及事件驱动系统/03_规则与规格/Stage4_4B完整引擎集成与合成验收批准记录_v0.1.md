# Stage 4 / 4B 完整引擎集成与合成验收批准记录 v0.1

批准状态：`approved`

批准时间：`2026-08-08T13:41:56.188447Z`

批准人：`repository_owner`

批准来源：当前 Codex task 中 owner 在收到精确待批准短语后回复“批准4B”

批准范围：`stage4_synthetic_research_validation`

## 1. 批准对象

owner 批准[《Stage 4 / 4B 完整引擎集成与合成验收规则包 v0.1》](Stage4_4B完整引擎集成与合成验收规则包_v0.1.md)第 9 节全部 16 项。被批准的原始 owner-review 文档 SHA-256 为：

`d5c1ab50d76ea5d9444adcc92da24313b5ce5b51080c2e9258a5484a9417ca8d`

原零权限 draft machine proposal canonical bundle SHA-256 为：

`2b845a6c4df0dc7e28779b0117409cd39b390cc304fb7bc54f9062c44697b44c`

原零权限 draft machine proposal canonical rules SHA-256 为：

`1c7e8cb5acd89187e527a11be8f50baf77307b29561bf3a7fdc95bb32f3e1df9`

批准只允许生成独立的 approved 4B machine bundle、approval record、完整合成编排器和 synthetic golden/replay 验收。原规则包和 draft proposal 保持不变，作为不可变批准谱系。

## 2. 十六项批准确认

- [x] `4B-01`：精确固定四个 approved batch 的 bundle/rules/approval record hash 与完整 inventory hash，漂移失败关闭。
- [x] `4B-02`：4B 只编排既有 14 项规则，不增改 4A-1—4A-4 业务语义。
- [x] `4B-03`：完整能力必须来自独立 approved 4B bundle、approval record 和 capability。
- [x] `4B-04`：完整输入只有一个 case、截止时间和版本链，并强制公司、产业节点、事件、主体、币种、单位和期间一致。
- [x] `4B-05`：4A-3/4A-4 上游结果只能由本次完整运行产生，禁止注入局部 PASS。
- [x] `4B-06`：执行顺序固定为 4A-1 → 4A-2 → 4A-3 → 4A-4 → 退出汇总。
- [x] `4B-07`：未评估规则显式 `not_evaluated`，不得默认 PASS 或跨门补偿。
- [x] `4B-08`：统一显示使用 4A-4 Gate 3—4，但不改写 4A-3 局部结果。
- [x] `4B-09`：最终 Gate 优先级为 `BLOCKED → REJECT → ABSTAIN → PASS`，四门全 PASS 才输出研究 `TRADE_READY`。
- [x] `4B-10`：`SHADOW_ONLY` 只保留 fragile-profit 研究语义，不授权 shadow。
- [x] `4B-11`：退出独立汇总，退出失败不改写 Gate，`EXIT_CANDIDATE` 不产生仓位或订单。
- [x] `4B-12`：完整结果保存五层 capability 身份、四个局部结果、统一 Gate 视图、`input_hash` 与 `replay_hash`。
- [x] `4B-13`：规范输入确定性重放，承重规则/输入变化改变 hash，运行环境噪声不进入 hash。
- [x] `4B-14`：验收覆盖正例、反例、边界、`ABSTAIN`、防伪、replay 和局部回归，14 项全可追溯。
- [x] `4B-15`：只允许匿名合成 `research` validation，不使用真实 KB Release、真实可成交价、真实持仓、账户或订单状态。
- [x] `4B-16`：backtest、paper、shadow、live、仓位、组合、成交、P&L 和订单全部继续不授权，Stage 5 不自动开始。

## 3. 精确依赖

| 批次 | bundle SHA-256 | rules SHA-256 | approval record SHA-256 |
|---|---|---|---|
| `4A-1` | `5224e8e6d600b8f613d6dfaf4dd486d6caafdcf5fe3d8d3db29af2f25462a32d` | `2e16e87585bccc1df735e33feed4b72e3160d7bb1c415320bed31ee01c1d264a` | `84d47caa4b8226dd4e9c4dee31645214938e7321e25e93f368bf1ecc167b5e1a` |
| `4A-2` | `9f9f5cf843347a1918a894be1151c0ef720bd6318daa1077657e97e9324d6560` | `574dd4273c60081b099cf2c2427a2f264521f57ff16aa70b5ce1138ea9e8f228` | `57c5147ab93c7cf547f72347a7550f951c9ca2ad0cf97cb0755148bfa0d155ac` |
| `4A-3` | `e6936e9c236fd7ed3a67eb8c5e01cb02d23d8fa20c8fcd7a3ccbd615220619b2` | `146c8c497f529a0b7c675882522f4928877c96093449b5e0245fb6cfb71a05f0` | `786944b9263a7571632dbc5a2c92dcb1deb1431f8946f113ee883495dac5281a` |
| `4A-4` | `6ad34d6534b646eb0eb4fcab73c9da13e0738af0d3ae0d296143a48129ee1762` | `d1d2e03d78f0a78c63e073916da87f9177bb2e7151bd1d4d9ec959cd865545e2` | `8b75674537a9b8939cd259e2efb5a46752282714f19b23e181d9509ae09b919e` |

完整 P0 inventory canonical SHA-256：

`fc07b10bb17d91b3447504fe7f5b2e346023fd98bb14da991e1a1dd85381bf53`

任一精确依赖变化都使本批准对应的 4B capability 失效，必须形成新版本和新批准。

## 4. 权限结论

本批准允许完整 Stage 4 **匿名合成研究验证能力**，不允许真实运行或交易能力。完整结果中的 `TRADE_READY`、`SHADOW_ONLY`、`EXIT_CANDIDATE` 均只是研究标签；`PositionState` 必须保持 `FLAT`，target/approved/actual weight、approver、order intent、execution 和 P&L 均为空或 false。

本批准不授权读取 KB SQLite、`raw/`、`staging/`、工作树或内部包，不签发 KB current-status authority，不创建正式 `StrategyRunManifest`，不开始 Stage 5，也不改变 Stage 3C—3D 的完成门。
