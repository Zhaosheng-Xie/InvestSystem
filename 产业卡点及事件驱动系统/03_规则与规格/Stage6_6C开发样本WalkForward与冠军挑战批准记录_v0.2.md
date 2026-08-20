# Stage 6 / 6C 开发样本、Walk-Forward 与冠军挑战批准记录 v0.2

批准状态：`approved`

批准时间：`2026-08-20T13:13:12.270950Z`

批准人：`repository_owner`

批准来源：当前 Codex task 中 owner 指令“先形成 v0.2，集中关闭上述 5 点，再重新统一批准。”v0.2 已关闭 holdout 技术隔离、统计进入门、portfolio/bootstrap、coverage selection bias 和 TWR/benchmark 五项重大方法风险，因而按第 6 节全部 40 项整包原子批准。

批准范围：`stage6_development_walk_forward_validation`

## 1. 批准对象

owner 原子批准[《Stage 6 / 6C 开发样本、Walk-Forward 与冠军挑战精确规则包 v0.2》](Stage6_6C开发样本WalkForward与冠军挑战精确规则包_v0.2.md)第 6 节全部 40 项。

精确批准来源：

- v0.2 specification raw SHA-256：`3886580f1785d4545b02d76ca81ce449577ba406cf1d829efb8b5d4f4e55d368`；
- v0.2 draft machine raw SHA-256：`6f2663feb8b8cef5fd969d2791d2505b82e31ff42071872df0350c2196007afd`；
- v0.2 draft canonical bundle SHA-256：`a45396cde1e23ab6c05ea03111cf9f72044031a57d6a91dce554e15d6979a72c`；
- v0.2 draft canonical rules SHA-256：`c64f2b6057355c5e0bca9d597c01ed9f39ae0fd483ee469de86f7c964d8879c8`；
- v0.2 40 项 owner items canonical SHA-256：`7e3eee1c02a8d16e27ec3180379d221302ff3ca1741bb43300f145063f910bd6`；
- v0.2 草案形成提交：`4ab2817451cd6d08ecfdb2d09a58a676e65876fe`。

v0.1 specification、v0.1 draft、v0.2 specification 与 v0.2 draft 均保持原始字节不变。批准通过独立、完整物化的 approved bundle、approval record 和 fail-closed verifier 表达；runtime 不得动态合并 delta 或解析 Markdown。

## 2. 风险判断

v0.2 没有阻断治理批准的重大风险：

- holdout 从逻辑承诺提升为 development projection、opaque commitment、独立 custodian/ACL/credential、拒绝 canary 和零读取审计；
- raw CI、company/risk sensitivity 与 Holm adjusted family 形成同一个进入 6D 的门；
- 唯一 portfolio 事实来自 source-driven 全链重放，主时间 bootstrap 与逐机会 cluster sensitivity 分层且均可重放；
- coverage 除数量门外增加 outcome-blind selection audit，并明确不能证明未观测缺失机制不存在；
- 主 TWR/benchmark、252-session 年化、最短 fold、外部现金流和 benchmark 成本/支持语义已经唯一化。

保留的风险均被转化为失败关闭或证据限制：当前 5D-1 不足、正式 admission seal 不存在、PIT data readiness 未完成或 holdout 隔离未部署时，都不得开始正式 6C。2026 只能称为 locked historical holdout，不能替代 Stage 7 真正未知样本。

## 3. 四十项原子批准确认

- [x] `6C-01`：批准 6C 只负责 development/walk-forward 与 champion freeze，不打开 6D holdout，不产生 Stage 6 最终 PASS 或任何交易权限。
- [x] `6C-02`：批准 scope 为 `stage6_development_walk_forward_validation`；当前 draft 零 capability，批准后第一步仍只允许匿名合成 kernel 验收。
- [x] `6C-03`：批准精确绑定 PLAN/PRD、6A/6B、Stage 5D、v0.1 specification/draft 和固定 KB transport identities。
- [x] `6C-04`：批准正式 6C 必须消费正式状态层重读复核的 exact HistoricalRunAdmissionSeal，禁止复用 6B validation-only seal。
- [x] `6C-05`：批准 v0.1 时间切分，并以根 knowledge cutoff 作为 inclusive instant 上界。
- [x] `6C-06`：批准 `Asia/Shanghai` calendar、UTC canonical instant 和左闭右开区间语义。
- [x] `6C-07`：批准研究单位、候选先登记及经济事件/公司/时间风险簇独立性规则。
- [x] `6C-08`：批准所有候选、REJECT、ABSTAIN、BLOCKED、退市和无成交进入全集，禁止成功样本先筛选。
- [x] `6C-09`：批准 effective/available/decision/knowledge-cutoff PIT 关系，当前快照不得回填历史。
- [x] `6C-10`：批准主 horizon 60 sessions，20/120 sessions 只作非确认性稳健性。
- [x] `6C-11`：批准 label 完整结束、120-session purge、20-session embargo，caller 不得自选训练 ID。
- [x] `6C-12`：批准以第 1 节 development projection、opaque commitment、独立 ACL/凭据、canary 和零读取审计技术隔离 holdout；2026 只称 locked historical holdout。
- [x] `6C-13`：批准任何表现读取前完成 content-addressed HistoricalDataReadinessReport 和逐候选缺口清单。
- [x] `6C-14`：批准 Stage 5D 支持矩阵绑定精确实现；当前受限 5D-1 不满足正式 6C。
- [x] `6C-15`：批准 unsupported 保留为 ABSTAIN/BLOCKED，禁止 partial NAV/P&L、静默剔除、零收益替代或择样重跑。
- [x] `6C-16`：批准总/年度 coverage 数量门与第 4 节 outcome-blind SMD、比例差、material-category coverage 选择偏差门必须同时通过。
- [x] `6C-17`：批准至少 30 个独立已结束交易、每 fold 至少 5 个；子组少于 15 只作描述。
- [x] `6C-18`：批准 v0.1 五模型 exact semantics 和仅用 development 冻结一次 best-simple。
- [x] `6C-19`：批准所有模型共享候选、PIT、horizon、执行、成本、容量、风险预算和组合时钟。
- [x] `6C-20`：批准 full system 只用本轮前 approved 唯一配置，6C 不搜索业务阈值。
- [x] `6C-21`：批准第 5 节零外部现金流、每日 excess factor、252-session annualization、最短 126 sessions 和 exact benchmark NAV 公式替换 v0.1 概括定义。
- [x] `6C-22`：批准 v0.1 收益、coverage、失败、成交、容量、风险、集中、换手、成本和 exposure 必报指标。
- [x] `6C-23`：批准 full-vs-benchmark 主 calendar-block、company-cluster 与 risk-cluster 三条 95% CI lower 均严格大于 0。
- [x] `6C-24`：批准 full-vs-frozen-best-simple 年化净增量至少 2.0 percentage points，且三条推断路径 95% CI lower 均严格大于 0。
- [x] `6C-25`：批准最大回撤 `<=15%`、最大赢家贡献 `<=25%`，总净利润非正不得绕过赢家门。
- [x] `6C-26`：批准至少 3/4 folds 净超额为正、最差 fold不低于 -10 percentage points。
- [x] `6C-27`：批准第 3 节 calendar-quarter daily-return bootstrap 与 company/risk Rademacher cluster wild bootstrap、三组固定 seed 和各 10,000 次。
- [x] `6C-28`：批准五项 family 的 Holm-Bonferroni adjusted p-value 全部 `<=0.05`，并保存完整 raw/adjusted inference trail。
- [x] `6C-29`：批准未登记参数搜索禁止；exploratory 结果不能进入当前 champion。
- [x] `6C-30`：批准正式批量前必须通过既有 golden、PIT/withdrawal/不可成交/mark 负例和确定性 replay 门。
- [x] `6C-31`：批准八类消融只作归因和证伪，不参与 champion 选择。
- [x] `6C-32`：批准摩擦、延迟、容量、不可成交与 mark 压力 closed world，并要求 1.5× 摩擦下净基准超额非负。
- [x] `6C-33`：批准 100,000 CNY 主场景和 300,000 CNY 容量压力，不改变风险比例。
- [x] `6C-34`：批准幸存者、前视、重复事件、选择性纳入、不可成交和研究者自由度审计为 P0 门。
- [x] `6C-35`：批准每 fold 原子封存完整输入、逐机会、账本、统计、压力、失败和搜索制品，失败不得覆盖。
- [x] `6C-36`：批准 replay identity 覆盖 seal/prereg/candidates/support/rules/code/config/data/model/fold/seed/outputs，动态获取 meta 只作观察。
- [x] `6C-37`：批准 phase outcome closed world，READY_FOR_6D_FREEZE 只代表 6D 进入资格。
- [x] `6C-38`：批准即使规则获批也只先授权匿名合成 kernel；正式 development/walk-forward 仍须 owner 独立授权。
- [x] `6C-39`：批准 6D 只以独立 capability 解封一个 frozen champion、完整 6C seals 和第 1 节 opaque holdout commitment；任何提前访问或身份变化使请求失效。
- [x] `6C-40`：批准 v0.2 全部 40 项必须整包原子批准；部分、pending、拒绝、identity drift 或缺验收均保持零 runtime authority。

## 4. 批准后的权限结论

本批准允许形成精确 Stage 6C v0.2 approved bundle、approval record 和独立 capability verifier，并据此实现、测试匿名合成的 holdout-isolation/candidate/fold/statistics/replay kernel。

本批准明确不授权：

- 正式 historical admission、development 或 walk-forward run；
- 读取、解密或打开 holdout artifact；
- Stage 6 最终 PASS、6D 或 Stage 7；
- 正式状态库 migration；
- backtest、paper、shadow、live；
- 真实账户、仓位、订单、broker 或资金部署；
- KB 内部读取或 KB 写入。

下一步只能先完成批准谱系和 fail-closed capability，再形成匿名合成 kernel 的精确实现切片。正式执行必须另行获得 owner 授权并真实关闭 admission、PIT readiness、Stage 5D support 和 holdout custody 前置门。
