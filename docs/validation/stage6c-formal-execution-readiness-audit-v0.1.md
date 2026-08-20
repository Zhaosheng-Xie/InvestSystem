# Stage 6C 正式执行 Readiness 审计 v0.1

审计结论：`BLOCKED_FOR_FORMAL_STAGE6C_EXECUTION`

审计日期：`2026-08-20`

审计基线提交：`4b786142fc3c584868f011d39fcf03f3bc2859a8`

## 1. 技术摘要

**匿名 synthetic kernel 已准备好，但正式 Stage 6C 尚不能启动。** 六条 synthetic 切片已经验证 holdout/TWR、candidate/fold/coverage、inference/Holm、champion、peer/experiment 和统一 phase seal 的公式、身份及失败关闭；这只证明 IS 代码骨架能在匿名输入上按规则工作。

正式执行仍缺少六组承重条件：

1. 正式 execution owner approval、正式 `HistoricalRunAdmissionSeal` 与状态库 migration；
2. 2019—2025 全候选、PIT、修订、退市和历史证券状态的 Published Release 输入；
3. 60-session mark、退出/SELL、公司行动和真实已结束交易的 Stage 5D 支持；
4. 历史行业/市值/Beta peer universe 与同成本 benchmark NAV；
5. 真实 experiment、friction、completion 和 bias-audit 来源；
6. 独立 holdout custodian、ACL/credential、canary 和 zero-read audit。

因此当前不得签发正式 run authority，不得运行 development/walk-forward，也不得把 `SYNTHETIC_PHASE_SEALED` 升级为 `READY_FOR_6D_FREEZE`。

## 2. 状态定义与审计范围

| 状态 | 含义 |
|---|---|
| `READY` | 精确证据已存在，并足以支撑正式 6C 对应前置门 |
| `MISSING` | 所需合同、数据、实现或验收尚不存在 |
| `BLOCKED` | 受一个或多个承重 `MISSING` 项阻断，当前动作必须停止 |
| `NOT_REQUIRED_WITH_JUSTIFICATION` | 本阶段明确不需要，且不影响正式 6C 结论 |

审计只检查 InvestSystem 工作区、固定公共 KB transport/Release 验收证据和现有 approved artifacts。未读取 KB SQLite、`raw/`、`staging/`、`published/` 工作树、内部包或临时运行数据；未访问网络或 holdout。

目标研究单位仍为 PIT `economic_event × listed_company × decision_time`；正式用途是 2019—2025 development/walk-forward，不包含 2026 holdout。

## 3. Readiness 清单

### 3.1 治理、权限与阶段门

| ID | 状态 | 责任方 | 检查项 | 当前证据 / 缺口 |
|---|---|---|---|---|
| `R-01` | `READY` | IS / owner | Stage 6C v0.2 40 项精确批准 | approved bundle、approval record、`stage6c_governance.py` 与治理验收已存在 |
| `R-02` | `READY` | IS | 匿名 synthetic kernel 完整编排 | 六条切片与 `stage6c-synthetic-phase-seal-acceptance.md`，全仓 `1089 passed, 4 skipped` |
| `R-03` | `MISSING` | owner | 正式 development/walk-forward execution 授权 | 当前 capability 只允许 anonymous synthetic kernel；正式 run 明确为 false |
| `R-04` | `MISSING` | IS / owner | 正式 Stage 6C phase-result / issuer 合同 | 只有 `SYNTHETIC_PHASE_SEALED`，且强制 `not_ready_for_6d_freeze=true` |
| `R-05` | `NOT_REQUIRED_WITH_JUSTIFICATION` | owner | 6D holdout open 权限 | 6C 只需证明 holdout 未访问；打开 holdout 属于独立 6D 门 |
| `R-06` | `NOT_REQUIRED_WITH_JUSTIFICATION` | owner | paper/shadow/live/订单权限 | 历史验证不需要交易权限，且这些权限必须保持关闭 |

### 3.2 Admission、状态与持久化

| ID | 状态 | 责任方 | 检查项 | 当前证据 / 缺口 |
|---|---|---|---|---|
| `R-07` | `READY` | IS | 固定公共 transport contract | KB commit `aab36fe…d285`，snapshot lock `02e0505f…169` |
| `R-08` | `READY` | IS / KB | 根与 Source Release 真实 HTTPS 闭包 | `stage6b-live-https-acceptance.md`：2 Releases、10 artifacts、published、完整 hash/header closure |
| `R-09` | `READY` | IS | 隔离 validation-only admission/seal | Stage 6B validation store/seal 已验收；明确不是正式 run authority |
| `R-10` | `MISSING` | IS / owner | 正式 `HistoricalRunAdmissionSeal` | 仓库只有 `Stage6BHistoricalRunAdmissionSeal` validation-only 类型和临时 store |
| `R-11` | `MISSING` | IS / owner | 正式状态库 migration/version/table prefix | `STORAGE_SCHEMA_VERSION=3`；无 Stage 6 正式 tables/migration；不得占用 Stage 5D 预留 v4 |
| `R-12` | `MISSING` | IS | 正式 run 的单事务 envelope/seal persistence | 仅隔离 validation store 原子实现，未进入 `var/state/invest_system.sqlite3` 正式 schema |
| `R-13` | `MISSING` | IS | 正式撤回、崩溃、并发、audit replay 验收 | validation-only failure matrix 已有；正式 migration/run 路径尚不存在，不能外推 |

### 3.3 历史数据、PIT 与完整总体

| ID | 状态 | 责任方 | 检查项 | 当前证据 / 缺口 |
|---|---|---|---|---|
| `R-14` | `READY` | KB / IS | 单一 cutoff 正式 Context Pack/Evidence 传输 | Release `rel_fc8…` / `rel_02f…` 已闭合；只证明 2026-07-28 cutoff 的交付与内容身份 |
| `R-15` | `MISSING` | KB / IS | 2019—2025 候选源总体 | 未见内容寻址 HistoricalDataReadinessReport 或可证明全量事件/公司/失败者的正式 projection |
| `R-16` | `MISSING` | KB | 历史 PIT completeness | 未证明每个 decision time 的事实、财务、价格和修订满足 `available_at <= decision_time <= knowledge_cutoff` |
| `R-17` | `MISSING` | KB | 修订、撤回、更正的历史可见性 | 单一当前 Release 不能证明历史版本未被后续修订回填；需版本化 lineage/availability 证据 |
| `R-18` | `MISSING` | KB / IS | 历史交易日历、MarketRuleSet、证券状态 | synthetic contracts/规则存在；未见 2019—2025 正式 Published Release 覆盖和 readiness 结果 |
| `R-19` | `MISSING` | KB / IS | 20/60/120-session marks 与合法 observation | 当前只验收固定 synthetic mark/TWR；无正式历史 marks、stale/conflict/停牌闭包 |
| `R-20` | `MISSING` | KB / IS | 幸存者、退市、失败者和被拒绝候选 | PRD 要求包含；尚无正式 candidate inventory/coverage 证据 |
| `R-21` | `MISSING` | KB / IS | Document/Fact/Event/Company/Security/Mark 引用完整性 | Stage 3D 只验证一个 Context Pack/Evidence 闭包；未验证历史总体跨制品 join coverage 与重复率 |

### 3.4 Stage 5D 执行、账本与 P&L 支持

| ID | 状态 | 责任方 | 检查项 | 当前证据 / 缺口 |
|---|---|---|---|---|
| `R-22` | `READY` | IS | 第一 ENTER/BUY source-driven bounded replay | 固定单例已完成 Stage 5C 同次重算、Ledger V2、mark/NAV、18-cell P&L 和 replay |
| `R-23` | `MISSING` | IS / owner | 已结束交易的 EXIT/SELL 生命周期 | 当前 bounded 5D-1 明确不覆盖 SELL/退出，无法证明 30 笔 completed trades |
| `R-24` | `MISSING` | IS / owner | 公司行动、外部现金流、特殊结算的必要支持 | 不要求一次覆盖所有边角，但必须先做真实样本 census 并达到 80%/70% coverage；当前 census 不存在 |
| `R-25` | `MISSING` | IS | 正式 Stage 5D support matrix + 逐候选 unsupported 原因 | 目前只有规则声明和 synthetic matrix；未绑定正式历史候选 |
| `R-26` | `MISSING` | IS / KB | 真实 fee/tax/slippage/impact/capacity/friction replay | Stage 5B/5C synthetic 规则存在；未见正式历史输入和 1.5× friction source-driven验收 |

### 3.5 Peer benchmark、实验与 holdout

| ID | 状态 | 责任方 | 检查项 | 当前证据 / 缺口 |
|---|---|---|---|---|
| `R-27` | `READY` | IS | Peer benchmark 规则/kernel | target exclusion、三层 fallback、最少五 peers、exact 1/N 已通过 synthetic 验收 |
| `R-28` | `MISSING` | KB / IS | 历史行业/流通市值/Beta peer universe | 无正式 PIT quintile/source projection；当前 peer snapshots 全为匿名 synthetic |
| `R-29` | `MISSING` | IS / KB | Peer return/NAV 与同成本执行/账本 | kernel 只构造 basket，不计算正式 peer returns；benchmark security 的 Stage 5D 支持未验证 |
| `R-30` | `READY` | IS | Holdout 隔离合同/kernel | development projection、opaque commitment、ACL/canary/zero-read 合同和 synthetic precheck 已验收 |
| `R-31` | `MISSING` | owner / IS | 真实 holdout custodian 与技术隔离 | 未指定 custodian principal、独立路径/CAS、OS ACL、凭据、canary、access log 或 unlock 流程 |
| `R-32` | `MISSING` | IS | 真实 experiment/friction/completion/bias audit sources | 目前只有匿名 synthetic attestations 和 24 项 ledger contract，无真实执行或审计报告 |
| `R-33` | `MISSING` | IS / owner | 正式 `READY_FOR_6D_FREEZE` issuer/handoff | 当前 phase seal 明确 `not_ready_for_6d_freeze=true`，也没有 6D capability |
| `R-34` | `BLOCKED` | owner / IS | 启动正式 Stage 6C execution | 被 `R-03/04/10—13/15—21/23—26/28—29/31—33` 联合阻断 |

## 4. 汇总与风险判断

| 状态 | 数量 |
|---|---:|
| `READY` | 9 |
| `MISSING` | 22 |
| `BLOCKED` | 1 |
| `NOT_REQUIRED_WITH_JUSTIFICATION` | 2 |
| 合计 | 34 |

### 最高风险

1. **Critical：历史 PIT 总体尚未证明。** 如果直接使用当前 cutoff 数据回放 2019—2025，会产生未来信息、修订回填和幸存者偏差。
2. **Critical：当前 Stage 5D 无法形成 30 笔已结束交易。** ENTER/BUY 单例不能替代 EXIT/SELL 与完整 P&L。
3. **High：peer benchmark 只有规则，没有正式历史输入和 return/NAV。** 不能公平比较 full system 与 simple/baseline。
4. **High：holdout 只有 synthetic 合同，没有真实 ACL/custodian。** 不能证明开发人员或进程未接触 2026 字节。
5. **High：正式 admission/migration 不存在。** validation-only seal 不能升级为正式 run authority。

没有实际历史数据 profile，因此本审计没有伪造行数、缺失率或覆盖率；这些指标本身被列为正式 readiness 的必需交付，而不是用 synthetic golden 代替。

## 5. 建议执行顺序

### P0：并行完成两份只读 census

1. **KB 公共交付 census**：只通过 Published Release/Manifest/artifact 或不可变 export，列出 2019—2025 每类事实/事件/公司/证券/mark/行业/市值/Beta/公司行动的日期范围、grain、key、`available_at`、修订 lineage、记录数与 Schema；不要求 KB 生成策略候选或 benchmark。
2. **IS Stage 5D support census**：用 outcome-blind 历史候选预投影，统计 EXIT/SELL、公司行动、外部现金流、特殊结算和 mark 场景命中率；不得读取收益汇总。输出逐候选 reason 与 80%/70% coverage 预估。

### P1：基于 census 作三个 owner 决策

1. 是否授权只补满足 coverage 的最小 Stage 5D 生命周期，不追求所有证券会计边角；
2. 正式 Stage 6 状态库 migration 采用什么版本/table prefix，且不得与 Stage 5D v4 冲突；
3. holdout custodian 由哪个独立 principal 管理，如何隔离路径、凭据、canary、access log 和 6D unlock。

### P2：前置门完成后再形成正式授权草案

只有 `R-10—13/15—21/23—26/28—32` 具备真实证据、`R-31` 有技术实现且重新审计后，才形成正式 Stage 6C execution approval draft。正式 run 仍只允许 development/walk-forward，不打开 holdout。

## 6. KB 与 IS 的职责边界

KB 需要提供通用、不可变、PIT 的事实/事件/市场/参考数据及公开 Schema/Release 证据；KB 不提供候选筛选、E0—E7、Gate、benchmark matching、回测、P&L、统计或 champion 结论。

IS 负责 candidate inventory、PIT filtering、Stage 5D support census、peer matching、执行/账本、统计、实验、偏差审计和结论。IS 不得读取 KB 内部路径来补 readiness。

## 7. 当前决策

`NO_GO_FOR_FORMAL_STAGE6C_EXECUTION`

允许的下一动作只有只读 readiness census、精确合同/迁移/holdout 方案和 owner 审阅。禁止正式 run、收益读取、holdout 访问、6D、paper/shadow/live 或交易。
