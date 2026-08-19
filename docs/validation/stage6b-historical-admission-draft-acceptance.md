# Stage 6B 历史准入与原子留存草案验收记录

日期：`2026-08-19`

分支：`codex/stage6-historical-validation`

进入基线：`59e1edd80765dbd67635d1497b2fc008d08b21d9`

结论：`draft_ready_for_owner_review / zero_runtime_authority`

## 1. 交付范围

本次只形成 Stage 6B 的精确规则规格、零权限 machine proposal、治理测试和导航。32 项全部保持 `pending`，没有 approved bundle、approval record、capability、confirmation issuer、admission seal runtime、正式状态库 migration 或 historical evaluator。

草案把准入完成条件收敛为内容寻址 `HistoricalRunAdmissionSeal`。单独的公网响应、Receipt、Observation、Manifest、confirmation、pin 或调用方布尔值均不能替代 seal。

## 2. 精确身份

| 制品 | SHA-256 / canonical identity |
| --- | --- |
| specification raw | `96ec47da0eb356f726db3ce1be8015366ad3a804cc3f93d63c5b1c3fc65e3f5a` |
| draft raw | `4a5ed454e6ab152e03dc83b9723f035eacd020ff4bfe16d742427b4aaff827e4` |
| draft canonical bundle | `0ef8808f8de5e44991bbdecb5bb6a63f1b408d0650fd395c958af454adb262d4` |
| draft canonical rules | `4cd66370471d22169f1308ad4cc9f16852b5b6ebe1f20832ca3de6e30598a73b` |
| 32 pending owner items | `17d1d3dabb4d68e8917ce008f6494d644c006c7a4d57f27a81a2e89260a2a3d8` |
| authority profile | `07d3e6a03aa45f38604ecd3728b2ad64b34c075dfc94032431a4486911692238` |

Machine proposal 精确绑定 Stage 6A 批准谱系、`59e1edd` 进入基线、KB `aab36fe` transport snapshot、IS 自有 Receipt/Observation/Retention/Manifest/confirmation draft Schema 与 SQLite v3 技术基础。依赖只用于追溯，不把现有 draft 或骨架升级为历史 authority。

## 3. 关键设计裁决

- 每个 run 仍只有一个对外五字段 `strategy_input_ref`；传递 source Releases 只属于完整 Retention Closure。
- current-status authority 使用真实只读 HTTPS；不可变 export 不能单独证明当前状态。
- 拟议 profile 固定 origin、status path、TLS、禁止 redirect、snapshot 最大年龄 `300s`、最大 clock skew `30s`、confirmation TTL `300s`。
- 原始 status response bytes 以脱敏后的实际响应字节进入 IS CAS；Token 和 Authorization header 永不持久化。
- 网络与候选 CAS 准备在 SQLite 事务外完成；单一 `BEGIN IMMEDIATE` 事务重验全部 identity/head/freshness，并最后写 seal。
- 失败可留下完整但未引用的 CAS orphan；它不是权威状态，不能被 evaluator 读取。所有权威数据库行保持零提交。
- Stage 5D 已预留的 SQLite v4 不被 6B 复用。6B 正式 migration 版本和表前缀仍是批准后的独立 owner 决策；在此之前只允许临时隔离验证库。
- 6B 即使获批也只允许 validation-only admission 验收，不授权正式历史 run；6C/6D 继续独立关闭。

## 4. 验证结果

- Stage 6B draft 专项：`8 passed`；
- Stage 6A/6B 与 Schema 相邻：`46 passed`；
- 全仓 pytest：`986 passed, 4 skipped`；四个 skip 均为 Windows 当前账户没有 symlink privilege 的既有平台 skip；
- Ruff check：通过；
- Ruff format check：通过；
- mypy：通过；
- compileall：通过；
- `git diff --check`：通过。

测试只验证 draft identity、32 项 pointer、零权限、authority profile、closure、confirmation、seal、原子提交、撤回/audit 和失败矩阵的机器表达。没有发起网络请求或写正式状态。

## 5. Owner 需审阅的主要选择

1. 是否接受固定公网 origin 和 `300s / 30s / 300s` freshness 参数；
2. 是否接受“CAS orphan 非权威、数据库 seal 原子可见”的跨文件/SQLite事务模型；
3. 是否接受 confirmation 覆盖完整 closure 的每个 Release，而不是只确认根 Release；
4. 是否接受 6B 获批后仍只在临时隔离库进行 validation-only 验收；
5. 是否接受不占用 Stage 5D SQLite v4，并把 6B 正式 migration 版本延后到独立批准门。

上述任一项调整都应在批准前修改本 draft 并重算全部身份。部分批准不能签发 capability。
