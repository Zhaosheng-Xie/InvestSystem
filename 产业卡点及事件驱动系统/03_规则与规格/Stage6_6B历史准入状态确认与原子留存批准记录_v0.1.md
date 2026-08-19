# Stage 6 / 6B 历史准入、状态确认与原子留存批准记录 v0.1

批准状态：`approved`

批准时间：`2026-08-19T14:13:39.583064Z`

批准人：`repository_owner`

批准来源：当前 Codex task 中 owner 回复“看看精确规则包有什么很大的风险，如果没有那么批准继续”；经复核，本包只开放隔离、validation-only 的 6B admission 实现与验收，不开放正式历史 run、策略 evaluator、正式状态库迁移、6C/6D 或交易权限，因此按第 14 节全部 32 项整包原子批准。

批准范围：`stage6_historical_admission_validation`

## 1. 批准对象

owner 原子批准[《Stage 6 / 6B 历史准入、状态确认与原子留存精确规则包 v0.1》](Stage6_6B历史准入状态确认与原子留存精确规则包_v0.1.md)第 14 节全部 32 项。

精确批准来源：

- specification raw SHA-256：`96ec47da0eb356f726db3ce1be8015366ad3a804cc3f93d63c5b1c3fc65e3f5a`；
- draft machine proposal raw SHA-256：`4a5ed454e6ab152e03dc83b9723f035eacd020ff4bfe16d742427b4aaff827e4`；
- draft canonical bundle SHA-256：`0ef8808f8de5e44991bbdecb5bb6a63f1b408d0650fd395c958af454adb262d4`；
- draft canonical rules SHA-256：`4cd66370471d22169f1308ad4cc9f16852b5b6ebe1f20832ca3de6e30598a73b`；
- 32 项 draft owner items canonical SHA-256：`17d1d3dabb4d68e8917ce008f6494d644c006c7a4d57f27a81a2e89260a2a3d8`。

原 specification 与 draft machine proposal 保持原始字节不变。批准通过独立 approved bundle、approval record 和 fail-closed verifier 表达，不回写原 draft。

## 2. 风险判断

本包没有阻断批准的重大风险。四项主要风险均被限制为 validation failure，而不是错误 authority：

- 固定公网 origin 会增加 endpoint 变更时的换版成本，但禁止静默覆盖，变化必须产生新 profile/hash；
- `300s / 30s / 300s` 的新鲜度参数可能使慢 admission 失败，但等号通过、超界失败关闭，不会接受陈旧状态；
- SQLite 事务外准备 CAS 可能留下未引用 orphan，但 orphan 不构成 run/pin/confirmation/seal，evaluator 不可读取；
- 6B 正式 migration 版本仍未决定，但规则禁止复用 Stage 5D SQLite v4，并把所有获批后的写入限制在隔离临时库。

完整 closure confirmation、seal-last 原子提交、撤回后 audit-only、失败零权威写入和零 evaluator 调用共同阻断了错误历史准入。批准仍不等于 6B 实现完成或正式 historical authority。

## 3. 三十二项原子批准确认

- [x] `6B-01`：批准 6B 只负责 historical admission、状态确认、原子留存和 seal，不执行策略 evaluator、development、walk-forward 或 holdout。
- [x] `6B-02`：批准拟议 scope 为 `stage6_historical_admission_validation`；当前 draft 零 capability，获批后也只允许隔离 validation-only 验收。
- [x] `6B-03`：批准精确绑定 Stage 6A 批准谱系、`59e1edd` 基线、IS 自有消费/留存/Manifest/confirmation 合同和 `aab36fe` transport snapshot。
- [x] `6B-04`：批准只经 KB 公共只读 HTTPS/不可变导出消费内容，当前状态 authority 必须另经真实在线 HTTPS 获取，禁止 KB 内部读取和 KB 写入。
- [x] `6B-05`：批准 `HistoricalAdmissionRequest` 内容寻址，并要求一个且仅一个五字段 `strategy_input_ref`、精确规则/代码/配置/预注册/transport/authority 身份。
- [x] `6B-06`：批准 validation preregistration fixture 必须显式非历史证据；正式预注册缺失或含未决字段时不得签发正式 seal。
- [x] `6B-07`：批准 Receipt 根与 Retention Closure 分层，闭包精确覆盖所有传递 Release、Manifest、依赖和 artifact，禁止 caller 少报或多报。
- [x] `6B-08`：批准 closure source Release 不是第二个策略输入，首版 run 仍只有一个对外 `strategy_input_ref`。
- [x] `6B-09`：批准 authority ID、endpoint、path、transport lock、TLS、redirect 和 credential 边界按第 6 节精确冻结，任一变化形成新 profile/hash。
- [x] `6B-10`：批准 provider snapshot 最大年龄 `300` 秒、最大时钟偏差 `30` 秒、confirmation TTL `300` 秒，边界按含等号通过、超出失败关闭。
- [x] `6B-11`：批准短期只读凭据只在进程内使用，Token/Authorization header 不得进入 canonical bytes、日志、状态库、缓存或 Git。
- [x] `6B-12`：批准每个 closure Release 获取完整 status history 原始响应和 response SHA，事件链必须连续、自哈希闭合且 current head 为 published。
- [x] `6B-13`：批准状态 recorded/snapshot/checked/confirmed/expires 的 PIT 关系和 transaction 前新 head 失效规则。
- [x] `6B-14`：批准原始状态 response bytes 进入 IS CAS，动态 meta 只作观察证据，不进入 Release/Manifest 语义哈希。
- [x] `6B-15`：批准 RunReleaseStatusConfirmation 精确绑定 run、receipt、closure、authority、时间窗和完整排序 items，并由受信 issuer 从实际 response 构造。
- [x] `6B-16`：批准禁止复用 Stage 3 validation-only、旧 run、另一个 run、Stage 7 或调用方自报的 confirmation。
- [x] `6B-17`：批准 HistoricalRunAdmissionEnvelope 同时绑定 request/preregistration、Receipt、Closure、Observations、Manifest、confirmation、pin 集合和事务 profile。
- [x] `6B-18`：批准 HistoricalRunAdmissionSeal 是唯一 admission 完成标志；后续 evaluator 只能消费从状态库重读并复核的 exact seal。
- [x] `6B-19`：批准网络与候选 CAS 准备在事务外完成，数据库写事务内禁止网络 I/O。
- [x] `6B-20`：批准未被 seal 引用的 CAS orphan 不是权威 run 状态，不可被 evaluator 读取；历史已引用制品不得自动删除。
- [x] `6B-21`：批准第 10 节十类对象在单一 `BEGIN IMMEDIATE` 中原子链接/写入，并最后写 seal。
- [x] `6B-22`：批准任何 admission 失败权威状态零写、seal 不存在且 evaluator 调用为零，不允许 partial pin、partial Manifest 或 partial confirmation。
- [x] `6B-23`：批准同 run 同字节幂等、同键异字节冲突，失败 run 不得被成功重试覆盖。
- [x] `6B-24`：批准并发只有一个 generation 成功，heads 变化后必须重新构造全部 admission，不能只重试 SQL。
- [x] `6B-25`：批准 WAL/IOERR/FULL/BUSY/崩溃恢复只能观察完整 seal 或无 seal，并阻断 REPLACE、UPDATE/DELETE、head 回拨和 child 注入。
- [x] `6B-26`：批准 SQLite v2 quarantine 永久 audit-only，任何补写不得恢复新 run。
- [x] `6B-27`：批准不得占用 Stage 5D 已预留的 SQLite v4 语义；6B 正式迁移版本/表前缀须另行明确批准，未决前只使用临时验证库。
- [x] `6B-28`：批准任一 closure Release 撤回或不可确认阻断新 seal，历史 seal 不改写且只允许严格 audit replay。
- [x] `6B-29`：批准普通读取和 audit replay 均重验 canonical parent、child indexes、CAS 与完整 pin closure，SQLite 投影不能冒充权威字节。
- [x] `6B-30`：批准第 13 节七种 admission 状态 closed world 和最低失败注入矩阵，不得用异常吞掉、默认 PASS 或静默降级。
- [x] `6B-31`：批准 6B 验收只在独立临时 IS state/cache 中进行，所有 output 保持 validation-only、authority_eligible=false，正式 state DB 与 KB 零修改。
- [x] `6B-32`：批准 32 项必须整包原子批准；部分、pending、拒绝、identity drift 或缺验收均保持零 runtime authority，6C/6D 继续未授权。

## 4. 批准后的权限结论

本批准允许形成精确 6B approved bundle、approval record 和独立 validation capability，并据此实现、测试 admission contracts/issuer/adapter 与隔离临时库中的 validation-only confirmation/seal。

本批准明确不授权：

- 正式 historical run 或策略 evaluator 调用；
- development、walk-forward 或 frozen holdout；
- 正式状态库 migration 或 Stage 5D SQLite v4 复用；
- backtest、paper、shadow、live；
- 真实账户、仓位、订单、broker 或资金部署；
- 读取或写入 KB 内部状态；
- 复用 Stage 3、Stage 5、Stage 6A 或 Stage 7 capability 作为 6B capability。

下一步只能先形成批准谱系和 fail-closed 6B capability，再实现纯 contracts/issuer/adapter 与隔离临时库原子 seal。完成 failure matrix 和一次真实 HTTPS validation-only seal 验收前，不得进入正式 migration 决策或 6C。
