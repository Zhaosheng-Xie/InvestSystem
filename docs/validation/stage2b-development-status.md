# Stage 2B 开发状态

> 状态日期：`2026-08-02`
>
> 分支：`codex/stage2b`
>
> 阶段状态：`in_progress`
>
> 当前子阶段：`2B-0 approval-safe contracts implemented / 2B-1 awaiting owner rule approval`
>
> 本文性质：开发状态证据，不是 Stage 2B 正式验收

## 1. 进入裁决

Stage 2A 已完成且没有遗留 P0/P1 阻塞项，Stage 2B 可以开工。用户已授权继续 Stage 2B，但该授权不自动批准 PRD v0.3 中仍标为 `hypothesis` 的业务阈值和场景假设。

因此 Stage 2B 拆为：

- `2B-0`：先实现不产生策略业务结论的 provenance、规则批准和 replay 契约；
- `2B-1`：只有 owner 明确批准最小规则包后，才实现 E3.5/`E4_public`、四道门、利润桥、预期、估值和四类策略结果。

## 2. 已实现的 2B-0 边界

### 2.1 Synthetic validation provenance

`SyntheticValidationInput` 把以下身份固化进规范 JSON，而不是只依赖单条 Fact 的自由 metadata：

- `provenance=invest_system_synthetic`；
- `synthetic=true`、`validation_only=true`；
- `not_a_published_release=true`、`not_strategy_evidence=true`；
- `authorizes_positions=false`、`authorizes_orders=false`；
- `synthetic_`/`synthetic_release_` 独立命名空间；
- 显式 fixture 语义版本；
- 底层 `VerifiedKnowledgeInput` canonical SHA-256 重算与绑定。

正式 KB Release 不经过该包装层，合成输入也不能被改标为正式 Release。

### 2.2 Rule bundle exact approval

规则文档的自报状态不再等于批准能力：

- `RuleBundleDocument` 的完整 canonical bytes 形成唯一 bundle hash；
- `RuleApprovalRecord` 固定 strategy/bundle/version/hash、批准人、UTC 时间、范围和来源记录；
- `RuleApprovalRegistry` 仅在逻辑身份和完整 hash 全部精确匹配、且文档本身已升级为 `approved` 时签发 capability；
- approval ID 复用、同一逻辑版本绑定多个 hash、自称 approved、未知 hash 和空 registry 均失败关闭；
- 当前 `CURRENT_RULE_APPROVAL_REGISTRY` 为空，因此仓库中仍没有可执行策略规则。

### 2.3 Self-excluding replay identity

`ReplayEnvelope` 显式覆盖：

- synthetic input envelope hash 与 provider-neutral verified input hash；
- rule bundle hash、策略/规则版本和规则成熟度；
- 代码提交、配置、环境锁、随机种子、运行模式和注入评价时钟；
- 确定性语义输出。

`replay_hash` 存在 envelope 外。`run_id`、`decision_id`、三类 observation ID、endpoint、观察/持久化时间和 `replay_hash` 自身不能进入语义输出；嵌套出现也会失败关闭。

Synthetic replay builder 直接从完整 wrapper、底层 verified input 和完整 rule bundle 对象派生三类内容哈希，不信任调用方自填 hash；同时要求输入引用、strategy ID、bundle 版本/状态与 Manifest 精确一致，并强制 `research` run mode。

### 2.4 机器契约与隔离

新增四个 InvestSystem 自有 draft JSON Schema：

- `SyntheticValidationInput`；
- `RuleBundleDocument`；
- `RuleApprovalRecord`；
- `ReplayEnvelope`。

架构测试禁止 `domain/` 和未来 `strategies/` 导入 provider integration 或 storage 层。代码和测试不读取 KB 仓库、SQLite、`raw/`、`staging/`、工作树或内部 Python 包。

## 3. 待批准规则草案

[最小订单合同纵向切片规则包 v0.1](../../产业卡点及事件驱动系统/03_规则与规格/最小订单合同纵向切片规则包_v0.1.md) 当前状态为：

- `draft_for_owner_approval`；
- `所有者批准：未取得`；
- `未生效、不可执行`。

草案明确了匿名高速光互连订单/合同合成场景、E3.5/E4、四道门、Decimal/PIT、证据独立性、利润桥、预期、估值、结果短路和五类 golden 设计。它不能被运行时直接解析为规则，也不能在批准前产生 `TRADE_READY/REJECT/ABSTAIN` 业务结论。

## 4. 当前验证证据

工作站共享解释器 `E:\Conda\envs\Data_Analysis\python.exe`：

- `pytest -q`：`442 passed, 4 skipped`；4 项均为当前 Windows 账户缺少 symlink 权限；
- `ruff check .`：通过；
- `ruff format --check .`：通过；
- `mypy`：`42 source files` 通过；
- `compileall -q src tests`：通过；
- `git diff --check`：通过；
- `pip check`：只报告共享环境既有的 OpenCV/NumPy 冲突；本阶段没有安装、升级、降级或卸载任何包，也没有新增依赖冲突。

上述证据证明 2B-0 契约没有破坏 Stage 1/2A 基线，不证明任何策略规则有效。

## 5. 尚未实现

- approved 机器规则 bundle 与非空 owner approval registry；
- Stage 2B 专用 synthetic strategy fixture；
- E3.5/`E4_public` 状态判断；
- Gate 1—4、利润桥、预期分类和情景估值；
- `TRADE_READY`、`SHADOW_ONLY`、`REJECT`、`ABSTAIN` 策略 golden；
- `BLOCKED` admission-before-evaluator 编排证明；
- Stage 2B StrategyRunManifest/DecisionRecord 完整输出；
- Stage 2B 正式验收和完成状态。

真实 HTTP/export/current-status transport 仍属于 Stage 3，不是 Stage 2B 缺口。

## 6. 下一完成门

owner 明确批准规则草案的逐项清单后：

1. 把批准内容转写为严格 canonical 机器 rule bundle；
2. 登记精确 bundle hash 的 `RuleApprovalRecord`，不得靠文档自报状态授权；
3. 实现同一 provider-neutral 策略入口和 typed E/Gate/经济对象；
4. 建立四类正常合成 fixture 与独立 admission failure fixture；
5. 完成五类 golden、阈值邻域、PIT、短路、隔离和 replay 测试；
6. 形成 Stage 2B 正式验收证据后，才可把阶段标为 `completed`。
