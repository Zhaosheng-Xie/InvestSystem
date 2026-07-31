# ADR-0001：InvestmentResearchKB 与 InvestSystem 边界及 Release 消费政策

状态：`approved`

批准日期：`2026-07-31`

批准人：`仓库负责人`

适用范围：`InvestSystem Stage 0 及后续所有阶段`

## 背景

`InvestmentResearchKB` 是独立的数据与证据提供方，InvestSystem 是策略、决策、组合和执行验证消费者。两个项目可以复用工作站级 Python 解释器，但不能共享项目依赖、内部代码、数据库、缓存或运行状态。原始文档中的投资设想也不能直接成为已实现策略。

## 决策

### 1. 职责与依赖方向

- KB 负责采集、PIT、结构化事实、证据、审核、Release、Manifest 和 Context Pack。
- InvestSystem 只消费精确 Published Release，并负责 `StrategyRunManifest`、E0—E7、四道门、利润桥、估值、分析结论、决策、组合、执行和 P&L。
- 依赖方向只能从 KB 的版本化发布面指向 InvestSystem。InvestSystem 不读取 KB SQLite、`raw/`、`staging/`、`published/` 工作树、内部 Python 包或临时目录，也不向 KB 写入策略逻辑。

### 2. 输入引用数量

首版一次 run 只允许一个五字段 `strategy_input_ref`。任何多 Release 聚合都需要新的 ADR、版本化契约、规范排序/哈希规则和重新验证，不能通过列表兼容或隐式拼接提前引入。

### 3. 正式传输面

KB 的两种正式只读传输面均受支持：

- 版本化只读 HTTP API；
- 授权的不可变导出包。

两种传输必须映射到相同的 Release/Manifest/制品身份并分别记录传输观察。HTTP envelope 或导出包物理字节哈希不能替代公共契约定义的语义 `manifest_hash`。兄弟仓库路径、共享 volume 和本地 KB `published/` 目录不是传输面。

### 4. InvestSystem 自有存储

- SQLite：`var/state/invest_system.sqlite3`，只保存 InvestSystem 自有索引、消费/状态观察、运行、决策及审计元数据；不得成为 KB 事实库副本。
- KB Release 内容寻址缓存：`var/cache/kb-releases/`。
- 缓存软上限：`20 GiB`。达到上限时告警并进入容量复核，不得以软上限为由删除被历史 receipt、Manifest、run 或审计记录引用的制品。
- 只有未被任何历史记录引用的内容才可能成为未来 GC 候选；GC 的宽限期、并发规则和操作流程需另行规格化。在该规格批准前不自动删除缓存内容。
- 缓存、SQLite、日志和运行目录均由 InvestSystem 独占，不与 KB 或题材策略共享可变状态。

### 5. Release 撤回与历史重放

- Release 已撤回、状态无法确认或授权失效时，所有新 run 在策略启动前 `BLOCKED`。
- 已有输入字节、receipt、Manifest、状态观察、决策和审计记录继续保留，不因撤回改写或删除。
- 被撤回 Release 只允许使用原始固定输入进行标记为 `audit_replay` 的历史审计重放；不得据此产生新的当前判断、目标仓位、批准、订单或 paper/live 行为。
- 审计重放仍必须核对原 run 的输入身份和哈希，并明确显示当前撤回状态；不得把缓存伪装成新的 Published Release。

### 6. 工程与权限隔离

- 根级采用 `src/` 包布局、GitHub Actions、规范 JSON 和项目自有 TOML/hash lock。
- 本地可使用 `E:\Conda\envs\Data_Analysis` Python 3.12，但项目只以 editable `--no-deps` 注册，不得导入其中已有的 KB 包。
- required CI 只 checkout InvestSystem，并从 InvestSystem lock 建立隔离环境。
- KB 凭证只允许发布面只读 scope；不得拥有管理写权限。
- `origin` 是唯一正常 push 目标；`upstream` 只允许 fetch，并必须在每个开发 clone 上设置可验证的 no-push 护栏。

### 7. 策略隔离与生产边界

产业事件与题材轮动默认零信号互通，各自持有输入引用、Manifest、规则、状态、账本、验证和 P&L。本 ADR 不批准任何策略规则、自动实盘、券商连接或资金部署。

## 后果

- Stage 1 可以独立建设 provider-neutral 契约、确定性基础设施和测试，不等待 KB 后续数据开发。
- Stage 2A 才能通过显式依赖更新固定 KB 官方公共 Schema/lock/fixture 并实现 Adapter。
- 20 GiB 是运营告警阈值，不是数据保留保证或自动清理授权；容量不足必须显式处置。
- SQLite 选择已确定，但具体表、迁移和并发模型仍需在实现前形成 InvestSystem 自有规格和测试。

## 验证

- 当前 clone 的 `upstream` no-push 验证记录见 [Stage 0 Git remote 护栏验证](../validation/stage0-git-remote-guard.md)。
- Stage 1 架构测试必须持续检查项目依赖、源码、运行路径和 CI 不引用 KB 内部实现。
