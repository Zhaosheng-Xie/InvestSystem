# Stage 6 / 6A 历史验证预注册与准入批准记录 v0.1

批准状态：`approved`

批准时间：`2026-08-19T13:20:26.292292Z`

批准人：`repository_owner`

批准来源：当前 Codex task 中 owner 回复“帮我判断下，没有大风险就批准了”；经复核，本包只批准历史验证治理设计，不开放历史运行或交易权限，因此按第 13 节全部 35 项整包原子批准。

批准范围：`stage6_historical_validation_governance`

## 1. 批准对象

owner 原子批准[《Stage 6 / 6A 历史验证预注册与准入精确规则包 v0.1》](Stage6_6A历史验证预注册与准入精确规则包_v0.1.md)第 13 节全部 35 项。

精确批准来源：

- specification raw SHA-256：`7ef1126261ddbead37c016fe472a8d518cddb553fe3c3d1214f5c378a9b964df`；
- draft machine proposal raw SHA-256：`a071e2509bcf86361836cdd5e5d0748748b607e1129edc4f47c308de7073cdca`；
- draft canonical bundle SHA-256：`41759cb4e4db282d98bc70b3a599f632283d2cf79330adab910b1bc9a308eb92`；
- draft canonical rules SHA-256：`c1d0298488317318b8d9dedde9f1ff719aa83d08af7196d255482e11522dc097`；
- 35 项 draft owner items canonical SHA-256：`ea2b4b9d232884d3cd12b4a8003562261fc8e6c8e8f299b88f1df1fb16e3fcfe`。

原 specification 与 draft machine proposal 保持原始字节不变。批准通过独立 approved bundle、approval record 和 fail-closed verifier 表达，不回写原 draft。

## 2. 风险判断

本包可以批准，原因是它把主要风险锁在后续独立门内：

- 当前 Stage 5D 只覆盖单一 ENTER/BUY bounded replay，不足以支持正式历史总体；未支持样本必须留作 `BLOCKED/ABSTAIN`；
- 样本、coverage 或 PIT 不足时只能输出 `INSUFFICIENT_EVIDENCE`；
- holdout 在规则与参数冻结后才能一次打开，禁止看结果调参；
- 完整系统必须在统一条件下稳定优于最佳简单竞争模型，不能只证明历史收益为正；
- PRD 数值门槛仍是 `hypothesis`，本次没有批准其成为 evaluator 默认值；
- 6B historical admission、6C development/walk-forward 与 6D holdout 都保留独立实现和验收门。

## 3. 三十五项原子批准确认

- [x] `6A-01`：批准 Stage 6 拆分为 6A 预注册治理、6B 准入与原子留存、6C development/walk-forward、6D frozen holdout 冠军挑战，任何前一阶段批准不得替代后一阶段验收。
- [x] `6A-02`：批准本包只形成 `stage6_historical_validation_governance` 草案，当前 allowed run modes 为空，不签发 runtime capability，不执行 backtest/paper/shadow/live。
- [x] `6A-03`：批准精确绑定 PLAN、PRD v0.3、Stage 3D 验收、Stage 5D 预注册/验收和 `caf1e67` 实现基线；任一承重身份漂移必须形成新版本。
- [x] `6A-04`：批准 KB/IS 隔离与产业/题材零信号互通边界，禁止 KB 内部读取、共享写存储或跨策略样本/P&L 混用。
- [x] `6A-05`：批准完整 `HistoricalValidationPreregistration` 内容寻址，并要求冻结时点早于任何本次表现结果读取。
- [x] `6A-06`：批准研究单位为 PIT `event × listed_company × decision_time` 机会，重复公告、同一经济事件、公司和风险簇不得冒充独立样本。
- [x] `6A-07`：批准先登记候选全集，再运行策略门；保留 TRADE_READY、SHADOW_ONLY、REJECT、ABSTAIN、BLOCKED 和无成交结果。
- [x] `6A-08`：批准所有事实、价格、财务、市场规则、Release 状态、修订与更正按实际 `available_at` 进入 PIT 信息集，禁止回写。
- [x] `6A-09`：批准只按时间前进切分 development、walk-forward 和 frozen holdout，并使用覆盖 label overlap 的 purge 与预注册 embargo。
- [x] `6A-10`：批准样本日期、切分比例、purge、embargo、horizon 和最小样本量都是 owner 必填项；缺任一项 6B—6D 失败关闭。
- [x] `6A-11`：批准 holdout 内容寻址、一次冻结、一次打开；结果可见后的规则、特征、门槛、样本、成本或支持矩阵变化只能进入新预注册版本。
- [x] `6A-12`：批准 6B 使用本次新鲜公共状态证据签发 run-scoped `RunReleaseStatusConfirmation`，不得复用 Stage 3D validation-only 对象或 Stage 7 authority。
- [x] `6A-13`：批准 6B 原子固定原始状态证据、Receipt、Observations、StrategyRunManifest、预注册和完整 Release 闭包；任一失败 evaluator 零调用且状态零写。
- [x] `6A-14`：批准撤回或无法确认的 Release 阻止新 run，历史材料仅允许 `audit_replay`，且每个 run 只允许一个 `strategy_input_ref`。
- [x] `6A-15`：批准每轮在看表现前固定 Stage 5D 支持矩阵和事件 closed world，当前单一 ENTER/BUY bounded replay 不足以授权正式历史总体。
- [x] `6A-16`：批准未支持会计/执行输入必须保留为 BLOCKED/ABSTAIN，禁止静默剔除、事后择样扩展或发布 partial NAV/P&L。
- [x] `6A-17`：批准 coverage 是正式完成门；低于 owner 冻结下限时整轮只能 `INSUFFICIENT_EVIDENCE`。
- [x] `6A-18`：批准零假设、no-trade、风险匹配基准、simple E4、simple valuation 和 full system 为首版冠军挑战 closed world。
- [x] `6A-19`：批准所有竞争模型共享候选总体、PIT、执行、成本、持有期和风险预算，完整系统必须稳定优于最佳简单模型才保留复杂度。
- [x] `6A-20`：批准主估计量为扣除全部交易摩擦后的组合级基准增量结果，并要求逐机会 contribution 可追溯；精确 horizon/标准化待 owner 填写。
- [x] `6A-21`：批准同时报告收益、coverage、ABSTAIN/BLOCKED、成交、容量、回撤、尾损、最大赢家、风险簇、换手和成本敏感性。
- [x] `6A-22`：批准风险过滤器、发现工具与执行优势必须单独归因，未经竞争检验不得称为 Alpha 来源。
- [x] `6A-23`：批准置信区间与重采样反映事件/公司/风险簇和时间依赖，随机种子、重采样次数及实现版本在 holdout 前冻结。
- [x] `6A-24`：批准全部假设、参数、特征、消融和指标进入搜索台账；确认性结论使用预注册 multiple-testing family 与调整方法。
- [x] `6A-25`：批准 PRD 的 `30`、`>0`、`95% CI lower >0`、`max drawdown <=15%`、`largest winner <=25%` 当前均为 hypothesis，owner 原子批准前不得进入 evaluator。
- [x] `6A-26`：批准另行冻结 full-vs-best-simple 最小实质增量、coverage 下限、有效样本下限、成本/容量压力和失败容忍度。
- [x] `6A-27`：批准参数搜索空间、顺序、停止规则和全部结果完整登记，holdout 禁止调参或择优重跑。
- [x] `6A-28`：批准对 E0—E7、四道门、利润桥、估值、退出、风险和执行层做消融，并把参数邻域稳定性作为完成门。
- [x] `6A-29`：批准交易费用、税、滑点、冲击、容量、延迟、跳空、停牌、涨跌停和不可成交压力测试。
- [x] `6A-30`：批准幸存者、前视、重复事件、选择性纳入、不可成交和研究者自由度审计，并披露最大赢家/公司/风险簇/时期集中。
- [x] `6A-31`：批准 Stage 6 结果状态 closed world 为 PASS、FAIL、INSUFFICIENT_EVIDENCE、PRECHECK_BLOCKED、AUDIT_REPLAY_ONLY。
- [x] `6A-32`：批准 run、候选、拒绝、ABSTAIN、BLOCKED、错误、搜索和报告 append-only 留存，失败不得被成功重跑覆盖。
- [x] `6A-33`：批准 deterministic replay identity 固定规则、代码、配置、预注册、数据、随机种子和完整输入闭包。
- [x] `6A-34`：批准 6D 只按冻结预注册形成正式报告，并由 owner 作 `go / revise / stop / insufficient_evidence` 决策；历史结果不等于前瞻或 live 证据。
- [x] `6A-35`：批准 6A 全部 35 项必须整包原子批准，部分批准不得签发 capability 或授权部分实现。

## 4. 批准后的权限结论

本批准允许形成精确 6A approved bundle、approval record 和治理 capability，并据此开始形成 6B 的待批准精确规则；它不授权直接实现或执行 6B—6D。

本批准明确不授权：

- 运行真实或合成历史策略、打开 holdout、读取历史表现后调参；
- 签发 `RunReleaseStatusConfirmation` 或写入 historical run 状态；
- backtest、paper、shadow、live；
- 真实账户、仓位、订单、broker 或资金部署；
- 读取或写入 KB 内部状态；
- 把任何 PRD hypothesis 数值解释为正式通过线；
- 把 Stage 5D 单一 ENTER/BUY bounded replay 解释为完整历史会计覆盖。

下一步只能是形成 6B exact admission/transaction 草案；6B 未经 owner 独立批准不得实现。
