# Stage 5 / 5A 成交、组合、账本与确定性回放批准记录 v0.1

批准状态：`approved`

批准时间：`2026-08-08T14:51:10.437340Z`

批准人：`repository_owner`

批准来源：当前 Codex task 中 owner 在收到《Stage 5 / 5A 成交、组合、账本与确定性回放精确规则包 v0.1》及其零权限边界后回复“批准”

批准范围：`stage5_synthetic_execution_validation`

## 1. 批准对象

owner 批准[《Stage 5 / 5A 成交、组合、账本与确定性回放精确规则包 v0.1》](Stage5_5A成交组合账本与确定性回放精确规则包_v0.1.md)第 13 节全部 40 项。被批准的原始 owner-review 文档 SHA-256 为：

`df866949bdfcc8eb52451b38155080551291d7539f17b730a01a233cf60a5740`

原零权限 draft machine proposal canonical bundle SHA-256 为：

`d0664b6b371ad042218f5d3c6caac9b9f1d1edd3ff475a5f7b36e401ca3d02db`

原零权限 draft machine proposal canonical rules SHA-256 为：

`ecc61a4ee3eb3a7e4dea7238c027aca2ac3c2ce145eb40f0fa80bb34085463f5`

批准只允许生成独立 approved machine bundle、approval record 和精确的 Stage 5A 合成执行验证 capability。原规则包和 draft proposal 保持不变，作为不可变批准谱系。本批准不等于 Stage 5B—5D 已实现或验收。

## 2. 四十项批准确认

### A. 身份、范围与失败语义

- [x] `5A-01`：独立 `stage5_synthetic_execution_validation` capability，既有 capability 和本草案本身均不能替代。
- [x] `5A-02`：固定 Stage 4B 精确身份；`ENTER/ADD` 重算四门，`REDUCE/EXIT` 只能按精确退出或风险命令减险。
- [x] `5A-03`：单 case 版本链、规范 hash、UTC 与市场交易日、十进制定点和显式 lineage。
- [x] `5A-04`：市场规则按官方字节和历史有效区间固定，禁止当前规则回填历史。
- [x] `5A-05`：执行、Gate、不可成交和对账状态严格分层。

### B. 决策时钟与首次可成交

- [x] `5A-06`：批准前参考价只形成上限且不可成交；批准后才从 `execution_eligible_from` 寻找窗口。
- [x] `5A-07`：盘中要求精确时间和完整延迟；低精度输入顺延并标记。
- [x] `5A-08`：只取时间上第一个全部合格窗口，禁止事后择优。
- [x] `5A-09`：一字板、零成交、无对手盘、停牌或报价不可证时不得模拟成交。
- [x] `5A-10`：日线 VWAP 只在严格前提下使用，不声称盘中时间或排队顺序。
- [x] `5A-11`：进入窗口为三个候选交易日且逐日重跑 Gate 3/4，第三日无 fill 后失效。
- [x] `5A-12`：退出不适用三日放弃，持续按新规则和价格尝试但不保证成交。
- [x] `5A-13`：数量、零股和 tick 舍入服从历史规则且不改善风险。

### C. 容量、成本与 fill

- [x] `5A-14`：`5%` 最大参与率仅限本合成 scope，真实历史验证必须重新校准。
- [x] `5A-15`：显式单调 `ImpactCurve`、线性插值、禁止外推和隐藏默认值。
- [x] `5A-16`：费用和税费按市场、证券、方向、账户及生效日版本化。
- [x] `5A-17`：成交价影响与 fee/tax 现金分录分离，禁止重复扣除。
- [x] `5A-18`：冻结 E4 前经济预期；当前可成交价格只更新价格反映和 Gate 4，不改写 Stage 4。
- [x] `5A-19`：合成 intent 仅为 `DAY`；部分成交、余量取消和多日重审语义固定。
- [x] `5A-20`：fill 完全确定性，禁止随机队列、随机滑点或 Monte Carlo。

### D. 组合与风险

- [x] `5A-21`：仅匿名 CNY 合成账户，无杠杆、做空、负现金、真实账户或券商绑定。
- [x] `5A-22`：压力损失率和初始目标金额按第 6.2 节公式统一为 CNY 后取最小值。
- [x] `5A-23`：合成市场状态损失率、E4 初始上限和单公司上限按草案精确值生效。
- [x] `5A-24`：风险簇损失、风险簇权重和总未平仓计划损失按草案精确值生效。
- [x] `5A-25`：多风险簇逐簇通过，簇身份版本化，缺失 `ABSTAIN`，跨策略账本隔离。
- [x] `5A-26`：市场状态只能缩小风险；真实分类器未批准时禁止默认为 `NORMAL`。
- [x] `5A-27`：回撤阈值、等号和人工恢复语义仅在本合成 scope 生效。
- [x] `5A-28`：五层仓位分离；首次合格窗口只能缩小或取消批准上限，增加必须重新批准。

### E. 账本、公司行动与 P&L

- [x] `5A-29`：按 strategy/account 隔离的 append-only 双分录 journal。
- [x] `5A-30`：事件集合与确定性排序固定。
- [x] `5A-31`：同 key 同字节幂等、不同字节失败关闭，修订只用 reversal 与 replacement。
- [x] `5A-32`：成交、交收、可卖数量和现金可用分别记账，历史例外来自 `MarketRuleSet`。
- [x] `5A-33`：每个 fill 建 lot，卖出采用 FIFO，且不声称等于券商成本展示。
- [x] `5A-34`：公司行动使用未复权价格和独立账本事件，缺失失败关闭，复权价不得作为 fill。
- [x] `5A-35`：actual position、cash、cost、sellable 和 NAV 全部由 journal 派生并逐事件对账。
- [x] `5A-36`：equity/P&L、外部现金流剥离和各分项加总恒等式固定。
- [x] `5A-37`：合法未复权 mark、停牌 stale 和缺失 mark 的失败关闭语义固定。

### F. Replay、隔离与零权限

- [x] `5A-38`：replay hash 覆盖全部承重输入和派生结果，并排除运行噪声。
- [x] `5A-39`：`audit_replay` 只复现历史，不形成新的当前权威。
- [x] `5A-40`：产业/题材全链隔离；零 backtest/paper/shadow/live、零真实仓位/账户/订单、零券商/KB 写权限。

## 3. 权限结论

本批准允许未来 Stage 5B—5D 在精确 approved bundle 和 approval record 下实现匿名合成 `research` 验证。Stage 5A capability 只证明规则身份获得 owner 授权，不证明 evaluator、市场规则历史表、成交模型、组合账本、P&L 或 replay 已实现和通过验收。

本批准明确不授权：

- backtest、paper、shadow 或 live；
- 真实 KB Release、KB current-status authority 或正式 `StrategyRunManifest`；
- 真实行情下载、账户、资产、仓位、委托、成交、订单、券商连接或资金部署；
- 读取或写入 KB SQLite、`raw/`、`staging/`、工作树或内部包；
- 题材策略复用产业策略的信号、组合、账本、成交或 P&L。

Stage 5B、5C 和 5D 必须依次形成实现、专项测试、golden/replay 和独立验收证据；在 Stage 5 全部完成并由 owner 另行授权前，不得进入 Stage 6 backtest。
