# Stage 2A 离线 Release 消费与准入内核验收记录

> 验收日期：`2026-08-02`
> 验收状态：`completed`
> 实现提交：`01073c1acbcb0350c3710749b29f581bdc7c56f6`
> 验收分支：`codex/stage2`
> 当前成熟度：`offline_release_admission_kernel / real_transport_not_implemented / strategy_not_implemented`

## 1. 验收结论

Stage 2A 的离线公共契约验证、provider-neutral 投影、消费持久化、run-scoped 当前状态确认、准入、完整闭包 pin 和历史留存内核通过验收。仓库现在能够在不读取 InvestmentResearchKB 工作树、包、SQLite 或内部目录的前提下，验证固定的公共契约与官方 fixture，并用 InvestSystem 自有 SQLite v3 和内容寻址缓存保存可复核的消费边界。

本结论不代表真实 KB HTTP API 或不可变导出包 transport 已实现，也不代表正式 current-status authority 已启用。两个传输入口当前都会在 I/O 前失败关闭，默认 authority allowlist 为空；E0—E7、四道门、利润桥、估值、分析结论、组合、执行和 P&L 仍未实现。

## 2. 已验收范围

| 范围 | 验收结果 |
|---|---|
| 固定公共依赖 | 从 KB 提交 `58ed9c5cb5302e3e719f1696bed83a03c5d6313b` 固定 20 个官方文件，其中包含 14 个锁定 v1 Schema；逐文件 Git blob、字节数和 SHA-256 受 snapshot lock 保护。 |
| Provider canonical 与 catalog | `irkb-jsonl-v1` 与 InvestSystem 自有 canonical profile 隔离；固定 Schema、contract lock、fixture lock、hash vectors 和路径安全均失败关闭。 |
| Reference fixture | 官方 Stage 6 fixture 的 Manifest、artifact、状态摘要、PIT、证据闭合和窄投影可确定性验证；状态摘要明确不能冒充完整 current-status 证明。 |
| 消费与留存契约 | `ArtifactConsumptionReceipt`、三类 append-only Observation 和 `ReleaseRetentionClosure` 固定根 Release、传递 source Release、Manifest 文档和精确 artifact 集。 |
| SQLite v3 | Receipt、Observation、闭包、Manifest、CAS、confirmation、run binding 和完整 closure pin 原子持久化；canonical parent 是聚合权威，关系行只作精确索引。 |
| Run-scoped 状态确认 | 新 run 必须提供受允许 authority、未过期且恰好覆盖完整闭包的 `RunReleaseStatusConfirmation`；五字段身份、current published event、event ID/hash/sequence、最大年龄和时钟偏差均重核。 |
| 默认拒绝 | 没有固定真实 authority 时，新 run 失败关闭；HTTP API 与 immutable export 在公共传输契约固定前以稳定 blocker code 在 I/O 前拒绝。 |
| 撤回与审计 | 新撤回或无法确认阻断新 pin 和普通读取；历史材料只通过显式 `audit_replay` 读取，不能形成新的当前决策、仓位、批准或订单。 |
| v2 迁移 | 已验证非空 v2 无损升级到 v3；全部旧 pin 写入不可变 quarantine，后注入 confirmation/binding 也不能恢复 `NEW_RUN`，且不会污染历史审计。 |
| 失败矩阵 | [Stage 2A 失败矩阵](stage2a-failure-matrix.md) 映射 100 个真实测试 ID，覆盖官方 fixture、InvestSystem 失败注入、合成状态、SQLite/CAS 篡改和跨仓隔离。 |

## 3. 完成门证据

| 完成门 | 证据 | 结论 |
|---|---|---|
| 无 KB 仓库/内部模块的独立验证 | CI 只 checkout InvestSystem；架构测试禁止 sibling path、KB import/editable、内部 SQLite/raw/staging/published、submodule 和共享可变状态。 | `passed` |
| 未知或漂移契约失败关闭 | Snapshot、Schema、canonical、Manifest、artifact、PIT、Receipt、Observation、闭包和 confirmation 正反例均进入失败矩阵。 | `passed` |
| 策略层保持 provider-neutral | 策略导入边界测试禁止 provider integration 进入策略层；公共投影只输出 InvestSystem DTO。 | `passed` |
| 确定性与幂等 | 固定原始字节/哈希、规范序列化、self hash、SQLite aggregate 重建、精确重试和冲突检测均有测试。 | `passed` |
| SQLite v3 原子准入与留存 | 全闭包 confirmation、pin、rollback、撤回、quarantine、CAS 损坏和 audit replay 均有正反例。 | `passed` |
| Windows/Linux 独立 CI | GitHub Actions run `30744115034` 的 Ubuntu 和 Windows 作业均为 `success`。 | `passed` |

## 4. 验证记录

### 4.1 本地锁定环境

从本仓库 `requirements-dev.lock` 建立的 `.venv` 中完成：

- `pip check`：无损坏依赖；
- Ruff lint 与 format check：通过；
- mypy：34 个源文件无问题；
- compileall：通过；
- pytest：`396 passed, 4 skipped`；
- 失败矩阵测试 ID：`100 documented / 0 missing`；
- support matrix JSON 与 `git diff --check`：通过。

4 个跳过项只因当前 Windows 账户没有创建测试 symlink/junction 的权限。相同测试在 Ubuntu CI 中由支持链接的文件系统实际执行；不能把本地权限跳过解释为发布门缺失。

### 4.2 GitHub Actions

实现提交 `01073c1` 的 push 工作流 [run 30744115034](https://github.com/Zhaosheng-Xie/InvestSystem/actions/runs/30744115034) 完成且结论为 `success`：

- [Ubuntu 作业 91486650254](https://github.com/Zhaosheng-Xie/InvestSystem/actions/runs/30744115034/job/91486650254)：`success`；
- [Windows 作业 91486650261](https://github.com/Zhaosheng-Xie/InvestSystem/actions/runs/30744115034/job/91486650261)：`success`。

两项作业都从本仓库 dev lock 使用 `--require-hashes` 建立 Python 3.12 环境，并成功执行依赖一致性、lint、格式、类型、pytest、compileall 和 push 范围空白检查。CI 不 checkout、安装或启动 InvestmentResearchKB。

### 4.3 独立审阅

两轮只读审阅最终结论为 `P0=0 / P1=0`。审阅推动并验证了以下补强：

- v2 旧 pin 使用不可变 quarantine，而不是仅凭“缺少 binding”推断 audit-only；
- confirmation canonical 文档按精确字段、类型、规范 UTC、数组顺序和模型语义严格反序列化并逐字节往返；
- authority 配置为无公共可变入口的私有只读快照，但不把同一受信 Python 进程内任意代码误称为权限沙箱；
- 增加 SQLite 级非法 confirmation、quarantine trigger 和直接注入 binding 的回归测试。

## 5. 可复核锚点

| 锚点 | SHA-256 / 标识 |
|---|---|
| runtime lock | `addcf10b912e97dd03c0e108975a0075e435048b3008cf8e30e8287b496e83c6` |
| dev lock | `f1e661cf8bc08172b5f2b7ddc328ec3de94ba8e7484cbae6c8b2a958cc3e147c` |
| KB snapshot lock | `4bd79d0e3032a3eeb7824a1b956282e5495dd52a01db81df8bf36b03a2d49092` |
| Stage 2A support matrix | `d170823615fe5e9ac4e61d68619117af9f6faf172892c6be4b22087836346787` |
| run status confirmation Schema | `9f7f7096f48bb5100fac2c5f4a6bed829e4801d0b849b870875b433ad45a5175` |
| 固定 KB 公共契约提交 | `58ed9c5cb5302e3e719f1696bed83a03c5d6313b` |
| Stage 2A 实现 | `01073c1acbcb0350c3710749b29f581bdc7c56f6` |

实现提交的 author 与 committer 均为 `Zhaosheng-Xie <70618384+Zhaosheng-Xie@users.noreply.github.com>`。`origin` 是可写 fork；`upstream` push URL 仍是 `disabled://upstream-push-prohibited`。

## 6. 明确未实现与后续入口

Stage 2A 完成后仍未实现：

- KB 只读 HTTP API 的 envelope、鉴权、重试、超时和分页 transport；
- immutable export package 的发现、解包、Schema/lock 和完整性 transport；
- 完整 provider status-event 正文与真实 current-status 获取或订阅；
- 由已认证 transport 保留并重核原始状态响应/导出证据后启用真实 authority；
- 正式 Published Release 的黑盒传输 smoke；
- 任何产业或题材策略语义。

这些 transport 与真实 authority 工作进入 Stage 3，并继续等待可固定的公共 HTTP/export/current-status 契约；不得用 KB 内部文件或调用方自填 self hash 绕过。下一条可独立推进的产品工作是 Stage 2B，但必须先由用户批准最小合成订单/合同场景和 approved 规则包。

KB 可以继续自己的开发、发布和备份工作；本仓库的 SQLite、缓存、运行目录、依赖、CI 和发布流程不与 KB 共享，也不会反向阻塞 KB。
