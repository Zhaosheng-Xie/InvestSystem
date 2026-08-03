# InvestSystem 工作区

本仓库用于设计、实现、验证和维护可复现、可审计的 A 股策略系统。同事提供的原始设想和历史材料保留在文档层；只有经批准的规格、对应代码以及验证证据才能成为系统能力。

根目录既承载项目索引、原始材料和历史归档，也将在工程阶段承载跨策略的机器契约、配置、代码、测试和运行工作区。不同收益机制的策略规格、状态、运行记录和 P&L 仍须相互隔离。

## 实施计划

- [InvestSystem 实施计划 v1.5](PLAN.md)：本仓库唯一正式实施路线图；PLAN v0.4 为批准基线，当前为 `Stage 0—2B completed / Stage 3 deferred by owner / Stage 4 in progress`。Stage 3 的完成门仍保留并在正式历史验证前补齐；Stage 4 的 4A-1 已实现，4A-2 仅形成等待 owner 批准的精确 draft，不代表事件 evaluator 或完整策略已实现。
- `PLAN.md` 只管理阶段、依赖和完成门，不取代 PRD、规则规格、机器契约或测试报告。

Stage 1 已通过[正式验收](docs/validation/stage1-acceptance.md)：独立包装、hash lock、TOML、InvestSystem 自有 draft 契约、provider-neutral DTO、构造级规则成熟度防线、SQLite/内容寻址缓存与准入骨架、合成测试和 Windows/Linux CI 均已验证。该验收只证明当时的工程骨架可安装、可测试、可审计，不应被回溯解释为后续策略能力已经存在。

Stage 2A 已通过[正式验收](docs/validation/stage2a-acceptance.md)。仓库从 KB 公共契约提交 `58ed9c5cb5302e3e719f1696bed83a03c5d6313b` 固定了 20 个官方文件，并完成 provider canonical、契约 catalog、官方 reference fixture 验证/窄投影，以及 InvestSystem 自有 SQLite v3 的 Receipt、append-only Observation、传递留存闭包、run-scoped 当前状态确认、receipt-derived atomic pin 和 legacy v2 quarantine。根 Receipt 只标识本次策略输入的制品，留存闭包另行固定实际依赖的 source Release、Manifest 快照与制品；调用方不能声明任意 pin 子集。真实 current-status authority 默认为空，且两种批准 transport 都会在 I/O 前显式失败关闭，因此官方 fixture 不能授权新 run。HTTP/export acquisition、完整 status-event 正文、认证 transport、原始响应留存和真实 authority 启用归入 Stage 3。Stage 2A 本身没有交付任何策略能力。

Stage 2B 已通过[正式验收](docs/validation/stage2b-acceptance.md)：最小订单/合同规则包 22 项、精确批准 capability、24 个正常策略向量、10 个 admission failure 向量、E3.5/E4、四道门、窄版利润桥/预期/估值、完整 DecisionRecord 和确定性 replay 已形成。它只授权匿名合成 `research` validation；不授权 backtest、paper、shadow、live、仓位、组合、订单或资金部署，也不证明策略有效。

Stage 2 进入 Stage 4 的[复核](docs/validation/stage2-reentry-audit.md)已通过。owner 于 `2026-08-03` 决定本轮跳过 Stage 3、启动 Stage 4；Stage 3 标为 `deferred` 而非完成。Stage 4 当前处于 [4A rule governance](docs/validation/stage4-development-status.md)：14 项 P0 inventory 中 4A-1 的四项已批准并实现局部合成 research-validation evaluator；4A-2 的四项已有精确 draft 规则与机器提案，但 16 项业务语义尚待 owner 批准、没有 evaluator 或 capability。其余 10 项仍为 `draft`，所以完整 Stage 4 runtime capability 继续关闭。

## 当前项目

- [产业卡点及事件驱动系统](产业卡点及事件驱动系统/README.md)：PRD v0.3 已于 `2026-07-31` 批准；Stage 2B 最小合成 research-validation 切片已验收，Stage 4 规则治理已启动，完整产业策略仍未实现。
  - 第一读物：[需求文档 v0.3](产业卡点及事件驱动系统/01_需求/产业卡点及事件驱动系统_PRD_v0.3.md)
  - 研究裁决：[框架审计与研究结论 v0.1](产业卡点及事件驱动系统/02_研究/框架审计与研究结论_v0.1.md)
- [题材扩散与资金轮动系统](题材扩散与资金轮动系统/README.md)：独立、延后的研究轨道，需求与规则尚未冻结；默认不向产业策略提供信号。
  - 第一读物：[题材轮动独立立项评估 v0.1](题材扩散与资金轮动系统/02_研究/题材轮动独立立项评估_v0.1.md)

## 根级工程目录

以下目录已开始按阶段建立；目录存在只代表对应骨架或测试存在，不代表其中规划的策略能力已经实现：

- `contracts/`：InvestSystem 自有契约，以及固定版本的外部提供方契约。
- `config/`：版本化、可审计且不包含凭证的配置。
- `src/`：策略、集成、组合、执行和审计代码。
- `tests/`：契约、单元、黄金案例、回放、集成和验收测试。
- `var/`：InvestSystem 自有运行工作区；KB Release 缓存在 `var/cache/kb-releases/`，状态索引使用 `var/state/invest_system.sqlite3`。它不作为源码提交，也不与 KB 共享。

## 本地环境与依赖管理

Stage 1 本地开发复用 `E:\Conda\envs\Data_Analysis` 的 Python 3.12，但它只作为工作站级共享解释器。InvestSystem 将独立维护：

- `pyproject.toml`：项目元数据、Python 范围和直接依赖；
- `requirements-build.in`、`requirements.lock`、`requirements-dev.lock`：构建来源及带哈希的完整 runtime/dev 依赖锁；
- `config/default.toml`：不含凭证的运行默认配置，与依赖声明分离；
- `docs/environment-baseline.md`：安装前后 Conda、pip 和 `pip check` 基线。

已批准的 KB 边界、单输入引用、双传输面、SQLite、缓存和撤回政策见 [ADR-0001](docs/adr/ADR-0001-kb-investsystem-boundary.md)。KB Release 缓存固定在 `var/cache/kb-releases/`，软上限 `20 GiB`；历史引用制品不得自动删除。

项目自身已以 `python -m pip install -e . --no-deps --no-build-isolation` 注册。安装前后唯一新增的是 InvestSystem editable 包，没有升级、降级或卸载既有共享包。确实缺少的包可以在精确锁定并核对影响后安装到 `Data_Analysis`，但不得未经确认改变既有共享包。当前环境仍只有复用前已存在的 OpenCV/NumPy 冲突；正式 CI 和可复现验收从 InvestSystem 自有 lock 建立干净环境。

## 资料区

- `原始文档/`：用户提供的原始投资框架与深度研究报告。作为输入基线保留，不直接改写。
- `归档/`：上一轮研究输出与页面验收截图。仅供追溯，不代表当前生效规则。

## 文件生效规则

1. 原始材料只提供观点和案例，不自动成为交易规则。
2. `01_需求/` 定义系统为什么做、做什么、何时算完成。
3. 规则只有在 `approved` 且批准 scope 明确包含目标运行模式时才可进入该模式；Stage 2B 的批准不包含回测。
4. 带 `draft`、`hypothesis` 或 `placeholder` 的参数禁止用于实盘。
5. 任何允许进入 paper，或未来另行获准进入 live 的版本，都必须能追溯到精确 KB 输入引用、消费回执、`StrategyRunManifest`、规则版本、测试报告和人工批准记录。
