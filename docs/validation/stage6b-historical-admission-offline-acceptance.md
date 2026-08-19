# Stage 6B 历史准入离线实现验收记录

日期：`2026-08-19`

分支：`codex/stage6-historical-validation`

结论：`offline_implementation_accepted / real_https_validation_seal_pending`

## 1. 验收范围

本记录只验收 Stage 6B 已批准范围内的离线实现和隔离临时库 failure matrix。它不把固定 transport fixture 冒充当前状态 authority，也不表示 6B 已完成独立真实公网验收。

已验收实现提交：

- `9fc9f70`：Stage 6B admission contracts、受信 status evidence issuer、validation-only confirmation 与 envelope；
- `559d7f9`：独立 validation state/cache、内容寻址缓存、单一 `BEGIN IMMEDIATE` 权威事务和 seal-last 提交；
- `93295c0`：固定公网 profile 的只读 HTTP status adapter；
- `ddc1120`：恢复策略、provider adapter 和应用编排的单向架构边界；
- `10e45f6`：用不可覆盖的原子 CAS 发布关闭 Windows 同哈希并发竞态。

## 2. 已形成的能力

- 一个且仅一个对外 `strategy_input_ref`，同时固定 Receipt 根和全部传递 source Release 的 Retention Closure；
- 从固定 `aab36fe229104779b50ec71e2dc37a9fad81d285` transport snapshot 的完整 status response 字节重新验证连续事件链、自哈希和 `published` head；
- 固定 `https://82.157.112.120`、精确 status path、`300s / 30s / 300s` 新鲜度与 TTL；
- 从实际已验证 response bytes 构造 opaque status evidence、`ReleaseStatusObservation`、validation-only confirmation、Manifest 和 admission envelope；
- 所有网络读取在 SQLite 写事务前完成；事务内不访问网络；
- 在独立临时根目录中保存规范 parent、child indexes、完整 CAS/pin closure、generation 和最后写入的 seal；
- 同 run 同字节幂等、同键异字节冲突、完整闭包少报/多报拒绝、每个原子步骤失败零权威写入；
- 读取时重新验证 canonical parent、child indexes、CAS、pin closure 和 seal；
- Windows 并发 CAS 采用原子 create-if-absent，同哈希同字节成功复用，异字节仍失败关闭；
- `strategy_evaluator_calls=0`、`authority_eligible=false`，不签发正式历史运行 authority。

策略目录只保留 provider-neutral contracts 和 validation store；KB response 解析位于 `integrations/investment_research_kb`，HTTP 获取与封存编排位于根级应用模块。策略层不导入 provider integration 或正式 storage 层。

## 3. 离线失败矩阵与质量门

- Stage 6B、KB HTTP Client 与架构相邻专项：`58 passed`；
- Windows CAS 并发用例连续执行十次：`10 / 10 passed`；
- 全仓 pytest：`1014 passed, 4 skipped`；
- Ruff check：通过；
- Ruff format check：通过；
- mypy：`123 source files` 通过；
- compileall：通过；
- `git diff --check`：通过。

四个 skip 均为当前 Windows 账户没有 symlink privilege 的既有平台 skip，不是 Stage 6B 失败。

## 4. 权限与存储边界

- 当前实现只允许使用独立临时 IS state/cache；没有修改 `var/state/invest_system.sqlite3`，也没有决定正式 migration 版本；
- 未复用 Stage 5D SQLite v4，没有改写 Stage 2A/Stage 3/Stage 5 历史制品；
- 没有读取 KB SQLite、`raw`、`staging`、`published`、源码、工作树或临时内部材料；
- 没有 KB 写入、策略 evaluator、正式 historical run、development、walk-forward、holdout、backtest、paper、shadow、live、仓位或订单能力。

## 5. 尚未完成的 6B 独立验收

规则要求在离线 failure matrix 之后，使用新的短期只读凭据完成一次真实公网 validation-only seal。当前旧 Stage 3 Token 已撤销，仓库中也没有可复用凭据，因此以下证据仍缺失：

1. 同一次 admission 窗口内，经真实公网 HTTPS 获取根 Release 与全部 source Release 的完整当前 status history；
2. 用精确真实 Release/Manifest/artifact 字节重建 Receipt、Retention Closure、Manifest 和 status payload；
3. 在新的独立临时 state/cache 中签发并重读 `authority_eligible=false` 的 validation-only confirmation/seal；
4. 记录实际 response SHA-256、status head、knowledge cutoff、confirmation/seal hash 和临时根已清理/隔离的证据；
5. 完成后通知 KB 撤销本轮短期 Token。

在这五项完成前，Stage 6B 状态保持 `offline_implementation_accepted / live_https_acceptance_pending`，不能进入正式 migration、正式 preregistration 或 6C。
