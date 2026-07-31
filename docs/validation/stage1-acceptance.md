# Stage 1 工程与机器契约骨架验收记录

> 验收日期：`2026-07-31`
> 验收状态：`completed`
> 实现提交：`f8d58f296fb5aa6dfaf3229c9b11422492e5021f`
> 验收分支：`codex/stage1-completion`
> 当前成熟度：`engineering_skeleton / strategy_not_implemented`

## 1. 验收结论

Stage 1 的工程与机器契约骨架通过验收。仓库现在具备独立安装、hash-locked
依赖、TOML 配置、provider-neutral draft 契约、确定性序列化与哈希、规则成熟度
防线、InvestSystem 自有 SQLite、内容寻址缓存、Release 准入与历史审计重放边界，
以及 Windows/Linux 独立 CI。

本结论只证明工程底座满足 Stage 1 完成门，不证明投资策略已经实现或有效。KB
Adapter、真实 KB Release 消费、E0—E7、四道门、利润桥、市场预期、估值、组合、
执行和 P&L 均不属于本次验收结果。

## 2. 已验收范围

| 范围 | 验收结果 |
|---|---|
| 包装与依赖 | 根级 `src/` 包装、Python 3.12 范围、runtime/dev hash lock、固定锁生成工具和 editable `--no-deps --no-build-isolation` 已建立。 |
| 配置与运行边界 | `config/default.toml`、项目自有 `var/state/`、`var/cache/kb-releases/` 和 `20 GiB` 软限额已建立；不共享 KB 可变状态。 |
| 最小机器契约 | InvestSystem 自有 `0.1.0-draft` 的 `VerifiedKnowledgeInput`、`StrategyRunManifest`、`GateResult` 和 `DecisionRecord` Schema 与不可变模型已建立。 |
| 确定性 | 规范 JSON 禁止浮点数和无序集合；UTC、完整代码提交、单一 `strategy_input_ref`、Schema 版本和哈希均被固定并验证。 |
| 规则成熟度 | 未批准规则只能产生研究或 shadow 输出；不能产生交易就绪决策、方向性仓位或审批记录。 |
| Release 状态与准入 | provider 状态与本地准入分别记录；新 run 在最新状态或准入不满足时失败关闭，撤回为终态。 |
| 缓存与固定输入 | 制品按 SHA-256 内容寻址、原子写入并读回重验；run 只固定调用方声明的精确制品子集。 |
| 历史审计 | 撤回或失去准入后，普通读取与新 run 被阻断；既有精确 pin 只能通过独立 `AuditReplayRequest` 审计读取，不改变原 Manifest。 |
| SQLite 完整性 | schema、索引、主键、唯一约束、外键、检查约束、视图、触发器、`quick_check` 和外键检查均有验证。 |
| 跨仓隔离 | 测试禁止 KB 内部包、SQLite、`raw/`、`staging/`、兄弟路径、submodule、共享配置和链接；离线冷启动不依赖 KB 仓库、网络或服务。 |

## 3. 验证证据

### 3.1 本地共享开发环境

在 `E:\Conda\envs\Data_Analysis` 中完成：

- Ruff lint 与 format check：通过；
- mypy：通过，17 个源文件无问题；
- compileall：通过；
- pytest：`194 passed, 3 skipped`；
- editable 注册后，Conda 显式清单和排除 editable/VCS 表示差异后的 pip 清单无变化；
- `pip check` 未新增冲突，仍只有安装前既有的 OpenCV/NumPy 冲突。

3 个跳过项只因当前 Windows 账户没有创建测试符号链接的权限；相同测试在 Linux CI
中未跳过，不能把本地跳过解释为未覆盖的发布门。

### 3.2 全新锁定环境

从 `requirements-dev.lock` 建立全新环境后完成：

- `pip check`：无损坏依赖；
- Ruff lint 与 format check：通过；
- mypy `1.20.2`：通过；
- compileall：通过；
- pytest：`194 passed, 3 skipped`，跳过原因仍为宿主 Windows 符号链接权限。

### 3.3 GitHub Actions

实现提交 `f8d58f2` 的 push 工作流
[run 30636576903](https://github.com/Zhaosheng-Xie/InvestSystem/actions/runs/30636576903)
完成且结论为 `success`：

- [Windows 作业 91175580710](https://github.com/Zhaosheng-Xie/InvestSystem/actions/runs/30636576903/job/91175580710)：`success`，`197 passed`；
- [Ubuntu 作业 91175580828](https://github.com/Zhaosheng-Xie/InvestSystem/actions/runs/30636576903/job/91175580828)：`success`，`197 passed`。

CI 只 checkout InvestSystem，使用 Python 3.12，从本仓库 dev lock 以
`--require-hashes` 安装，并执行依赖检查、lint、格式、类型、测试、编译和提交范围
空白检查。它不 checkout、安装或启动 InvestmentResearchKB。

## 4. 可复核锚点

| 锚点 | SHA-256 / 标识 |
|---|---|
| runtime lock | `ADDCF10B912E97DD03C0E108975A0075E435048B3008CF8E30E8287B496E83C6` |
| dev lock | `F1E661CF8BC08172B5F2B7DDC328EC3DE94BA8E7484CBAE6C8B2A958CC3E147C` |
| Manifest golden | `904cd0d3ee1d03a50c9f8ac79a96cef97e35e0417e2d984d202ad7cefe2bfa5e` |
| Stage 0 修正后基线 | `95674c3b7bf745f6c1fc39d20d46a5e6fbc893b1` |
| Stage 1 实现 | `f8d58f296fb5aa6dfaf3229c9b11422492e5021f` |

两个提交的 author 与 committer 均为
`Zhaosheng-Xie <70618384+Zhaosheng-Xie@users.noreply.github.com>`。`origin` 是可写 fork；
`upstream` 的 push URL 是 `disabled://upstream-push-prohibited`，且
`protocol.disabled.allow=never`。该护栏是 clone-local，新的 clone 必须重新建立。

## 5. 已知限制与语义说明

- 标准 JSON Schema 不能表达 `knowledge_cutoff <= created_at` 或
  `knowledge_cutoff <= decision_at` 这类跨字段时间顺序；不可变 Python 模型强制该不变量，
  并由正反例单测覆盖。只做 Schema 校验不能代替模型构造。
- 所有当前契约都是 InvestSystem 自有 `0.1.0-draft`，不是 KB 官方公共契约。Stage 2A
  必须通过显式依赖更新固定 KB Schema、lock、官方 fixture 字节和来源哈希。
- Stage 1 的 Release 状态、准入和缓存对象是 provider-neutral 骨架，不代表已经实现
  HTTP 或导出包 Adapter，也没有消费任何真实 KB Release。
- 共享开发环境的既有 OpenCV/NumPy 冲突未被修改；正式可复现证据来自本项目 lock
  建立的隔离环境和 GitHub Actions。

## 6. 后续入口

Stage 1 完成后可以并行准备 Stage 2A 和 Stage 2B，但本记录不自动启动任一阶段：

- Stage 2A：固定 KB 公共契约和官方 fixture，实现只读黑盒 Adapter；
- Stage 2B：由用户先批准一个合成订单/合同场景和最小规则包，再实现策略纵向切片。

两条轨道继续保持单向契约协作和零共享可变状态；KB 后续开发不受本仓库运行、数据库、
缓存或 CI 影响。
