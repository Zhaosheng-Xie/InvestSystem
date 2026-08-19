# Stage 6B 历史准入治理批准验收记录

日期：`2026-08-19`

分支：`codex/stage6-historical-validation`

进入基线：`5cdf67c387148c6d5dcdd415343ec497cd7b1bd7`

结论：`approved_validation_capability_accepted / zero_formal_historical_authority`

## 1. Owner 批准与风险结论

owner 要求复核精确规则包的重大风险，并明确表示没有重大风险即可批准继续。复核确认固定公网 profile、新鲜度窗口、CAS orphan 和未决 migration 都只可能使 validation admission 失败，不会生成正式历史 authority；因此将 `6B-01—6B-32` 按同一 exact draft 整包原子批准。

本批准只允许实现和验收隔离临时库中的 admission contracts、真实只读 HTTPS status confirmation 与 validation-only seal。正式历史 run、策略 evaluator、正式状态库 migration、6C/6D 和全部交易权限继续关闭。

## 2. 精确批准谱系

| 制品 | SHA-256 / canonical identity |
| --- | --- |
| specification raw | `96ec47da0eb356f726db3ce1be8015366ad3a804cc3f93d63c5b1c3fc65e3f5a` |
| draft raw | `4a5ed454e6ab152e03dc83b9723f035eacd020ff4bfe16d742427b4aaff827e4` |
| draft canonical bundle | `0ef8808f8de5e44991bbdecb5bb6a63f1b408d0650fd395c958af454adb262d4` |
| draft canonical rules | `4cd66370471d22169f1308ad4cc9f16852b5b6ebe1f20832ca3de6e30598a73b` |
| draft 32 items | `17d1d3dabb4d68e8917ce008f6494d644c006c7a4d57f27a81a2e89260a2a3d8` |
| approval document raw | `040cbe7dc04b0c153d8cd5902486dc4ffb8830c1018bccbfa747678663935aac` |
| approved bundle raw | `c39d06fc822beeec1a78627c67c7ecb82909cf6f3a279786052f74013ebc06a8` |
| approved canonical bundle | `c8ee13e82bf3e91f7c5f948c71da5f6af21969caa5ca54792d10e5571c334414` |
| approved canonical rules | `6f3ddba4d510342c9679975576ef2797ddd481034dddef391ec43c3e80b0c20b` |
| approved 32 items | `ad32dfa2db1ec4c8f8b9e2f8f2baf8a604626f9effd15cc049d57d88953827b6` |
| approval JSON raw | `a1a28288a13245ad7cd420033a6a11f64906c97498b8451a0fe07675d6abbc3d` |
| approval record canonical | `e4ee892f59efea1e29ddb4c8d2ef7adc41711d2a8219e10f4c29f9724214d185` |
| authority profile canonical | `07d3e6a03aa45f38604ecd3728b2ad64b34c075dfc94032431a4486911692238` |

原 specification 与 draft proposal 未修改。approved bundle 只通过 exact source hashes 接受 owner 已审阅语义，不在批准时改写 profile、时间窗口、事务语义或 failure matrix。

## 3. Capability 与失败关闭

新增 approval scope：`stage6_historical_admission_validation`。

该 capability 允许：

- 实现 6B admission contracts、issuer、adapter；
- 使用短期只读凭据进行 validation-only 公网 HTTPS status 验证；
- 在独立临时 IS state/cache 中签发 `authority_eligible=false` 的 confirmation 与 seal。

以下能力全部保持 false：

- 正式 historical run 与策略 evaluator；
- development、walk-forward、holdout；
- 正式状态库 migration 和 Stage 5D SQLite v4 复用；
- backtest、paper、shadow、live、positions、orders、broker、funds deployment；
- KB internal read/write。

默认空 registry、错误 scope、部分 32 项、6C/6D authority 提前打开、正式 run/migration/交易权限扩张、draft source 或 authority profile 漂移均失败关闭。

## 4. 验证结果

- Stage 6B approval 专项：`7 passed`；
- Stage 6A/6B 治理相邻：`29 passed`；
- 全仓 pytest：`993 passed, 4 skipped`；四个 skip 均为 Windows 当前账户没有 symlink privilege 的既有平台 skip；
- Ruff check：通过；
- Ruff format check：通过；
- mypy：通过；
- compileall：通过；
- `git diff --check`：通过。

这些结果只验收批准身份和 capability 边界，不代表 6B runtime 已实现，也不证明任何策略有效。

## 5. 下一门

下一步按批准顺序实现纯 contracts/issuer/adapter，再实现隔离临时库中的原子 validation seal，并运行完整 failure matrix。真实 HTTPS 验收需要新的短期只读凭据，且不得修改 KB。正式 migration 版本/表前缀仍须另行 owner 批准；6B runtime 独立验收前不得进入 6C。
