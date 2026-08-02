# 实现

需求与边界已于 Stage 0 冻结；Stage 1 的工程与机器契约骨架已经通过根级[正式验收](../../docs/validation/stage1-acceptance.md)，Stage 2A 的离线 Release 消费与准入内核也已通过[正式验收](../../docs/validation/stage2a-acceptance.md)。Stage 2B 已启动，且不产生业务结论的 `2B-0` 已完成；最小规则包经 owner 明确批准后，才进入实现策略语义的 `2B-1`。首个纵向切片随后以正式 Release E2E 汇合：

2B-0 的实际交付和未实现清单见根级 [Stage 2B 开发状态](../../docs/validation/stage2b-development-status.md)。

- 策略轨：`合成策略 fixture → provider-neutral DTO → StrategyRunManifest → E3.5/E4 → 四道门 → 利润桥/预期/估值 → DecisionRecord + replay_hash`；
- 已完成契约轨：`KB 官方 fixture → 离线 validator/projector → ArtifactConsumptionReceipt + Observations + ReleaseRetentionClosure → provider-neutral DTO`；真实只读 Adapter/transport 属于 Stage 3；
- 正式传输核验：`精确 market-daily Published Release → Manifest/制品/状态/权限/Receipt 验证`，不生成订单/合同策略结论；
- 汇合：`精确 Context Pack Published Release → 同一策略入口 → 真实只读 smoke（允许 ABSTAIN）`。

完整策略、TargetPortfolio 和 paper 成交回放在后续阶段开发，可与正式 Release E2E 并行；正式历史验证须在两支都完成后开始。

Stage 2A 已从固定 KB 公共契约提交 `58ed9c5cb5302e3e719f1696bed83a03c5d6313b` 按原始字节引入 20 个官方文件，并验收 provider canonical、契约 catalog、消费 Receipt/Observation、官方 reference fixture 验证/窄投影，以及 SQLite v3 的正式持久化、传递 source Release 留存闭包、run-scoped 当前状态确认、receipt-derived atomic pin 和 legacy v2 quarantine。固定提交尚无锁定的公共 HTTP envelope/OpenAPI、不可变 export-package 或完整 status-event 正文契约，因此两个真实 transport authority 默认禁用并在 I/O 前失败关闭。Stage 2A 只以离线验证/投影/持久化/准入内核为完成范围；真实 acquisition、鉴权、重试、当前状态查询、原始响应留存和 authority 启用进入 Stage 3。

根级采用 `src/` 包布局、GitHub Actions 和规范 JSON。本地实现使用工作站级 `E:\Conda\envs\Data_Analysis`（Python 3.12）作为共享开发解释器，但 InvestSystem 必须独立维护 `pyproject.toml`、`requirements-build.in`、带哈希的 runtime/dev lock、TOML 配置、`var/cache/kb-releases/`、`var/state/invest_system.sqlite3` 和运行目录。项目只以 editable `--no-deps --no-build-isolation` 注册；缺包安装前后保存环境基线并运行 `pip check`，不得未经确认改变既有共享包。CI 和可复现验收必须从 InvestSystem lock 创建干净环境。

禁止通过 KB SQLite、`raw/`、`staging/`、兄弟目录 `PYTHONPATH`、KB editable 包、submodule、符号链接或内部 Python import 获取输入；禁止共享 KB 数据库、缓存、迁移和部署 volume。

KB Adapter 只面向已发布公共契约并使用只读权限。版本化 HTTP API 与不可变导出包是两个传输入口，但必须汇入相同的 Release validator、确定性 receipt 和 provider-neutral DTO。首版每个 run 只接受一个 `strategy_input_ref`。Manifest、制品哈希、Schema、撤回状态或知识截止时间任一不合格时，新 run 必须失败关闭为 `BLOCKED`。正式运行禁止解析 `latest`。

Release 撤回后保留固定历史材料，只允许走独立的 `audit_replay` 路径；该路径不得创建新的当前 DecisionRecord、仓位、批准或订单。SQLite 只保存 InvestSystem 消费、运行和审计索引，不保存 KB 内部事实表。

Stage 1 已实现的根级工程能力包括：

- `Clock`、`SystemClock` 与 `FixedClock`，所有运行时间必须显式读取并校验为 UTC；
- provider-neutral draft DTO、规范 JSON、SHA-256 和固定 Manifest golden；
- SQLite `user_version=1` 的本项目状态层，以及 SHA-256 内容寻址缓存；
- 原子缓存写入、读回重验、幂等 artifact 映射、20 GiB 软阈值报告和零自动删除；
- 原子核对最新 provider 状态与本地准入后，按 run 固定精确 artifact 子集；撤回后阻止普通读取和新 pin，只允许通过独立 `AuditReplayRequest` 读取既有 pin 的审计上下文；
- pytest、Ruff、mypy、双平台 GitHub Actions 和跨仓隔离测试。

Stage 2A 本轮在该骨架上新增：

- `ReleaseRetentionClosure` 机器契约，显式保存根 Release 到 source Release 的传递依赖，不从 fixture 中“出现过的全部 Release”猜测闭包；
- 完整 sealed Manifest 文档快照、物理文档哈希/大小与 provider 的 self-excluding `manifest_hash` 分开保存，并共同进入闭包身份；
- 三类 Observation 的完整 canonical bytes、从 sequence 1 开始的连续 provider status previous-hash 链、线性 `supersedes` 与不可回拨当前 head；
- `pin_run(manifest, confirmation)` 只从持久 Receipt/闭包推导 root、source Manifest 和制品 pin，并要求受信、未过期、run-scoped 的确认精确覆盖全部闭包 Release；默认 authority 集合为空，所以未固定真实传输契约时所有新 run 失败关闭；
- Receipt/closure canonical aggregate、关系索引、CAS 字节与 `persisted_at <= run.created_at <= pin clock` 在 pin/read 时重核；撤回或无法确认后阻止新 pin 和普通读取，既有完整闭包只供显式 `audit_replay`。
- 非空 SQLite v2 无损迁移时为全部旧 pin 写入不可变 quarantine；直接注入 confirmation/binding 也不能把旧 run 恢复为普通运行。

缓存和状态层的行为边界见根级 [存储与 Release 缓存说明](../../docs/storage-and-cache.md)。这些能力仍不包含 HTTP/export transport、真实 Release 当前状态获取或任何策略规则语义。

策略内核只依赖 provider-neutral DTO。E0—E7、四道门、利润桥、预期、估值、Decision、组合、执行和 P&L 全部属于 InvestSystem，不能回写 KB。

研究、风险和执行必须分层；任何研究 Agent 都不得访问交易凭证或直接提交订单。

第一阶段用 InvestSystem 自有、明确标记的合成策略 fixture 打通完整链路；真实 KB Context Pack 只做只读 smoke/E2E，允许正确结果为 `ABSTAIN`，不得要求 KB 为正例定制事实。

