# Stage 6 KB 提供方与 IS 消费者边界批准记录 v0.1

状态：`approved_governance_only / zero_runtime_authority`

批准日期：`2026-08-26`

批准对象：

- `KBIS-ADR-0002`；
- Stage 6 历史公共数据消费与验收 Profile `0.3.0-draft` 的精确冻结内容；
- `S6BOUND-01—10` 全部十项。

## 1. Owner 授权来源

Owner 在形成草案前明确授权：

> 这两份待批准的文件可能会有很大的风险吗？如果风险不大，就可以帮我看着批准。

Owner 在 KB 修复完成后继续指令：

> KB那边修复完了，IS这边继续

IS 与 KB 两仓独立只读审计得到相同职责结论，没有发现生产级 P0 或需要阻止该治理批准的 P1；KB Stage 7 稳定性修复已合入 `main@6ae6c4c3c8ec9433ff63fddcb2bbb207a39e8cbe`，合并后三条主干 CI 全绿。因此满足 owner 的条件授权。

## 2. 精确批准身份

### ADR-0002 提议

- path：`docs/adr/ADR-0002-kb-provider-contract-consumer-profile-boundary.md`
- raw SHA-256：`e18e91423066589b636edd0ca793e6949f45dcf272ce0f81661aa33c3982f22e`

### Consumer Profile v0.3 draft

- path：`docs/validation/stage6-historical-public-data-consumer-profile-v0.3-draft.md`
- raw SHA-256：`79abfe814577dd2da644f5a59310021e6151e1c3a585cc6fa69aa69424e6bbad`

### Machine draft

- path：`docs/validation/machine/stage6-historical-public-data-consumer-profile-v0.3.0-draft.json`
- raw SHA-256：`2ea49cf7cd2cd100ecf6fde345b431a75a3f03c226d79fa4689cb0799fce8f6d`
- canonical profile SHA-256：`76c8d8eceab4c012dc957ac40edfd7d013a7d2a27a8b4edb997815ce81e3ebc0`
- pending owner items SHA-256：`dd003f2688fa459bce537e7d1c560152494c7ffad120cdb383cc1e4f5e8d0a27`

草案原始字节继续保持 pending 状态供审计；本批准记录和机器 approval lineage 令上述精确内容生效，不回写草案。

## 3. 原子批准的十项决定

- `S6BOUND-01`：KB public contract 与 IS Consumer Profile 使用独立版本空间。
- `S6BOUND-02`：新 KB 核心 Schema 不再输出 `strategy_input_ref` 或 IS run 字段。
- `S6BOUND-03`：`authority_eligible`、holdout/outcome 和运行权限只由 IS 持有。
- `S6BOUND-04`：KB 提供通用 aggregate dependency closure；单一 root 是 IS run 约束。
- `S6BOUND-05`：KB benchmark/factor 基础 Schema 参数化；H00985 由 IS Profile 选择。
- `S6BOUND-06`：KB 发布 raw basis 和版本化通用 factor；IS 负责重算、接受和策略使用。
- `S6BOUND-07`：v0.2/S6DATA-01—10 继续有效，正式解释为 IS 消费需求与验收 Profile。
- `S6BOUND-08`：legacy `strategy-input-ref.v1` 与专用 handoff 只兼容读取，不作为新生产模板。
- `S6BOUND-09`：artifact Schema/catalog 增量不自动升级 transport v1。
- `S6BOUND-10`：本批准保持零数据和运行权限。

十项原子生效，不允许部分实施。

## 4. 批准后的职责

KB 应继续作为通用数据与证据提供方；IS 负责 Adapter、`StrategyInputRef`、H00985/ADV/Beta 消费选择、holdout、candidate/coverage、authority 与决策。

KB 对本 ADR 的对应实现仍需在 KB 仓库形成同一 decision ID、内容 hash 和本仓库 owner 批准谱系；本记录不修改 KB，也不自动批准 KB Schema 实现。

## 5. 明确未授权

本批准只关闭治理边界，以下全部保持未授权：

- KB Schema/catalog/fixture 实现；
- 数据源探测、许可取得或 backfill；
- Published Release、Token、tcloud 或生产变更；
- IS parser、Adapter 业务实现或 repin；
- handoff、candidate、coverage、historical run 或 holdout；
- migration、backtest、paper、shadow、live、仓位或订单。

下一步只能由 KB 先形成通用 draft Schema/registry/catalog/fixture 提案；实施仍须遵守 KB 自有批准门。IS 在固定新的 KB public contract commit 前不得实现真实适配或 repin。
