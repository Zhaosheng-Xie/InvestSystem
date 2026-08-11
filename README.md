# InvestSystem 工作区

本仓库用于设计、实现、验证和维护可复现、可审计的 A 股策略系统。同事提供的原始设想和历史材料保留在文档层；只有经批准的规格、对应代码以及验证证据才能成为系统能力。

根目录既承载项目索引、原始材料和历史归档，也将在工程阶段承载跨策略的机器契约、配置、代码、测试和运行工作区。不同收益机制的策略规格、状态、运行记录和 P&L 仍须相互隔离。

## 实施计划

- [InvestSystem 实施计划 v3.0](PLAN.md)：本仓库唯一正式实施路线图；PLAN v0.4 为批准基线，当前为 `Stage 0—2B completed / Stage 3 in progress / Stage 4 completed_with_scope_limits / Stage 5B—5C completed_with_scope_limits / Stage 5D governance approved，5D-1 not_started`。Stage 3A—3C 已完成，其中 [Stage 3C](docs/validation/stage3c-tcloud-http-acceptance.md)已通过真实 tcloud 公网 HTTPS 的正式 `market_daily` Release/Manifest/Status/artifact 验收；3D 正式 Context Pack 策略 smoke 尚未开始，且当前仍无 run authority。Stage 4 的 14 项 P0 规则和 4B 完整编排已通过匿名合成验收；Stage 5A 四十项规则已精确批准，Stage 5B 已实现历史市场与 synthetic fill，Stage 5C 已实现合成组合风险、五层数量、提交前约束、结算投影和截至运行时点的内存双分录账本。Stage 5D 的 48 项规则现已原子批准并形成独立批准谱系与 fail-closed capability verifier，但完整 5D evaluator、公司行动、NAV/P&L、complete replay 和 SQLite v4 仍未实现，完整生产策略仍不存在。
- `PLAN.md` 只管理阶段、依赖和完成门，不取代 PRD、规则规格、机器契约或测试报告。

Stage 1 已通过[正式验收](docs/validation/stage1-acceptance.md)：独立包装、hash lock、TOML、InvestSystem 自有 draft 契约、provider-neutral DTO、构造级规则成熟度防线、SQLite/内容寻址缓存与准入骨架、合成测试和 Windows/Linux CI 均已验证。该验收只证明当时的工程骨架可安装、可测试、可审计，不应被回溯解释为后续策略能力已经存在。

Stage 2A 已通过[正式验收](docs/validation/stage2a-acceptance.md)。仓库从 KB 公共契约提交 `58ed9c5cb5302e3e719f1696bed83a03c5d6313b` 固定了 20 个官方文件，并完成 provider canonical、契约 catalog、官方 reference fixture 验证/窄投影，以及 InvestSystem 自有 SQLite v3 的 Receipt、append-only Observation、传递留存闭包、run-scoped 当前状态确认、receipt-derived atomic pin 和 legacy v2 quarantine。根 Receipt 只标识本次策略输入的制品，留存闭包另行固定实际依赖的 source Release、Manifest 快照与制品；调用方不能声明任意 pin 子集。Stage 2A 的无参数 transport 门仍在 I/O 前显式失败关闭；当前只有调用方提供完整验证的 `aab36fe` Stage 3 transport catalog 时才启用协议实现。真实 current-status authority 仍为空；Stage 3B 的认证兼容验收没有写入 CAS/Observation，也不能授权新 run。正式 acquisition、持久化与 authority 启用仍须后续明确实现和批准。Stage 2A 本身没有交付任何策略能力。

Stage 2B 已通过[正式验收](docs/validation/stage2b-acceptance.md)：最小订单/合同规则包 22 项、精确批准 capability、24 个正常策略向量、10 个 admission failure 向量、E3.5/E4、四道门、窄版利润桥/预期/估值、完整 DecisionRecord 和确定性 replay 已形成。它只授权匿名合成 `research` validation；不授权 backtest、paper、shadow、live、仓位、组合、订单或资金部署，也不证明策略有效。

Stage 2 进入 Stage 4 的[复核](docs/validation/stage2-reentry-audit.md)已通过。owner 于 `2026-08-08` 恢复 Stage 3；[Stage 3A 离线传输消费者验收](docs/validation/stage3a-acceptance.md)、[Stage 3B 正式跨仓只读 HTTP 验收](docs/validation/stage3b-http-acceptance.md)和[Stage 3C 真实 tcloud 只读 HTTPS 验收](docs/validation/stage3c-tcloud-http-acceptance.md)均已完成，但正式 Context Pack 策略 smoke 和 run authority 尚未通过。Stage 4 已通过[4B 完整合成验收](docs/validation/stage4-4b-acceptance.md)：完整输入从原始 typed case 重新运行 4A-1—4A-4，固定五层 capability 身份、统一 Gate/退出视图与 deterministic replay。该能力只适用于匿名合成 research validation，不读取真实 KB Release，也不授权 backtest、paper、shadow、live、仓位、组合、成交、P&L 或订单。

Stage 5A 的[成交、组合、账本与确定性回放精确规则包](产业卡点及事件驱动系统/03_规则与规格/Stage5_5A成交组合账本与确定性回放精确规则包_v0.1.md)四十项已获 owner 批准；原零权限 draft 保持不变，另建[批准记录](产业卡点及事件驱动系统/03_规则与规格/Stage5_5A成交组合账本与确定性回放批准记录_v0.1.md)、approved machine bundle 和 approval record，并通过[Stage 5A 治理验收](docs/validation/stage5-5a-governance-acceptance.md)。[Stage 5B 验收](docs/validation/stage5-5b-market-execution-acceptance.md)实现历史有效 `MarketRuleSet`、交易日历、首次可成交、固定点成本/冲击、可成交价 Gate 重算和确定性 synthetic fill；[Stage 5C 验收](docs/validation/stage5-5c-portfolio-ledger-acceptance.md)进一步实现受约束候选重算、合成组合风险、现金/可卖量、五层数量、结算投影和内存 append-only 双分录账本。上述能力仍仅限 `stage5_synthetic_execution_validation`，不含非空公司行动、NAV/P&L、SQLite migration、durable full replay 或真实订单权限。

Stage 5D 的[公司行动、估值、P&L、完整回放与原子持久化精确规则包](产业卡点及事件驱动系统/03_规则与规格/Stage5_5D公司行动估值P&L完整回放与原子持久化精确规则包_v0.1.md)仍以原始 draft 字节保留，owner 已原子批准第 13 节全部 48 项；独立[批准记录](产业卡点及事件驱动系统/03_规则与规格/Stage5_5D公司行动估值P&L完整回放与原子持久化批准记录_v0.1.md)、[approved machine bundle](产业卡点及事件驱动系统/03_规则与规格/机器制品/industrial_event_stage5_5d_corporate_action_pnl_replay_persistence_v0.1.0.rule-bundle.json)、[approval record](产业卡点及事件驱动系统/03_规则与规格/机器制品/industrial_event_stage5_5d_corporate_action_pnl_replay_persistence_v0.1.0.approval.json)和治理 verifier 已形成。批准仍只允许 `stage5_synthetic_execution_validation` 下的匿名合成 `research`；5D-1 业务实现尚未开始，5D-2 仍须等待 5D-1 独立验收，当前没有 migration、SQLite v4 写入或新增真实/交易权限。

## 当前项目

- [产业卡点及事件驱动系统](产业卡点及事件驱动系统/README.md)：PRD v0.3 已于 `2026-07-31` 批准；Stage 2B 最小切片与 Stage 4 完整合成 research-validation 引擎均已验收，完整生产策略仍未实现。
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
