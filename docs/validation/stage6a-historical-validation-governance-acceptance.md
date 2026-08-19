# Stage 6A 历史验证预注册治理批准验收记录

日期：`2026-08-19`

分支：`codex/stage6-historical-validation`

进入基线：`b45e13c8879dbfb00598cfe3aef190b2cd4adf0e`

结论：`approved_governance_capability_accepted / zero_historical_run_authority`

## 1. Owner 批准

owner 在当前 task 中要求评估风险，并明确表示没有重大风险即可批准。复核确认 35 项只约束研究设计、准入和失败关闭，不授权历史执行，因此按同一 exact draft 将 `6A-01—6A-35` 整包原子批准。

本批准没有把 PRD hypothesis 数值提升为 evaluator 规则，也没有授权 6B—6D。

## 2. 精确批准谱系

| 制品 | SHA-256 / canonical identity |
| --- | --- |
| specification raw | `7ef1126261ddbead37c016fe472a8d518cddb553fe3c3d1214f5c378a9b964df` |
| draft raw | `a071e2509bcf86361836cdd5e5d0748748b607e1129edc4f47c308de7073cdca` |
| draft canonical bundle | `41759cb4e4db282d98bc70b3a599f632283d2cf79330adab910b1bc9a308eb92` |
| draft canonical rules | `c1d0298488317318b8d9dedde9f1ff719aa83d08af7196d255482e11522dc097` |
| draft 35 items | `ea2b4b9d232884d3cd12b4a8003562261fc8e6c8e8f299b88f1df1fb16e3fcfe` |
| approval document raw | `392eb5461c3e1c0e2ff3654fe0eea729de2671adb0bc5207854b98f8fbe79b9f` |
| approved bundle raw | `4d933c04b341e454009f49ed9e912d22d4b62878473e02e47ebf51e956cdabee` |
| approved canonical bundle | `9a3f663936b0ad83795c7338c6b93fc9617d1f9ed6f4ccca6f92dd2fd06f6505` |
| approved canonical rules | `f1f42898fd61f21724d8bfe22158d2a22f6499b52c670d27e7c2f69800cbea80` |
| approved 35 items | `03a4fdde65cc5d4d567eb71b46cdd57e95348e90a552330cf6958cbd409e8dbb` |
| approval JSON raw | `b5cae6779ab50a153f8aef37017f8ff3a59caa3f05642f169833edd04e0dedeb` |
| approval record canonical | `c81fca2c42a160b91a4ebbb2f2144b8e12ada28a270cb1f810104695bb0a3076` |

原 specification 和 draft proposal 未修改。approved bundle 通过 exact canonical hash 接受原 draft 语义，没有复制时改写阈值或扩大支持矩阵。

## 3. Capability 与失败关闭

新增 approval scope：`stage6_historical_validation_governance`。

该 capability 唯一允许：

- 证明 owner 已批准 exact 6A 预注册治理；
- 形成 6B exact draft，供 owner 后续审阅。

以下能力全部保持 false：

- 6B implementation、6C execution、6D holdout；
- historical run、Release status confirmation、state persistence、holdout open；
- backtest、paper、shadow、live；
- positions、orders、broker、funds deployment；
- KB internal read/write。

验证覆盖：默认空 registry、错误 stage scope、部分 35 项、6B authority 提前打开、任何历史/交易权限扩张、draft source hash 漂移和 hypothesis guard 漂移均失败关闭。

## 4. 验证结果

- Stage 6A draft/approval/schema 专项：`38 passed`；
- 全治理相邻套件：`195 passed`；
- 全仓 pytest：`978 passed, 4 skipped`；四个 skip 均为 Windows 当前账户无 symlink privilege 的既有平台 skip；
- Ruff check：通过；
- Ruff format check：通过；
- mypy：通过；
- compileall：通过；
- `git diff --check`：通过。

## 5. 下一门

Stage 6A 治理批准已经完成，但 Stage 6 整体仍是 `in_progress`。下一步只能形成 6B historical admission/atomic retention 精确草案，至少需要冻结：新鲜 Release 状态证据、run-scoped confirmation、单 `strategy_input_ref`、Receipt/Observations/Manifest/完整 Release 闭包原子事务、撤回处理、幂等/冲突、失败零写和 audit replay。

6B 草案必须再次由 owner 独立批准；当前 capability 不能执行 6B，也不能读取策略历史表现。
