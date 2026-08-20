# Stage 6 / 6C 开发样本、Walk-Forward 与冠军挑战精确规则包 v0.1

状态：`draft_for_owner_approval`

适用策略：`industrial_bottleneck_event`

拟议批准 scope：`stage6_development_walk_forward_validation`

本文只冻结 Stage 6C 的开发样本、时间顺序 walk-forward、竞争模型、统计、压力、留存和进入 6D 的规则。当前文件不签发 capability，不运行正式历史样本，不打开 frozen holdout，不修改正式状态库，不执行 backtest、paper、shadow、live，不产生真实仓位、订单或资金部署。

## 1. 6C 的唯一目标

6A 已批准必须在查看表现前冻结样本、竞争模型、统计和失败语义；6B 已完成隔离 validation-only admission/seal，但没有正式 historical run authority。6C 的目标不是证明策略有效，而是形成一个可证伪的开发与 walk-forward 实验：

1. 在同一候选总体、PIT 信息集、历史市场规则、成本、风险预算和会计支持矩阵下比较完整系统与简单模型；
2. 完整登记 golden、候选、拒绝、`ABSTAIN`、`BLOCKED`、无成交、参数敏感性和失败；
3. 只在 development/walk-forward 中形成一个冻结 champion；
4. 达到精确完成门时只取得“可进入 6D”的资格，不产生 Stage 6 最终 `PASS`，更不产生 Stage 7 或交易权限。

当前 Stage 5D-1 只覆盖单一匿名合成 ENTER/BUY bounded replay，不能生成本包要求的正式总体和至少 30 笔已结束交易。批准本包不得把该缺口解释为已关闭，也不得把一天 mark-to-market 结果冒充完整事件交易。

## 2. 阶段与权限边界

| 工作 | 本草案是否允许 |
|---|---:|
| 固定 6C 规则、日期、指标、阈值和失败语义 | 是，待 owner 原子批准 |
| 使用匿名合成 fixture 实现纯 runner/statistics kernel | 批准后可另行授权与验收 |
| 消费 6B validation-only seal 执行正式历史样本 | 否 |
| 正式 development / walk-forward run | 否，须正式 6B run seal 与独立执行授权 |
| 打开 2026 frozen holdout | 否，属于 6D |
| 改动 Stage 4/5 业务规则以改善结果 | 否 |
| paper / shadow / live / 仓位 / 订单 | 否 |

6C 实现必须位于应用/验证层，只消费 provider-neutral 已验证输入与重读复核后的正式 admission seal。策略目录不得发 HTTP、解析 KB 响应或自行签发状态 authority。

## 3. 精确上游与正式执行前置门

机器草案必须内容寻址绑定：

- PLAN v3.11、产业 PRD v0.3；
- Stage 6A approved bundle、approval record 和治理验收；
- Stage 6B approved bundle、approval record、离线实现验收与真实 HTTPS validation-only seal 验收；
- Stage 5D 第一条订单/合同回放预注册、受限验收和精确实现提交；
- KB transport snapshot `aab36fe229104779b50ec71e2dc37a9fad81d285` / lock `02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169`。

正式 6C run 开始前还必须另有：

1. owner 批准的完整 `HistoricalValidationPreregistration`，不存在 `TBD/pending/hypothesis` 承重字段；
2. 正式状态层中重读复核的 exact `HistoricalRunAdmissionSeal`，不得复用 6B validation-only seal；
3. 对总体、PIT 历史深度、交易日历、benchmark、market rules、marks 和公司行动的完整 data-readiness receipt；
4. 覆盖本包 60-session 主 horizon 和已结束交易的 Stage 5D 支持矩阵；
5. 从未访问 6D holdout 结果的机器证据。

任一前置门缺失时，正式 evaluator 调用必须为零，结果为 `PRECHECK_BLOCKED` 或 `INSUFFICIENT_EVIDENCE`，不得用合成 fixture、validation-only seal 或 KB 当前快照补位。

## 4. 时间总体、切分与标签

### 4.1 时间口径

- 时区：`Asia/Shanghai`；所有 canonical 时间保存为 UTC instant，同时保留交易日历版本。
- 总体 decision time 范围：`[2019-01-01T00:00:00+08:00, 2026-07-29T00:00:00+08:00)`。
- 任何 decision time 还必须 `<= 2026-07-28T14:13:31.303929Z` 根 Release knowledge cutoff；本地日期上界不能放宽该 instant。
- development/calibration：`[2019-01-01, 2022-01-01)`。
- walk-forward evaluation folds：`2022`、`2023`、`2024`、`2025` 四个自然年，均为左闭右开。
- frozen holdout：`[2026-01-01, 2026-07-29)`，6C 只固定 identity/hash，不读取结果。

上述年份可能已参与研究设计，因此 6C/6D 仍只属于历史证据；真正未知样本必须来自 Stage 7 前瞻登记。

### 4.2 Horizon、purge 与 embargo

- 主 label/mark horizon：首次合法可成交后第 `60` 个交易日收盘；提前触发已批准退出时按退出时点结束。
- 次要、非确认性 horizon：`20` 与 `120` 个交易日，只作稳健性披露，不参与 champion 选择。
- 训练行只有在其完整 label end 早于当前 evaluation fold start 时才可进入。
- purge：从训练集中删除所有 label interval 与 evaluation interval 相交的机会，最长按 `120` 个交易日处理。
- embargo：evaluation fold start 前额外保留 `20` 个交易日信息隔离；等号位于隔离区，不能进入训练。

每个 fold 的训练集是当时全部满足上述 predicate 的历史机会，不允许 caller 提交自选训练 ID。

## 5. 候选总体、PIT 与独立性

研究单位继续是 `economic_event_id × listed_company_id × decision_time`。登记顺序固定为：

`候选发现 → PIT/identity 去重 → 支持矩阵预检 → 策略判断 → 执行/账本 → 指标`

候选全集必须先于 Gate 和成交结果冻结，包含所有成功、失败、退市、被否决、`ABSTAIN`、`BLOCKED` 和无成交机会。相同经济事件的多份材料、同一公司连续公告或同一客户订单不得拆成独立交易。

任何事实、修订、价格、mark、规则、benchmark 成分或 Release 状态必须满足：

`effective_at <= decision_time` 且 `available_at <= decision_time <= knowledge_cutoff`

无法证明历史可得性的字段一律不可用。当前 2026 Context Pack 若不能证明历史时点完整视图，只能进入 data-readiness failure，不得从当前内容回填旧决策。

## 6. Data readiness 与 Stage 5D 支持矩阵

在读取任何收益汇总前，6C 必须生成内容寻址 `HistoricalDataReadinessReport`：

- 每年候选总数、PIT 完整数、支持数、无成交数和各失败原因；
- Release/Manifest/Schema/日历/市场规则/benchmark/mark 覆盖；
- 退出、SELL、公司行动、外部现金流、特殊结算和 fractional entitlement 命中；
- 每个缺口对应的候选 ID，不只保存计数。

支持矩阵必须精确绑定运行代码和 approved Stage 5D profile。当前受限 5D-1 不满足正式 6C 运行门。任何扩展必须先完成独立 Stage 5D 版本、验收和新的 6C 预注册；禁止在看见表现后就地补实现并只重跑失败样本。

确认性 coverage 门：

- 全部已登记候选中可形成完整、无 partial NAV/P&L 的比例 `>= 80%`；
- 每个 walk-forward 年份 coverage `>= 70%`；
- 低于任一门时整轮只能 `INSUFFICIENT_EVIDENCE`。

## 7. 样本充分性

- 全部 walk-forward 合计至少 `30` 个相互独立、真实可成交、已结束且完整对账的交易；
- 每个 evaluation fold 至少 `5` 个独立已结束交易，否则整轮 `INSUFFICIENT_EVIDENCE`；
- 任一行业、公司类型或风险簇子组少于 `15` 个时只作描述，不下子组统计结论；
- `ABSTAIN/BLOCKED/无成交` 保留在 coverage 分母，不计作零收益或已结束交易。

样本不足后的合法顺序仍是：修复非选择性数据覆盖 → 扩展更早年份/通用来源 → 形成新机制相邻产业提案 → owner 重新批准。禁止放宽独立性或复制样本。

## 8. 冠军挑战 closed world

首版竞争模型固定为：

1. `no_trade`；
2. `market_or_industry_matched`；
3. `simple_e4_only`；
4. `simple_valuation_threshold`；
5. `full_system`。

`H0_no_independent_alpha` 是统计零假设，不是第六个可交易模型。所有模型共享候选总体、PIT 截面、60-session horizon、可成交约束、费用/税/滑点/冲击、容量、风险预算和组合时钟。

各模型的差异 closed world：

- `no_trade`：全期现金，不生成风险资产目标；
- `market_or_industry_matched`：对每个候选在 decision time 使用 PIT 一级行业、流通市值五分位与过去 120 个合法交易日 Beta 五分位匹配；排除目标公司，至少 5 个 peer，按等风险预算组合。同行业 peer 不足 5 个时依次回退到同市值/Beta bucket、再回退到全 A 股同市值 bucket，回退层级必须记录；
- `simple_e4_only`：只要求 approved E4 public，使用统一风险预算、首次可成交和 60-session 固定退出，不使用利润桥、市场预期或估值门；
- `simple_valuation_threshold`：要求 approved E4 public 与进入本轮前已批准的唯一估值/赔率门，其他条件与 simple E4 相同；
- `full_system`：使用进入本轮前已批准的完整 E0—E7、四道门、利润桥、估值、执行和风险链。

`best_simple` 只能在 2019—2021 development 期间从前三个非 full 风险模型中按主估计量选择一次，并在任何 walk-forward summary 可见前内容寻址冻结。净结果并列时按 `market_or_industry_matched → simple_e4_only → simple_valuation_threshold` 的低复杂度顺序裁决；四个 walk-forward folds 共用同一 frozen best-simple identity，禁止逐 fold 或事后重选。

`full_system` 使用进入本轮前已经 approved 的唯一规则与配置，不在 6C 中搜索 E0—E7、Gate、利润桥、估值、退出或风险阈值。任何新业务参数只能形成新规则版本与新预注册，不能作为本轮 champion。

## 9. 执行流水线与 golden 门

正式批量执行前必须通过：

1. Stage 2B/4/5 的既有 golden 与 replay 回归；
2. Stage 5D 当前支持 profile 的 exact golden；
3. PIT 未来字段、修订回填、withdrawal、重复候选、不可成交、成本和 mark 缺失负例；
4. 候选输入乱序不改变规范结果，任何承重字节变化必须改变 replay identity；
5. 同一正式 seal、预注册、代码、配置和随机种子重复执行得到相同候选、journal、NAV/P&L 和汇总 hash。

golden 失败时不得读取组合表现或继续下一 fold。

## 10. 指标与精确通过线

### 10.1 主估计量

主估计量为 60-session 组合每日 NAV 形成的、扣除费用/税/滑点/冲击后的年化 time-weighted return，减去同风险预算的 `market_or_industry_matched` 年化结果，单位为 percentage points。每日无持仓时仍保留现金，不删除日期。

完整系统与最佳简单模型的比较使用同一指标。`best_simple` 严格按第 8 节 development-only 规则选择和冻结；`no_trade` 仍单独报告。

### 10.2 必报指标

必须同时报告：绝对/基准超额收益、逐机会 contribution、coverage、`ABSTAIN/BLOCKED`、成交率、容量、最大回撤、Expected Shortfall 95%、最大赢家贡献、公司/风险簇/时期集中、换手、成本、现金占比和 exposure。风险过滤、发现、估值、执行与成本贡献分别披露，不得合并称为 Alpha。

### 10.3 进入 6D 的全部门槛

只有以下条件同时满足，6C phase outcome 才能是 `READY_FOR_6D_FREEZE`：

- 第 6、7 节 coverage 与样本门全部通过；
- full system 年化净基准超额 `> 0`，主聚类重采样双侧 `95%` CI 下限 `> 0`；
- full system 相对 `best_simple` 的年化净增量 `>= 2.0` percentage points，且对应 `95%` CI 下限 `> 0`；
- 四个 walk-forward fold 中至少 `3` 个净基准超额 `> 0`，且最差 fold 不低于 `-10.0` percentage points；
- walk-forward 最大回撤 `<= 15%`；
- 最大单笔盈利占总净利润 `<= 25%`；总净利润非正时该门直接失败，不能用零分母跳过；
- `1.5×` 全交易摩擦压力下净基准超额 `>= 0`；
- 没有 P0 偏差或 reconciliation failure。

等号语义按上文明确执行；不得用四舍五入后的显示值判门。

## 11. 不确定性与多重检验

- 重采样次数：`10,000`；随机种子：`20260820`；算法与库版本进入 Manifest。
- 主重采样 block：`calendar_quarter × risk_cluster_id`，block 内所有 event/company observation 整体移动；另做 company-cluster 敏感性。
- 置信区间使用预注册的 percentile bootstrap；若有效 block 少于 `30`，只允许 `INSUFFICIENT_EVIDENCE`。
- 确认性 family 是 full system 分别对 `no_trade`、`market_or_industry_matched`、`simple_e4_only`、`simple_valuation_threshold` 的四个主比较，以及 full-vs-best-simple 实质增量，共 `5` 项。
- family-wise `alpha=0.05`，按 Holm-Bonferroni 调整；未登记指标、horizon、子组或模型一律标记 `exploratory`。

## 12. 消融、邻域与压力

消融只用于归因和证伪，不参与 champion 搜索。至少分别移除：事件层、产业/公司映射、Gate、利润桥、估值、退出、组合风险和执行约束。

压力 closed world：

- 交易摩擦：`1.0× / 1.5× / 2.0×`；
- 信息/处理延迟：`+0 / +1 / +2` 个交易日；
- 容量：起始 NAV `100,000 CNY` 主场景、`300,000 CNY` 压力场景；
- 可成交性：跳空、停牌、涨跌停、无对手盘和容量减半；
- mark：合法 observation 缺失、陈旧和同刻冲突。

除第 10.3 节明确的 `1.5×` 门外，其余压力用于稳健性与失败归因；不得事后挑选最有利场景。

## 13. 搜索台账、留存与 replay

6C 禁止未登记参数搜索。任何探索性变体必须在运行前获得唯一 `experiment_id`，登记假设、变更字段、搜索空间、启动时间和 parent preregistration；探索结果不能进入当前 6D champion。

每个 fold 原子封存：正式 admission seal ref、预注册、候选全集、支持矩阵、golden receipt、模型输入/输出、逐机会 contribution、journal/NAV/P&L、搜索台账、压力/消融、统计结果、失败和 run Manifest。失败 run append-only 保留，不能由成功重试覆盖。

6C replay identity 至少覆盖：正式 admission seal hash、preregistration hash、候选 inventory hash、支持矩阵 hash、规则/代码/config/runtime lock、日历/benchmark/market-rule identities、模型 ID、fold、随机种子和全部规范输出。网络获取时间与动态响应 meta 只进 observation，不进确定性结果。

## 14. 状态与 6D 移交

6C phase outcome closed world：

- `READY_FOR_6D_FREEZE`：全部 6C 完成门通过，只允许冻结 champion 与 6D 请求；
- `REVISE_NEW_PREREGISTRATION`：明确失败，需要新规则/数据/支持矩阵版本，旧 holdout 资格失效；
- `INSUFFICIENT_EVIDENCE`：coverage、样本、PIT 或统计 block 不足；
- `PRECHECK_BLOCKED`：身份、正式 seal、权限、Schema、golden 或 reconciliation 失败；
- `AUDIT_REPLAY_ONLY`：只重放历史封存，不产生新 champion。

这些是 phase outcome，不是 Stage 6 最终 `PASS`。6D 只接收一个内容寻址 champion、完整 6C seal 集和仍未打开的 holdout identity。任何 6C 后变更都使旧 6D 请求无效。

## 15. 实施与验收边界

批准本包后，第一实现步仍只能是匿名合成 fixture 下的纯 candidate/fold/statistics/replay kernel，并验证零 I/O、零 runtime authority。正式 historical development/walk-forward 执行必须另有 owner 授权，且第 3 节所有前置门真实存在。

禁止为了进入 6D：

- 把 6B validation-only seal 升格为正式 run seal；
- 把当前 Context Pack 快照回填为历史时点视图；
- 把 unsupported/ABSTAIN/BLOCKED 从 coverage 分母删除；
- 把单一 5D-1 bounded case 外推成 30 笔完整交易；
- 打开或探测 holdout 结果；
- 修改 KB 或把策略逻辑写回 KB。

## 16. Owner 逐项批准清单

- [ ] `6C-01`：批准 6C 只负责 development/walk-forward 与 champion freeze，不打开 6D holdout，不产生 Stage 6 最终 PASS 或任何交易权限。
- [ ] `6C-02`：批准拟议 scope 为 `stage6_development_walk_forward_validation`；当前 draft 零 capability，批准后先只允许匿名合成 runner/statistics kernel 验收。
- [ ] `6C-03`：批准精确绑定 PLAN/PRD、6A/6B 批准谱系与验收、Stage 5D bounded replay 身份及固定 KB transport snapshot。
- [ ] `6C-04`：批准正式 6C 必须消费正式状态层重读复核的 exact HistoricalRunAdmissionSeal，禁止复用 6B validation-only seal。
- [ ] `6C-05`：批准总体、development、2022—2025 四个 walk-forward folds 与 2026 frozen holdout 的第 4 节精确日期。
- [ ] `6C-06`：批准 `Asia/Shanghai` 交易日历、UTC canonical instant 和左闭右开区间语义。
- [ ] `6C-07`：批准研究单位、候选先登记及经济事件/公司/时间风险簇独立性规则。
- [ ] `6C-08`：批准所有候选、REJECT、ABSTAIN、BLOCKED、退市和无成交进入全集，禁止成功样本先筛选。
- [ ] `6C-09`：批准事实、修订、价格、规则、benchmark 与状态必须满足 effective/available/decision/knowledge-cutoff PIT 关系，当前快照不得回填历史。
- [ ] `6C-10`：批准主 horizon 为 60 个交易日，20/120 日仅作非确认性稳健性，提前 approved exit 按真实时点结束。
- [ ] `6C-11`：批准训练 label 必须完整结束、最长 120-session purge 与 20-session embargo，caller 不得自选训练 ID。
- [ ] `6C-12`：批准 6C 只固定 2026 holdout identity/hash，不读取结果、计数、summary 或任何可推断表现的信息。
- [ ] `6C-13`：批准任何收益读取前必须完成内容寻址 HistoricalDataReadinessReport 与逐候选缺口清单。
- [ ] `6C-14`：批准 Stage 5D 支持矩阵绑定精确实现；当前受限 5D-1 不满足正式 6C，扩展后必须新预注册。
- [ ] `6C-15`：批准 unsupported 输入保留为 ABSTAIN/BLOCKED，禁止 partial NAV/P&L、静默剔除、零收益替代或事后择样重跑。
- [ ] `6C-16`：批准总体 coverage `>=80%`、每个 walk-forward 年份 `>=70%`，低于任一门只能 INSUFFICIENT_EVIDENCE。
- [ ] `6C-17`：批准至少 30 个独立已结束交易、每 fold 至少 5 个；子组少于 15 只作描述。
- [ ] `6C-18`：批准第 8 节 no-trade、精确 PIT peer-matched、simple E4、simple valuation 与 full system 模型语义 closed world，并仅在 2019—2021 development 选择和冻结一次 best-simple。
- [ ] `6C-19`：批准所有模型共享候选、PIT、horizon、执行、成本、容量、风险预算和组合时钟。
- [ ] `6C-20`：批准 full system 只用进入本轮前 approved 的唯一配置，6C 不搜索业务规则阈值；新参数必须新版本/新预注册。
- [ ] `6C-21`：批准主估计量为 60-session 每日 NAV 的扣费后年化 time-weighted 基准超额，现金日期不得删除。
- [ ] `6C-22`：批准第 10.2 节收益、coverage、失败、成交、容量、风险、集中、换手、成本和 exposure 必报指标。
- [ ] `6C-23`：批准 full system 年化净基准超额及其 95% 聚类 CI 下限均严格大于 0。
- [ ] `6C-24`：批准 full-vs-best-simple 年化净增量至少 2.0 percentage points 且 95% CI 下限严格大于 0。
- [ ] `6C-25`：批准 walk-forward 最大回撤 `<=15%`、最大赢家贡献 `<=25%`，总净利润非正不得绕过赢家门。
- [ ] `6C-26`：批准至少 3/4 folds 净超额为正、最差 fold 不低于 -10 percentage points。
- [ ] `6C-27`：批准 10,000 次、seed 20260820、quarter×risk-cluster block bootstrap，并要求 company-cluster sensitivity。
- [ ] `6C-28`：批准五项确认性 family、family-wise alpha 0.05 与 Holm-Bonferroni 调整，未登记结果只能 exploratory。
- [ ] `6C-29`：批准未登记参数搜索禁止；所有 experiment 预先登记且探索结果不能进入当前 6D champion。
- [ ] `6C-30`：批准正式批量前必须通过既有 golden、PIT/withdrawal/不可成交/mark 负例和确定性 replay 门。
- [ ] `6C-31`：批准八类消融只作归因和证伪，不参与 champion 选择。
- [ ] `6C-32`：批准摩擦、延迟、容量、不可成交与 mark 压力 closed world，并要求 1.5× 摩擦下净基准超额非负。
- [ ] `6C-33`：批准起始 NAV 100,000 CNY 主场景和 300,000 CNY 容量压力，不因此改变风险比例。
- [ ] `6C-34`：批准幸存者、前视、重复事件、选择性纳入、不可成交和研究者自由度审计为 P0 完成门。
- [ ] `6C-35`：批准每 fold 原子封存第 13 节完整输入、逐机会、账本、统计、压力、失败和搜索制品，失败不得覆盖。
- [ ] `6C-36`：批准 replay identity 精确覆盖 seal/prereg/candidates/support/rules/code/config/data/model/fold/seed/outputs，动态获取 meta 仅作观察。
- [ ] `6C-37`：批准 6C phase outcome closed world 及 READY_FOR_6D_FREEZE 只代表 6D 进入资格，不是策略有效或运行授权。
- [ ] `6C-38`：批准本包即使获批也只先授权匿名合成 kernel 实现；正式 development/walk-forward 必须另经 owner 执行授权。
- [ ] `6C-39`：批准 6D 只接收一个冻结 champion、完整 6C seal 集和未打开 holdout；任何后续承重变化使请求失效。
- [ ] `6C-40`：批准 40 项必须整包原子批准；部分、pending、拒绝、identity drift 或缺验收均保持零 6C runtime authority。

## 17. 批准后的唯一实施顺序

1. 保持本 specification 与 draft machine proposal 原始字节不变；
2. owner 审阅并原子批准或调整第 16 节 40 项；
3. 形成独立 approved bundle、approval record 和治理验收；
4. 只实现匿名合成 candidate/fold/statistics/replay kernel，完成 golden/failure matrix；
5. 另行关闭正式 admission migration、PIT data readiness 与 Stage 5D 支持矩阵；
6. owner 独立授权正式 6C development/walk-forward run；
7. 6C 完整封存且 outcome 为 `READY_FOR_6D_FREEZE` 后，才形成 6D holdout-open 请求。

任一前置身份、coverage、样本、PIT、会计支持或统计门失败都必须停止。不得为推进阶段而缩短主 horizon、删除失败样本、打开 holdout 或扩大权限。
