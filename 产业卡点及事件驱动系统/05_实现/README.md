# 实现

需求与边界冻结前不进入大规模开发。首个纵向切片分为可并行的策略轨和契约轨，再以正式 Release E2E 汇合：

- 策略轨：`合成策略 fixture → provider-neutral DTO → StrategyRunManifest → E3.5/E4 → 四道门 → 利润桥/预期/估值 → DecisionRecord + replay_hash`；
- 契约轨：`KB 官方 fixture → 独立只读 Adapter → ArtifactConsumptionReceipt + ArtifactFetchObservation + ReleaseStatusObservation → provider-neutral DTO`；
- 正式传输核验：`精确 market-daily Published Release → Manifest/制品/状态/权限/Receipt 验证`，不生成订单/合同策略结论；
- 汇合：`精确 Context Pack Published Release → 同一策略入口 → 真实只读 smoke（允许 ABSTAIN）`。

完整策略、TargetPortfolio 和 paper 成交回放在后续阶段开发，可与正式 Release E2E 并行；正式历史验证须在两支都完成后开始。

本地实现使用工作站级 `E:\Conda\envs\Data_Analysis`（Python 3.12）作为共享开发解释器，但 InvestSystem 必须独立维护 `pyproject.toml`、`requirements-build.in`、带哈希的 runtime/dev lock、TOML 配置、缓存、存储和运行目录。项目只以 editable `--no-deps` 注册；缺包安装前后保存环境基线并运行 `pip check`，不得未经确认改变既有共享包。CI 和可复现验收必须从 InvestSystem lock 创建干净环境。

禁止通过 KB SQLite、`raw/`、`staging/`、兄弟目录 `PYTHONPATH`、KB editable 包、submodule、符号链接或内部 Python import 获取输入；禁止共享 KB 数据库、缓存、迁移和部署 volume。

KB Adapter 只面向已发布公共契约并使用只读权限。Manifest、制品哈希、Schema、撤回状态或知识截止时间任一不合格时，新 run 必须失败关闭为 `BLOCKED`。正式运行禁止解析 `latest`。

策略内核只依赖 provider-neutral DTO。E0—E7、四道门、利润桥、预期、估值、Decision、组合、执行和 P&L 全部属于 InvestSystem，不能回写 KB。

研究、风险和执行必须分层；任何研究 Agent 都不得访问交易凭证或直接提交订单。

第一阶段用 InvestSystem 自有、明确标记的合成策略 fixture 打通完整链路；真实 KB Context Pack 只做只读 smoke/E2E，允许正确结果为 `ABSTAIN`，不得要求 KB 为正例定制事实。

