# Stage 6 / 6C 开发样本、Walk-Forward 与冠军挑战精确规则包 v0.2

状态：`draft_for_owner_approval`

适用策略：`industrial_bottleneck_event`

拟议批准 scope：`stage6_development_walk_forward_validation`

版本关系：`supersedes` [v0.1](Stage6_6C开发样本WalkForward与冠军挑战精确规则包_v0.1.md)

本文针对 v0.1 方法复核发现的五项重大风险形成集中修订。v0.1 specification SHA-256 固定为 `bcf77c5608eb09fd3e591f0bd92a3e0e71a27c42c18123e26e98080db9609383`，v0.1 draft machine raw SHA-256 固定为 `03e6717ab0de1b2c595e46b7a2a25c5cd3947ba9942a6e939f21636ce114e881`。除本文明确替换的规则外，v0.1 其余规则原样进入 v0.2 完整语义。

v0.2 当前仍不签发 capability，不运行历史样本，不读取 holdout，不修改正式状态库，也不授权 backtest、paper、shadow、live、仓位、订单或资金部署。

## 1. 修订一：Holdout 必须技术隔离

### 1.1 两类制品

正式 6C 只允许获得 `Stage6CDevelopmentProjection`：

- 只包含 `decision_time < 2026-01-01T00:00:00+08:00` 的 development/walk-forward 输入；
- 精确绑定原始根 Release closure、projection rule/version/code/config/hash；
- 保存候选全集、历史日历、benchmark、market rules、marks 和支持矩阵所需字段，但不含任何 holdout record、count、summary、schema-derived cardinality 或表现代理；
- 由独立 holdout custodian 在 6C runtime 启动前生成并封存。

6C 只能看到 `Stage6DHoldoutCommitment`：

- 固定 holdout 时间范围、源 closure hash、opaque holdout artifact commitment、custodian identity、生成代码/config hash 和 `sealed_at`；
- 不包含 record count、候选 ID、收益、状态分布、coverage、文件大小或其他可推断表现的信息；
- commitment 只能证明未来 6D 使用的字节已经冻结，不能让 6C 解密或读取字节。

### 1.2 访问隔离

- development projection 与 holdout artifact 必须位于不同 CAS namespace/不可变包，并使用不同 OS ACL 或独立只读凭据；
- 6C 进程身份、容器/用户、工作目录、cache root 和 Token 对 holdout 路径均无读取权限；holdout 不得被 mount、复制或链接到 6C；
- 同一个物理 artifact 同时包含 pre-2026 与 holdout 记录时，不得直接作为 6C 输入，必须先由 custodian 生成 projection；
- 6C preflight 必须实际尝试读取一个无敏感内容的 holdout canary，并证明访问被拒绝；审计日志中本轮 holdout read count 必须为 `0`；
- 任何权限、路径、commitment、custodian 或 access-log 不闭合时，6C evaluator 调用为 `0`，结果为 `PRECHECK_BLOCKED`。

6D 解封必须使用独立 capability、不同凭据和 owner 明确批准。即使隔离完全通过，2026 仍只能称为 `locked_historical_holdout`；由于这些年份可能已参与人类规则设计，它不是严格未知样本，真正未知证据仍属于 Stage 7。

## 2. 修订二：统计门与多重检验形成同一个进入门

`READY_FOR_6D_FREEZE` 除 v0.1 全部门槛外，还必须同时满足：

1. full-vs-benchmark 与 full-vs-frozen-best-simple 的主 calendar-block bootstrap `95%` CI lower 均 `>0`；
2. 两个比较各自的 company-cluster sensitivity `95%` CI lower 均 `>0`；
3. 两个比较各自的 risk-cluster sensitivity `95%` CI lower 均 `>0`；
4. v0.1 五项 confirmatory family 的 Holm-Bonferroni adjusted p-value 全部 `<=0.05`；
5. 任一 raw CI 通过但 adjusted p-value、company sensitivity 或 risk sensitivity 未通过时，不能进入 6D。

所有检验使用双侧零假设。CI 与 p-value 必须保存未调整值、排序、Holm 阈值、调整值及拒绝/不拒绝结论；不得只保存最终布尔值。

## 3. 修订三：Portfolio 事实与 Bootstrap 抽样层分开

### 3.1 唯一原始组合事实

每个模型/fold 必须先从原始候选、历史规则、执行、风险、Ledger 和 marks 完整 source-driven 重放，得到唯一 canonical daily NAV、daily benchmark NAV 和逐机会 contribution。调用方提供的收益、NAV、贡献或 PASS 一律不可信。

在原始样本中必须满足：

`sum(all opportunity contribution) == ending NAV - beginning NAV - external flow`

本轮外部现金流必须为零；任何非零 external flow 直接 `PRECHECK_BLOCKED`。

### 3.2 主时间依赖 Bootstrap

主推断只对已经由完整组合重放产生的 `daily_excess_return` 做 calendar-block bootstrap：

- block 是自然季度内连续、完整的交易日序列；季度边界和交易日来自 pinned calendar；
- 每次从完整季度 blocks 有放回抽取，保持 block 内日期顺序，按抽取顺序拼接，直到覆盖原样本交易日数，最后一个 block 超出部分确定性截断；
- 不重新计算或单独抽样逐机会 contribution，不把 contribution 简单相加冒充组合 NAV；
- 重采样 series 只用于估计原始 source-driven portfolio estimator 的抽样不确定性，不产生新的账本或历史事实；
- 10,000 次、seed `20260820`，抽样 block IDs 和每次统计量进入可重放制品。

### 3.3 公司与风险簇敏感性

company 和 risk-cluster sensitivity 分别在已对账逐机会 contribution 上执行 cluster wild bootstrap：

- 对每个冻结候选和每个 comparator 先形成 `d_i = (full_net_contribution_i - comparator_net_contribution_i) / fold_beginning_NAV`；某模型未交易时该模型 contribution 为 `0`，候选不得删除；
- `sum(full_net_contribution_i - comparator_net_contribution_i)` 必须等于两模型 ending P&L 差，敏感性估计量为全部冻结候选 `d_i` 的算术平均；
- company path 的 cluster key 为 `listed_company_id`；risk path 为 `risk_cluster_id`；
- 先计算 `e_i = d_i - mean(d)`；同 cluster 的全部 `e_i` 使用同一个 Rademacher `{-1,+1}` multiplier，bootstrap draw 为 `mean(d) + mean(multiplier_cluster(i) * e_i)`；
- multiplier stream 分别使用 seed `20260821` 与 `20260822`，各 10,000 次；
- CI 使用上述 draws 的双侧 percentile `95%` 区间；零假设 p-value 使用 centered draws `mean(multiplier_cluster(i) * e_i)` 计算双侧尾部比例；
- contribution 总额必须先与 canonical portfolio P&L 对账，任何差异 `RECONCILIATION_BLOCKED`；
- sensitivity 只验证 cluster 依赖下结论是否稳定，不能替代主 calendar-block 组合估计量。

## 4. 修订四：Coverage 必须同时通过数量门与选择偏差门

`HistoricalDataReadinessReport` 必须在任何收益、label 或表现 summary 可读之前冻结 support flag 和 `CoverageSelectionAudit`。

### 4.1 Outcome-blind 特征

审计只使用 decision time 已可得且不含未来收益的特征：年份、一级行业、事件类型、E4 状态、流通市值、过去 20 日 ADV、过去 120 日 Beta、停牌/涨跌停状态和 support-failure category。禁止使用未来收益、退出类型、最终公司行动结果或任何 label。

### 4.2 精确门槛

除 v0.1 总 coverage `>=80%`、每年 `>=70%` 外，还必须满足：

- 对流通市值、ADV 和 Beta，supported/unsupported 的绝对 standardized mean difference 每项 `<=0.10`；
- 对年份、行业、事件类型、E4 和当时证券状态，每个 material category 的绝对比例差 `<=0.10`；
- material category 定义为候选总数占比 `>=5%` 且候选数 `>=15`；
- 每个 material category coverage `>=60%`；
- unsupported 少于 15 个时仍报告全部个体，但 selection-bias 门不因小样本宣称“已证明无偏”，只允许随总 coverage 门继续并附强制 caveat；
- 任一可计算门失败、特征缺失或 support flag 在 outcome 可见后改变，整轮只能 `INSUFFICIENT_EVIDENCE`。

所有分母使用冻结候选全集，空分母、缺失值或无法匹配不得静默跳过。该审计只能降低结论权限，不能证明未观测缺失机制不存在。

## 5. 修订五：主估计量与 Benchmark 公式唯一化

### 5.1 每日收益

正式 6C 不允许外部现金流。对每个 pinned trading session `t`：

`strategy_return_t = NAV_t / NAV_(t-1) - 1`

`benchmark_return_t = benchmark_NAV_t / benchmark_NAV_(t-1) - 1`

`daily_excess_factor_t = (1 + strategy_return_t) / (1 + benchmark_return_t)`

任一 NAV 非正、日期不连续、策略与 benchmark 日历不一致或分母为零时 `RECONCILIATION_BLOCKED`。无持仓日必须保留，现金收益首版固定为 `0`。

### 5.2 Fold 主估计量

设 fold 含 `N` 个合法交易日：

`gross_excess_factor = product(daily_excess_factor_t for all t)`

`annualized_net_excess_percentage_points = (gross_excess_factor ** (252 / N) - 1) * 100`

`N` 必须大于 0；使用完整精度判门，显示舍入不参与比较。少于 126 个交易日的 fold 只作描述，不能满足 `READY_FOR_6D_FREEZE`。

### 5.3 Benchmark NAV

- benchmark 使用 v0.1 已冻结的 PIT peer-matched fallback；
- 每个策略目标在相同首次可成交时点、相同现金占用、风险预算和持有/退出时钟建立对应 peer basket；
- peer basket 承担相同费用、税、滑点、冲击、容量和无法成交约束；
- peer basket 权重只在目标建立、目标数量改变或目标退出时同步调整，不做额外择时；
- benchmark 的 delisting、停牌、公司行动和 mark 也必须在 Stage 5D 支持矩阵内，不能使用无摩擦指数收益替代；
- benchmark 任一组成证券不支持时，该候选按相同 coverage/unsupported 规则处理，不能只删除 benchmark 失败。

## 6. v0.2 完整 Owner 批准清单

以下 40 项构成 v0.2 原子批准对象。未明确修改的项目保持 v0.1 语义；标注“v0.2 替换”的项目以本文为准。

- [ ] `6C-01`：批准 6C 只负责 development/walk-forward 与 champion freeze，不打开 6D holdout，不产生 Stage 6 最终 PASS 或任何交易权限。
- [ ] `6C-02`：批准 scope 为 `stage6_development_walk_forward_validation`；当前 draft 零 capability，批准后第一步仍只允许匿名合成 kernel 验收。
- [ ] `6C-03`：批准精确绑定 PLAN/PRD、6A/6B、Stage 5D、v0.1 specification/draft 和固定 KB transport identities。
- [ ] `6C-04`：批准正式 6C 必须消费正式状态层重读复核的 exact HistoricalRunAdmissionSeal，禁止复用 6B validation-only seal。
- [ ] `6C-05`：批准 v0.1 时间切分，并以根 knowledge cutoff 作为 inclusive instant 上界。
- [ ] `6C-06`：批准 `Asia/Shanghai` calendar、UTC canonical instant 和左闭右开区间语义。
- [ ] `6C-07`：批准研究单位、候选先登记及经济事件/公司/时间风险簇独立性规则。
- [ ] `6C-08`：批准所有候选、REJECT、ABSTAIN、BLOCKED、退市和无成交进入全集，禁止成功样本先筛选。
- [ ] `6C-09`：批准 effective/available/decision/knowledge-cutoff PIT 关系，当前快照不得回填历史。
- [ ] `6C-10`：批准主 horizon 60 sessions，20/120 sessions 只作非确认性稳健性。
- [ ] `6C-11`：批准 label 完整结束、120-session purge、20-session embargo，caller 不得自选训练 ID。
- [ ] `6C-12`：批准以第 1 节 development projection、opaque commitment、独立 ACL/凭据、canary 和零读取审计技术隔离 holdout；2026 只称 locked historical holdout。
- [ ] `6C-13`：批准任何表现读取前完成 content-addressed HistoricalDataReadinessReport 和逐候选缺口清单。
- [ ] `6C-14`：批准 Stage 5D 支持矩阵绑定精确实现；当前受限 5D-1 不满足正式 6C。
- [ ] `6C-15`：批准 unsupported 保留为 ABSTAIN/BLOCKED，禁止 partial NAV/P&L、静默剔除、零收益替代或择样重跑。
- [ ] `6C-16`：批准总/年度 coverage 数量门与第 4 节 outcome-blind SMD、比例差、material-category coverage 选择偏差门必须同时通过。
- [ ] `6C-17`：批准至少 30 个独立已结束交易、每 fold 至少 5 个；子组少于 15 只作描述。
- [ ] `6C-18`：批准 v0.1 五模型 exact semantics 和仅用 development 冻结一次 best-simple。
- [ ] `6C-19`：批准所有模型共享候选、PIT、horizon、执行、成本、容量、风险预算和组合时钟。
- [ ] `6C-20`：批准 full system 只用本轮前 approved 唯一配置，6C 不搜索业务阈值。
- [ ] `6C-21`：批准第 5 节零外部现金流、每日 excess factor、252-session annualization、最短 126 sessions 和 exact benchmark NAV 公式替换 v0.1 概括定义。
- [ ] `6C-22`：批准 v0.1 收益、coverage、失败、成交、容量、风险、集中、换手、成本和 exposure 必报指标。
- [ ] `6C-23`：批准 full-vs-benchmark 主 calendar-block、company-cluster 与 risk-cluster 三条 95% CI lower 均严格大于 0。
- [ ] `6C-24`：批准 full-vs-frozen-best-simple 年化净增量至少 2.0 percentage points，且三条推断路径 95% CI lower 均严格大于 0。
- [ ] `6C-25`：批准最大回撤 `<=15%`、最大赢家贡献 `<=25%`，总净利润非正不得绕过赢家门。
- [ ] `6C-26`：批准至少 3/4 folds 净超额为正、最差 fold不低于 -10 percentage points。
- [ ] `6C-27`：批准第 3 节 calendar-quarter daily-return bootstrap 与 company/risk Rademacher cluster wild bootstrap、三组固定 seed 和各 10,000 次。
- [ ] `6C-28`：批准五项 family 的 Holm-Bonferroni adjusted p-value 全部 `<=0.05`，并保存完整 raw/adjusted inference trail。
- [ ] `6C-29`：批准未登记参数搜索禁止；exploratory 结果不能进入当前 champion。
- [ ] `6C-30`：批准正式批量前必须通过既有 golden、PIT/withdrawal/不可成交/mark 负例和确定性 replay 门。
- [ ] `6C-31`：批准八类消融只作归因和证伪，不参与 champion 选择。
- [ ] `6C-32`：批准摩擦、延迟、容量、不可成交与 mark 压力 closed world，并要求 1.5× 摩擦下净基准超额非负。
- [ ] `6C-33`：批准 100,000 CNY 主场景和 300,000 CNY 容量压力，不改变风险比例。
- [ ] `6C-34`：批准幸存者、前视、重复事件、选择性纳入、不可成交和研究者自由度审计为 P0 门。
- [ ] `6C-35`：批准每 fold 原子封存完整输入、逐机会、账本、统计、压力、失败和搜索制品，失败不得覆盖。
- [ ] `6C-36`：批准 replay identity 覆盖 seal/prereg/candidates/support/rules/code/config/data/model/fold/seed/outputs，动态获取 meta 只作观察。
- [ ] `6C-37`：批准 phase outcome closed world，READY_FOR_6D_FREEZE 只代表 6D 进入资格。
- [ ] `6C-38`：批准即使规则获批也只先授权匿名合成 kernel；正式 development/walk-forward 仍须 owner 独立授权。
- [ ] `6C-39`：批准 6D 只以独立 capability 解封一个 frozen champion、完整 6C seals 和第 1 节 opaque holdout commitment；任何提前访问或身份变化使请求失效。
- [ ] `6C-40`：批准 v0.2 全部 40 项必须整包原子批准；部分、pending、拒绝、identity drift 或缺验收均保持零 runtime authority。

## 7. 批准后的唯一顺序

1. 保留 v0.1 specification、draft machine proposal 和验收原始字节；
2. 冻结本文及 v0.2 draft machine proposal；
3. owner 原子批准或调整第 6 节 40 项；
4. 形成完整物化的 approved bundle、approval record 和治理验收，运行时不得动态合并 v0.1/v0.2 Markdown；
5. 只实现匿名合成 holdout-isolation/candidate/fold/statistics/replay kernel；
6. 另行关闭正式 admission、PIT readiness、Stage 5D support 和正式 6C 执行授权；
7. 6C 全部门通过后，才可形成独立 6D unlock 请求。

任一 holdout access、selection-bias、reconciliation、adjusted inference、coverage、样本或支持门失败都必须停止，不得降级为静默 caveat 后继续。
