# Stage 4 / 4A-2 事件状态与审计分层批准记录 v0.1

文档状态：`approved`

批准范围：`stage4_synthetic_research_validation`

批准日期：`2026-08-03`

批准主体：`repository_owner`

批准来源：当前 Codex 任务中 owner 明确回复：

> 批准《Stage 4 / 4A-2 事件状态与审计分层规则包 v0.1》第 8 节全部 16 项，仅授权 stage4_synthetic_research_validation，不授权 backtest、paper、shadow、live、仓位或订单。批准继续完成 4A-2。

## 1. 精确批准对象

批准对象为：

- 路径：`产业卡点及事件驱动系统/03_规则与规格/Stage4_4A2事件状态与审计分层规则包_v0.1.md`；
- 文件 SHA-256：`673e7b65425cfda19561b3e3ac97ffd624e9d9770fa2d8dc80f458a4fd23468f`；
- 包含规则：`FR-EVT-001`、`FR-EVT-002`、`FR-EVT-003`、`FR-EVT-004`；
- 批准项：原文件第 8 节 `1—16` 全部项目。

原 draft 文件和 `industrial_event_stage4_4a2_event_semantics_v0.1.0-draft.rule-bundle.json` 保持不变，作为批准前快照。运行时只接受新生成的 `0.1.0` approved machine bundle 与其精确 `RuleApprovalRecord`，不得把 draft 改名或复用为批准制品。

## 2. 批准边界

- 只允许显式合成、非 Published Release 的 `research / validation_only`；
- 不授权 `backtest`、`paper`、`shadow`、`live`；
- 不授权组合、仓位、订单、成交、P&L 或资金部署；
- 不签发完整 Stage 4 capability；
- 不复用 Stage 2B 或 4A-1 capability；
- 不读取 KB SQLite、`raw/`、`staging`、工作树或内部包，也不把策略判断写回 KB。

### FR-EVT-001

批准 E0—E7/E3.5 evidence passport、压缩跨级、append-only revision、显式反证降级、缺失/冲突不得静默降级，以及固定输入规则迁移 replay。

### FR-EVT-002

批准 `E4_public` 六项严格 AND、一个权威原文建立 E4 候选、两条独立链只形成后续 Gate readiness，以及保密经济量的 E4/利润门分离。

### FR-EVT-003

批准五类主体角色、合法保密买方、同源 lineage 和按 `(available_at, fact_id)` 选择最早合法公开事实。

### FR-EVT-004

批准 Fact/Assumption/Derived/Judgment 字段、依赖方向、DAG、时间约束、append-only supersedes、人工覆盖和禁止 KB writeback。

## 3. 16 项批准登记

- [x] 1. E0—E7/E3.5 使用 evidence passport，不使用综合分数。
- [x] 2. E1/E2/E3/E5 使用同层 OR，E6 使用收入/增量利润/现金回收严格 AND。
- [x] 3. E3.5 为强商业线索 AND E4 `REJECT/ABSTAIN`；E4 `BLOCKED` 不产生事件状态。
- [x] 4. 中间护照完整时允许压缩跨级；缺失时 `ABSTAIN`。
- [x] 5. E7 四个终局子型及其前置状态。
- [x] 6. logical event、snapshot、revision、duplicate、supersedes append-only 规则。
- [x] 7. 明确反证可降级；缺失/不可恢复/冲突不能静默降级或沿用。
- [x] 8. 规则迁移必须在固定输入上 replay，不能原位改写。
- [x] 9. E4 六项严格 AND 和 `BLOCKED > REJECT > ABSTAIN > PASS`。
- [x] 10. 一个权威原文建立 E4 候选，两条独立链仅用于后续 Gate readiness。
- [x] 11. 最低义务已知但金额/价格保密时 E4 PASS、利润门 ABSTAIN。
- [x] 12. 五类 party role；买方合法保密不否决 E4，但不能形成跨主体确认。
- [x] 13. 最早合法公开事实按 `(available_at, fact_id)` 确定性选择。
- [x] 14. 同源转述不增加独立证据且不提前 PIT。
- [x] 15. 四类审计对象字段、依赖方向、DAG 和时间规则。
- [x] 16. scope 仅为合成 research validation，零交易权限。

## 4. 完成条件

本批准记录只授权开发和验证 4A-2。只有同时存在以下证据时，4A-2 才可标记完成：

1. 精确 approved machine bundle 与 approval record；
2. capability 绑定 strategy/bundle/version/hash/scope；
3. `FR-EVT-001—004` typed evaluator；
4. 每条规则的正例、反例、边界例和 `ABSTAIN`；
5. PIT、hash、scope、duplicate/revision、migration、DAG 和零权限失败关闭测试；
6. 全仓质量门和双平台 CI 通过。

4A-2 完成后仍有 `FR-GATE-001—005` 与 `FR-EXIT-001` 未批准，完整 Stage 4 capability 必须继续关闭。
