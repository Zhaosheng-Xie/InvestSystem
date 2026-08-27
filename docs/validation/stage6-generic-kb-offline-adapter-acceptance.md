# Stage 6 通用 KB 契约离线 Adapter 验收

验收日期：`2026-08-27`

结论：`completed_with_scope_limits / synthetic_contract_only / zero_runtime_authority`

## 输入身份

- KB provider contract commit：`50604ea46e14580be976e1cf46c349a2d3088740`
- KB 普通 merge commit：`4352c10c6c639e25d4c190dfc9ec58ee9e76aa86`
- KB merge 后 Stage 6A/Linux security/Stage 7 CI：全部通过
- IS 授权与边界提交：`eb702559511083d2d0d603725be50997e0c22bbe`
- snapshot：`contracts/providers/investment_research_kb/stage6-provider-contracts-v1/`
- snapshot lock raw SHA-256：`513b3e8728fc299780bbd3205f0fa049a63bb4946b5eaa8193fc51447b5b333a`
- support matrix raw SHA-256：`34f7f4055bb243ed4852f36074d44d31819f255ec524198f2f044d781db3cab8`

显式 vendoring 脚本从 KB Git object 重建到临时目录后，19 个 vendor 文件和 snapshot lock 与仓库版本逐字节一致；没有读取 KB 工作树文件、Python 包或数据库。

## 已实现

1. 完整验证 snapshot lock、19 个 Git blob、size、SHA-256 和闭包；
2. 加载 16 个 active draft Schema，验证 provider catalog、benchmark/factor registry 和九类官方 synthetic examples；
3. 从通用 ReleaseReference 构造 IS `StrategyInputRef`；
4. 投影可变长度 aggregate dependency closure 和客观 release data profile；
5. 从 registry 精确选择 CSI `H00985`，禁止 fallback；
6. 验证 ADV20/Beta120 definition、observation、basis hash、completeness 和 PIT 顺序；
7. 提供 exact 20-session ADV arithmetic mean 与 exact 120-pair OLS-with-intercept 纯 Decimal 重算；
8. 保留既有 KB v1 `strategy-input-ref` 兼容，transport v1 未 repin；
9. 文件篡改、未知字段、错误定义、缺窗口、非规范 Decimal、负成交额和零方差失败关闭。

官方 synthetic fixture 的确定性 IS result hash：

`a9e43b70098be362b3795375f3eb597641416af5b83eed5a12a636c9e8e4c708`

## 正确阻塞的内容

- H00985 registry 身份闭合，但 redistribution=`pending_explicit_permission`，所以真实接受保持 `BLOCKED`；
- ADV20 observation 为 complete 20-session，但 fixture 只有 raw-basis hashes，没有 20 条 raw records，所以只接受定义/哈希闭包，不冒充重算；
- Beta120 observation 只有 118 对，保持 `incomplete`；
- data profile 明确 benchmark 历史连续性未覆盖，整体为 `PARTIALLY_READY_SYNTHETIC_PROFILE`；
- 没有 scope-eligible Published historical Release、真实 handoff 或 current authority。

## 验证

- 本切片专项：`15 passed`
- 架构与相邻测试：`60 passed, 1 skipped`
- 全仓 pytest：`1179 passed, 4 skipped`
- Ruff、format、mypy、compileall、diff-check：全部通过

Windows 的四项 skip 来自当前账户缺少 symlink 权限，与本切片无关。

## 权限边界

本轮没有网络数据访问、真实 Release、Token、handoff、transport repin、candidate、coverage、historical run、holdout、backfill、migration 或 KB 写入；不授权 backtest、paper、shadow、live、仓位或订单。

下一门是 KB 取得合法数据源、historical PIT 和 raw basis，并在另行授权后形成 immutable Release candidate/producer validation。上述完成前 IS 不进入真实 handoff 或历史运行。
