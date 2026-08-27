# 产业卡点及事件驱动系统 PRD v0.4 边界修订批准记录

状态：`approved_governance_only / zero_runtime_authority`

批准日期：`2026-08-28`

批准范围：`PRD04-BND-01—08 / boundary addendum only`

## 1. Owner 授权

Owner 对已形成并验收的八项边界修订作出条件授权：

> 如果没有特别值得我注意的风险就批准

复核结论：没有需要阻止批准的 P0/P1 风险。该补充只修订对象所有权和校验顺序，保留 v0.3 原始字节、legacy 兼容、策略规则和所有权限边界；不包含 Stage 6B 重构、spike 清理、数据、运行或交易动作。因此条件满足。

## 2. 精确批准身份

### PRD v0.3 基线

- path：`产业卡点及事件驱动系统/01_需求/产业卡点及事件驱动系统_PRD_v0.3.md`
- raw SHA-256：`0f7e6489ee0c5c17d638534337a73c389e70794cf41b821eec7cc92a242c6b03`
- 状态：`approved / bytes unchanged`

### v0.4 边界补充 pending draft

- path：`产业卡点及事件驱动系统/01_需求/产业卡点及事件驱动系统_PRD_v0.4边界修订补充.md`
- raw SHA-256：`3587f49786cd3425f5a9dc5dd9df1af364963a7369cb38b8c40511ce00501d36`

### 机器草案

- path：`docs/validation/machine/industrial-event-prd-v0.4-boundary-addendum-draft.json`
- raw SHA-256：`f6dcef60682a2eaf7824fc9039e048e5f1730c0ffd27db55ebaf3a72fc77b79b`
- canonical addendum SHA-256：`da32630be2b2ca9d44a68b7dba5a23fcc92ed4223adc00b7e448e7f541a092c4`
- pending owner items SHA-256：`72d79dd91c26129b1acdfa74371373522e164351833645b499e93b8995b46f03`

草案原始字节继续保持 pending 状态用于审计；本批准记录与 machine approval record 使上述精确内容生效，不回写草案。

## 3. 原子批准决定

- `PRD04-BND-01`：v0.4 是 v0.3 的窄边界补充，不重写 v0.3。
- `PRD04-BND-02`：IS 从已验证 KB ReleaseReference 构造 `StrategyInputRef`。
- `PRD04-BND-03`：KB legacy `strategy-input-ref.v1` 只兼容读取。
- `PRD04-BND-04`：先验证 Manifest，再投影并绑定 IS 输入引用。
- `PRD04-BND-05`：单一 root input 是 IS run 约束，不是 KB 发布限制。
- `PRD04-BND-06`：C1a draft 离线兼容与 C1b Published Release 消费使用独立完成门。
- `PRD04-BND-07`：H00985/factor 接受、holdout、authority、candidate/coverage 属于 IS。
- `PRD04-BND-08`：本补充保持零数据、运行和交易权限。

八项原子生效，不允许部分实施。

## 4. 生效结果

批准后的需求基线由 PRD v0.3 主体与本 v0.4 边界补充共同组成。本补充只在列明冲突处优先，未列明的 v0.3 需求继续有效。

当前 C1a 通用 draft 契约离线兼容已在 IS `4fc5597` 完成；C1b Published Release 消费仍为 `not_started`。

## 5. 未授权范围

本批准不授权：

- 旧 Stage 6B 重构；
- 根目录 spike 归档、提交或清理；
- KB 数据源、许可、backfill、数据库、Release 或生产；
- IS transport repin、Token 或真实 handoff；
- candidate、coverage、historical run、holdout；
- migration、backtest、paper、shadow、live、仓位或订单。

下一主线继续等待 KB 数据来源/许可/PIT 审计与后续独立授权，不因本 PRD 修订自动推进。
