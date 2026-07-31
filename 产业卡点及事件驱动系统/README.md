# 产业卡点及事件驱动系统

项目状态：`需求决策已确认 / v0.3 待文档验收；规则规格待编写；尚无已实现系统`
基线日期：`2026-07-30`
市场范围：`中国 A 股`
当前边界：`研究、回测、paper/shadow；不接自动实盘`

## 系统一句话定义

先找到产业链中供给响应慢、替代困难且利润可能向上市公司传导的关键约束，再用可核验事件确认盈利路径、预期差和时点，最后通过组合风险预算决定是否交易、交易多少和何时退出。

## 目录

- `01_需求/`：产品需求、目标、边界、验收标准、待确认决策。
- `02_研究/`：框架审计、外部证据、来源登记与研究假设。
- `03_规则与规格/`：下一阶段的状态机、字段、信号和风险规则。
- `04_数据/`：KB Published Release 输入契约、验证 receipt、策略数据投影和运行快照；不保存 KB raw/staging。
- `05_实现/`：只读 Release 消费、策略引擎、回测和 paper/shadow 执行实现。
- `06_测试与验证/`：golden cases、回放、样本外、压力与偏差测试。
- `07_运行与复盘/`：每日/每周操作手册、决策日志和版本发布。

## 当前交付

1. [需求文档 v0.3](01_需求/产业卡点及事件驱动系统_PRD_v0.3.md)
   - 历史基线：[需求文档 v0.2](01_需求/产业卡点及事件驱动系统_PRD_v0.2.md)、[需求文档 v0.1](01_需求/产业卡点及事件驱动系统_PRD_v0.1.md)
2. [框架审计与研究结论 v0.1](02_研究/框架审计与研究结论_v0.1.md)
3. [来源登记表 v0.1](02_研究/来源登记表_v0.1.md)
4. [Alpha 竞争假设补充研究 v0.1](02_研究/Alpha竞争假设补充研究_v0.1.md)

## 推荐研发顺序

`需求与边界冻结 → KB 输入契约和独立工程骨架 → 最小规则包 → 合成纵向切片 → 正式 Release 只读验收 → 规则回测 → paper/shadow → go/no-go`

首个实现切片不做全市场自动交易，分两步进入同一个 provider-neutral 策略入口：

1. `InvestSystem 合成策略 fixture → StrategyRunManifest → E3/E3.5/E4 → 产业卡点匹配 → 四道门 → 利润桥/预期/估值 → DecisionRecord + replay_hash`；
2. `精确 KB Published Release → Manifest/制品/Release 状态校验 → ArtifactConsumptionReceipt + ArtifactFetchObservation + ReleaseStatusObservation → 同一策略入口 → 真实 smoke（允许 ABSTAIN）`。

完整组合、首次可成交和 paper 回放属于后续阶段；它们可基于 provider-neutral 输入开发，不等待 KB 部署，但正式历史验证必须等真实 Release E2E 完成。

产业事实与证据由独立的 `InvestmentResearchKB` 生产和发布。本项目不得读取其 SQLite、`raw/`、`staging/` 或内部实现，也不得把策略逻辑写回 KB。策略正例使用本项目明确标记的合成 fixture；不得要求 KB 为策略结果定制事实。
