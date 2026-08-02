# Stage 2B 最小合成策略纵向切片验收记录

> 验收日期：`2026-08-02`
> 验收状态：`completed`
> 实现提交：`d5d60033f7190a70004802d975909247005cc862`
> 验收分支：`codex/stage2b`
> 当前成熟度：`synthetic_research_validation_completed / backtest_not_authorized / real_transport_not_implemented / full_strategy_not_implemented`

## 1. 验收结论

Stage 2B 的最小订单/合同合成纵向切片通过验收。仓库现在能够在不访问 InvestmentResearchKB 工作树、包、SQLite、`raw/`、`staging/`、网络或服务的前提下，使用 InvestSystem 自有且精确登记的匿名合成输入，确定性执行：

`SyntheticValidationInput → StrategyRunManifest → E3.5/E4_public → Gate 1—4 → 窄版利润桥/预期/估值 → DecisionRecord → replay_hash`

本结论只证明批准规则的合成路径可运行、可失败关闭、可审计和可重放，不证明策略有效、存在 Alpha 或适用于真实公司。授权范围精确限定为 `stage2b_synthetic_validation`、`run_mode=research` 和 `validation_only=true`；不授权 `backtest`、`paper`、`shadow`、`live`、TargetPortfolio、仓位、人工仓位批准、订单或资金部署。合成结果中的 `TRADE_READY` 与 `SHADOW_ONLY` 只是路径标签，全部输出仍保持 `FLAT`、三类权重为 `0`、`approver=null`，且无仓位或订单权限。

## 2. 已验收范围

| 范围 | 验收结果 |
|---|---|
| 规则批准 | 《最小订单合同纵向切片规则包 v0.1》全部 22 项已获所有者批准；机器 rule bundle 与 `RuleApprovalRecord` 由 strategy/bundle/version/canonical hash/scope 精确绑定。 |
| 批准加载 | 通用默认 registry 继续为空；运行组合点必须显式注入精确批准记录签发的 capability。自报 `approved`、相似 scope、未知或漂移 hash 均失败关闭。 |
| 合成输入身份 | 分别固定完整 `SyntheticValidationInput`、底层 `VerifiedKnowledgeInput`、typed semantic payload 和完整 `IndustrialEventCase` 四类 SHA-256，不允许互相替代。 |
| 可信 fixture | 注册表固定 24 个正常策略向量和 10 个独立失败注入向量；动态输入、旧 capability、内容漂移或身份前缀漂移均不能进入引擎。 |
| 事件与 Gate | 实现本规则包限定的 E3/E3.5/E4 路径、证据独立性、Gate 1—4、严格短路和 `TRADE_READY`、`SHADOW_ONLY`、`REJECT`、`ABSTAIN` 四类正常结果。 |
| 经济计算 | 金额与比率使用有限十进制字符串；阈值比较采用无中间舍入的精确整数交叉乘法，包含超过 100 位有效数字的邻域用例。 |
| 审计分层 | `Fact`、`Assumption`、`Derived`、`Judgment` 分开记录；每个现存 Assumption 都有唯一 ID、`as_of`、场景、来源理由和证伪条件，且 `as_of <= knowledge_cutoff`。 |
| 正常编排 | 唯一 typed runner 在全部 24 个正常案例中真实调用策略 evaluator 恰好一次，并构造完整 `ReplayEnvelope` 与 `DecisionRecord`。 |
| 失败编排 | 10 类准入失败和 Manifest/case/rule/capability/audit 错配在 evaluator 前拒绝，`strategy_evaluator_calls=0`，不生成正常 Manifest 或 DecisionRecord。 |
| Replay | replay 覆盖四类输入身份、规则批准、fixture registration/registry、代码、配置、环境锁、随机种子、显式评价时钟和语义输出；run/decision/observation ID 等审计身份被排除。 |
| 权限边界 | Manifest、引擎决定和 DecisionRecord 多层强制 `research + synthetic + validation_only + FLAT + zero authority`；代码无组合、券商、订单或资金副作用。 |
| KB 隔离 | 策略层只依赖 provider-neutral domain/model；无 KB integration、storage、兄弟路径、内部数据库、网络或文件 I/O。 |

## 3. 可复核锚点

| 锚点 | SHA-256 / 标识 |
|---|---|
| 实现提交 | `d5d60033f7190a70004802d975909247005cc862` |
| rule bundle canonical SHA-256 | `8e5c4a9da107d4ea4834bce2498b5315e7f5aa2013d3dd7fa1f7ea66e381bbe4` |
| approval record canonical SHA-256 | `25f464a6b15cb8fb944c014aeb4d9d72bbd21129275e5102d84f2a2391f9469e` |
| fixture registry semantic snapshot | `9c746809cf9d56bf54419dead7dbe33331b0fce9e17899993d1307795fb629d7` |
| fixture registry canonical sidecar | `89e593e1e0d595ed97115c2ea5aa35ab9cc4d312c31e32eac42e90771ab3a0ac` |
| baseline fixture | `synthetic_fixture_stage2b_optical_contract_001 / 0.1.0` |
| approval scope | `stage2b_synthetic_validation` |

规则 Markdown 是批准与追踪材料，运行时不解析它取得权限。机器 rule bundle 的 `document_binding` 固定该批准文档的原始字节；因此文档中“runtime wiring pending”的批准时点快照不在实现后原地改写，完成状态由本文记录。执行代码只接受精确 semantic profile、批准 capability 和 fixture registry snapshot。

## 4. 完成门证据

| 完成门 | 证据 | 结论 |
|---|---|---|
| 最小规则包已批准 | 22/22 批准项、canonical rule bundle、批准记录及其 Schema/哈希测试。 | `passed` |
| 五类结果在正确层级 | 24 个正常向量覆盖四类策略标签；10 个独立失败向量形成 pre-engine `BLOCKED` 审计。 | `passed` |
| 阈值、PIT 与短路正确 | 等号、略低、超过 100 位精度、未知、冲突、PIT cutoff、证据同源和三值逻辑均有正反例。 | `passed` |
| Manifest、Decision 与 Schema 闭合 | 真实 runner 输出通过 `StrategyRunManifest`、`GateResult`、`ReplayEnvelope` 和 `DecisionRecord` draft Schema。 | `passed` |
| 相同语义产生相同 replay | 语义输入或规则改变会变更 hash；仅 run/decision/observation ID 改变时 production runner 的 replay 保持相同。 | `passed` |
| 无 KB 与无副作用运行 | 架构测试禁止 provider/storage 进入策略层；runner 为纯内存合成验证，不读取 KB、不写数据库、不访问网络。 | `passed` |
| 独立审阅 | 架构与集成两轮审阅最终均为 `P0=0 / P1=0`。 | `passed` |

## 5. 验证记录

工作站共享解释器 `E:\Conda\envs\Data_Analysis\python.exe`：

- pytest：`617 passed, 4 skipped`；
- Ruff lint：通过；
- Ruff format check：`58 files already formatted`；
- mypy：`58 source files` 无问题；
- compileall：通过；
- `git diff --check`：通过；
- wheel：使用 `pip wheel --no-deps --no-build-isolation` 成功构建，并确认包含 strategy `engine`、`admission` 和 `runner`；
- `pip check`：只报告共享环境既有的 `opencv-python 4.12.0.88` 与 NumPy `1.26.4` 冲突；本阶段没有安装、升级、降级或卸载任何包。

4 个跳过项均因当前 Windows 账户没有创建测试 symlink/junction 的权限，属于既有跨平台隔离测试；Required CI 的 Ubuntu 文件系统会实际执行相应链接路径。

实现提交的 author 与 committer 均为 `Zhaosheng-Xie <70618384+Zhaosheng-Xie@users.noreply.github.com>`。`origin` 是可写 fork；`upstream` push URL 保持 `disabled://upstream-push-prohibited`。

## 6. 明确未实现与下一入口

Stage 2B 没有实现或授权：

- 真实 KB HTTP API、immutable export、current-status transport 或正式 Context Pack smoke；这些属于 Stage 3；
- 完整 E0—E7、全产业映射、通用利润桥/预期/估值、风险和退出规则；这些属于 Stage 4 及其后续批准；
- TargetPortfolio、持仓、成交、订单、P&L、backtest、paper、shadow 或 live；
- Stage 2B DecisionRecord 的 durable SQLite 写入。当前 runner 只返回完整、不可变、可序列化的审计对象；本阶段以零 I/O、零副作用作为安全边界，后续持久化必须先定义独立契约和失败语义。

Stage 2B 关闭后，Stage 3 与 Stage 4 可以独立推进：Stage 3 仍须等待并固定 KB 的公共 HTTP/export/current-status 契约和正式交付面；Stage 4 可在 InvestSystem 内继续逐项批准并实现完整产业事件规则，不依赖 KB 工作树或内部状态。两条路径只在正式历史验证前汇合，KB 可以继续自己的开发、发布和备份，不受本仓库影响。
