# Stage 6A 历史验证预注册治理草案形成记录

日期：`2026-08-19`

分支：`codex/stage6-historical-validation`

基线：`caf1e6702e2653e61c668508d32eb4f7c8f27783`

结论：`draft_formed_for_owner_review / zero_runtime_authority`

## 1. 本轮完成内容

本轮只形成 Stage 6A 历史验证预注册与准入治理草案，没有执行历史数据或新增运行能力：

- 将 Stage 6 拆为 6A 预注册治理、6B historical admission/原子留存、6C development/walk-forward、6D frozen holdout 冠军挑战；
- 固定候选全集、PIT、时间切分、holdout 一次打开、Stage 5D 支持矩阵、冠军挑战、指标/统计、多重检验、参数搜索与偏差审计的建议合同；
- 把 PRD 中 `30` 笔、`95% CI lower > 0`、最大回撤 `15%`、最大赢家 `25%` 等值继续标为 `hypothesis_not_runtime_rule`；
- 形成 35 项 owner 原子批准清单，全部保持 `pending`；
- 明确 6B—6D 尚未授权，当前不得签发 `RunReleaseStatusConfirmation`、写历史运行状态、打开 holdout 或执行 backtest。

## 2. 精确制品身份

| 制品 | SHA-256 / canonical identity |
| --- | --- |
| 6A 规则规格 Markdown | `7ef1126261ddbead37c016fe472a8d518cddb553fe3c3d1214f5c378a9b964df` |
| draft machine proposal 原始字节 | `a071e2509bcf86361836cdd5e5d0748748b607e1129edc4f47c308de7073cdca` |
| draft `RuleBundleDocument` canonical hash | `41759cb4e4db282d98bc70b3a599f632283d2cf79330adab910b1bc9a308eb92` |
| draft `rules` canonical hash | `c1d0298488317318b8d9dedde9f1ff719aa83d08af7196d255482e11522dc097` |
| 35 项 owner items canonical hash | `ea2b4b9d232884d3cd12b4a8003562261fc8e6c8e8f299b88f1df1fb16e3fcfe` |

machine proposal 精确绑定 PLAN v3.6、产业 PRD v0.3、Stage 3D 正式 Context Pack 验收、Stage 5D 第一条回放预注册/验收和 `caf1e67` bounded replay 实现基线。

## 3. 权限边界

以下字段全部保持 false 或空：

- `allowed_run_modes=[]`；
- historical run、Release confirmation、state persistence、holdout open；
- backtest、paper、shadow、live；
- positions、orders、broker、funds deployment；
- KB internal reads 与 KB writes。

默认空 registry 和伪造的其他 scope approval 都不能从 draft 签发 capability。

## 4. 验证结果

- Stage 6A 专项：`7 passed`；
- 全治理相邻套件：`164 passed`；
- 全仓 pytest：`971 passed, 4 skipped`；四个 skip 均为 Windows 当前账户无 symlink privilege 的既有平台 skip；
- Ruff check：通过；
- Ruff format check：`113 files already formatted`；
- mypy：`Success: no issues found in 111 source files`；
- compileall：通过；
- `git diff --check`：通过。

## 5. 尚未完成与下一门

6A 还没有 owner 批准，因此不能标记为 completed。下一步必须先由 owner 审阅并原子确认或修改 35 项决定，尤其是精确样本日期、horizon、purge、embargo、最小有效样本、coverage、统计调整方法和 full-vs-best-simple 实质增量门槛。

只有 6A approved identity 与 capability 形成后，才能单独设计和授权 6B。6B 实现仍必须在读取策略历史表现之前完成 Release 状态确认、Receipt/Observation/Manifest/预注册/留存闭包的原子准入和失败零写验收。

本记录不证明策略有效，不是历史验证报告，也不授权 Stage 7。
