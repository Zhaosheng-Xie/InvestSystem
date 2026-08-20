# Stage 6C 匿名合成 Kernel 第一纵向切片验收

验收状态：`completed_with_scope_limits`

验收日期：`2026-08-20`

本记录证明 Stage 6C v0.2 批准后的第一条匿名合成纵向切片已经实现：typed development projection、opaque holdout commitment、隔离证据、连续 synthetic NAV/benchmark、零外部现金流、精确 TWR 和 deterministic replay。它不是完整 6C development/walk-forward，不运行真实历史样本，不读取 holdout，不持久化，也不产生策略有效性结论。

## 1. 实现范围

- `Stage6CDevelopmentProjection`：只允许 synthetic/validation-only，禁止 holdout records、holdout metadata proxy 和 authority；
- `Stage6DHoldoutCommitment`：只保存 opaque commitment 与 custodian/generation 身份，显式不授予 artifact read；
- `Stage6CHoldoutIsolationEvidence`：绑定 projection/commitment、不同 namespace、进程访问、mount/link、canary 与 read-count；
- `Stage6CSyntheticKernelCase`：只接受连续匿名 synthetic NAV points、零 external flow、固定 Decimal context；
- `evaluate_stage6c_synthetic_twr_kernel`：要求精确 6C capability，先验证隔离，再按批准公式计算 daily excess factor、gross factor 和 `252/N` 年化净超额；
- `Stage6CSyntheticKernelResult`：完整 content-addressed replay，所有正式/持久化/holdout/交易权限为 false。

全部实现为纯函数；没有文件、网络、数据库、KB、缓存或环境时钟 I/O。

## 2. 固定 Golden

- projection hash：`cd45146d2a1c9592b5f274c155a07192db1d1f6bddb6bed66e440309bcd23fbe`
- holdout commitment hash：`e60d4487f9c89c079fc9c076a7037b69e3b6943aa0b4ab359e8b3caed401835f`
- isolation evidence hash：`fd30fd6d4230d5761995245a0975a0dbf3b647588be66390cd3180d16c63171f`
- case hash：`100de1e6e284cc68699a694045226a5aa9abe395380739c4393e4c3e5dd63dbe`
- sessions：`252`
- gross excess factor：`2`
- annualized net excess percentage points：`100`
- replay hash：`0c9307fb6064914bc4fa71439dd20319dff8954e02fd4ed5ca0f4af0723a9a02`

该数值仅是匿名 synthetic 公式 golden，不是投资表现或收益承诺。

## 3. 失败关闭

以下任一条件均返回 `PRECHECK_BLOCKED` 且不发布 partial TWR：

- projection 与 commitment 边界或 source closure 不一致；
- 两边同时漂移到未经批准的 holdout 日期；
- isolation evidence 未精确绑定 projection/commitment；
- 进程拥有 holdout read access；
- holdout 被 mount/link；
- canary 未被拒绝；
- holdout read count 非零。

其他阶段 capability、非零 external flow、holdout/authority 声明、非法 Decimal/NAV/session 和自哈希漂移均在构造或 evaluator 前失败关闭。

## 4. 权限边界

- `synthetic=true`
- `validation_only=true`
- `not_a_complete_stage6c_walk_forward=true`
- `formal_historical_run=false`
- `holdout_artifact_read=false`
- `persists_state=false`
- `authority_eligible=false`

当前未实现：candidate inventory、fold planner、data readiness、coverage selection audit、30-trade gate、benchmark peer construction、calendar bootstrap、company/risk sensitivity、Holm、消融/压力、champion freeze 或 6D handoff。

## 5. 验证结果

- Stage 6C kernel 专项：`11 passed`
- Stage 6 相邻：`85 passed`
- 全仓 pytest：`1049 passed, 4 skipped`
- Ruff check / format check：通过
- mypy：通过，`132` 个 source files 无问题
- compileall：通过
- `git diff --check`：通过

下一条最小切片应实现匿名合成 candidate inventory、时间 fold planner 与 outcome-blind coverage selection audit，仍不接真实数据或 holdout。
