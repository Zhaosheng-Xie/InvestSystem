# Stage 6B 真实 HTTPS validation-only seal 验收

验收状态：`passed / completed_with_scope_limits`

验收时间：`2026-08-19T16:41:10.257704Z`（北京时间 `2026-08-20 00:41:10`）

本记录只证明 InvestSystem 使用固定公共 transport contract、KB producer handoff 和短期只读凭据，对完整根 Release 闭包完成了一次真实公网 validation-only admission/seal。它不授权 historical evaluator、正式状态库迁移、6C/6D、backtest、paper、shadow、live、仓位或订单。

## 1. 固定输入

- IS 分支：`codex/stage6-historical-validation`
- 执行代码提交：`c19ac360059c738565a0ee8e515d8ccddcf20a53`
- Base URL：`https://82.157.112.120`
- handoff SHA-256：`446fe4cf8ddea44214d83b7372cd36fa1ea7fe7b345fab18c9595b767106bd9e`
- producer validation report SHA-256：`6dc2e100f3c7ff97fa451eff471ec0614bbba8d39459ef66dc84958e6dc8e241`
- transport source commit：`aab36fe229104779b50ec71e2dc37a9fad81d285`
- transport snapshot lock：`02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169`
- 根 Release：`rel_fc8be9b554aa414ca8ad5a14aaec69d9`
- Source Release：`rel_02f1148031c04036a5f7d5cda9807fb5`
- knowledge cutoff：`2026-07-28T14:13:31.303929Z`
- 根 manifest hash：`1a6759f2563d9708ec1973ab5f701c059e870d2ba12d1c84b11d1578b1cdaf92`

根 `strategy_input_ref` 保留全部五字段，且本次仅允许一个根输入引用。根 Receipt 只包含根 Release 的两个制品；留存闭包另行包含根与 Source Release 的全部十个制品。

## 2. 真实 HTTPS 结果

两个 Release、Manifest 和 Status 均从公网正式接口获取并闭合为 `published`。内容响应字节哈希如下：

| Release | Release response | Manifest response | Status response |
|---|---|---|---|
| `rel_fc8be9b554aa414ca8ad5a14aaec69d9` | `a7beb6ddd7eab8317854edf14d96cb6a4d211cfea5369edea3452012c41e8831` | `2385e799172ce2b8cc7bf55338190cac75ce1ab6cd4b8414149f34de90911081` | `bea28f71546787299327b2cccb6be8ac723c18d2afbd8b209237dc981a7c0b16` |
| `rel_02f1148031c04036a5f7d5cda9807fb5` | `b77b6af3a953be855500aa5a1344952180a80190b45e885a8c81dcf994b1ddc9` | `aeaee364475b6b763ea1a83c7df87feab7b29d3954a73aefed0319a0c977088a` | `33c024e416c32026bdd7912d2726e8535fe48d6c6b71fe6e56630ff147f56eaf` |

在 admission 窗口内又执行了两次新的 Status HTTPS 读取，响应 SHA-256 分别为：

- 根 Release：`60df96d23c3e5c7de2a8a44022e4474ba0f902b1fffa4e3815fcd361b395205e`
- Source Release：`86722515efb11ade156a405260cf901298f157b1f0127483e91190f81e49074d`

十个 artifact 的下载字节均与 handoff 中的精确 ID、SHA-256、size、Content-Type 和固定响应头一致：

| Release | Artifact | SHA-256 |
|---|---|---|
| root | `ctx_cb6b42a9e8acb4b5f81773a2d95e50f4` | `b42e3b7b290868a26d3c2e7194e6cf6aa08295c7e2f7d832812ec2081a1e01b8` |
| root | `ctx_cb6b42a9e8acb4b5f81773a2d95e50f4-record-schema` | `ae5965fe5edfb4bf4053a6471653e2bd003c1ae55ece180820f651118e2fbe17` |
| source | `disclosure-schedules-v1` | `494794b25eac475a21f16e04a5d0a92c607c8216f836753b5964d0a920905eb9` |
| source | `disclosure-schedules-v1-record-schema` | `679b8c16e836f35119d952eaaab16564ca6c449e4bcd56bab4e991a28b73f6c8` |
| source | `financial-segments-v1` | `4058f2e7b4b443e1b4bd694141e28b319e142d1d0f2f54547fab04bf7879885d` |
| source | `financial-segments-v1-record-schema` | `07e1f2ad24cb272516cb9b55ef6ab3319a2badbacd1ce6c8bfa42e6384a4ccda` |
| source | `financial-statements-v1` | `8f53a391d1fd3b44c451db0a160179f2f4fc607a4689dece2615f5621b7849b2` |
| source | `financial-statements-v1-record-schema` | `c96fd87189fa9ba5077e4c1fb69c08612860ba69874adc93096915e336795fa8` |
| source | `optical-evidence-bundle-v1` | `540ba608404bf550672d9168166c2f71b6888aaca7e4e15e20b8bd385b547fd6` |
| source | `optical-evidence-bundle-v1-record-schema` | `ab410a1d25b93c9fece1fe266f9a02622ffbe0ff02632932734c1c29f5692ee7` |

## 3. 收据、闭包与 seal

- Receipt hash：`52592d19d563274e5c1a4910e4332357144f57fd2fc46954738086d2cf0df0f5`
- Release retention closure hash：`5e27393649838807b6732187a65abcf7a8213927d0e70b09d331b7ec7d79c271`
- run ID：`run_stage6b_validation_2224d191e4937dea859c22c1`
- seal ID：`stage6b_seal_7e5bbf78987b6818cd00ddb9`
- envelope hash：`bcc92aece6c3d54cedbc109f860eca33eb6d23f45ef747801d9f354fb956594f`
- confirmation hash：`55b54b3bdf3309a98f6e8e7543d099587b33b68bee79a9b19915fd7b18d3e244`
- seal hash：`9cb4e7d8b71e288a739ade9f81e89f9e81b02fc43ec264fd29dd80be88e63100`
- commit generation：`1`
- seal status：`SEALED_VALIDATION_ONLY`

该 confirmation 只属于隔离 Stage 6B validation store，不是正式 run authority。`authority_eligible=false`、`validation_only=true`、`strategy_evaluator_calls=0`；正式 `var/state`、正式 `var/cache` 和 KB 均未修改。

## 4. 安全与职责边界

- Token 只在单一进程内读取；未打印、复制、提交或持久化。
- 本次只使用 `research:read` 与 `export:read`。未授予 `evidence:read`，因此没有调用 Context Pack 查询接口；该接口的 `403` 是交付方明确验证的预期边界。
- IS 只消费公网 Release、Manifest、Status 和 Artifact，不读取 KB SQLite、raw、staging、published 目录、源码或 Python 包。
- 隔离 validation store 位于系统临时目录；没有写正式业务状态、CAS、Observation、仓位、订单或交易凭据。

## 5. 验证结果与剩余边界

- producer-handoff 专项：`4 passed`
- Stage 6B 相邻专项：`40 passed`
- 全仓 pytest：`1018 passed, 4 skipped`
- Ruff check：通过
- Ruff format check：通过
- mypy：通过，`126` 个 source files 无问题
- compileall：通过
- `git diff --check`：通过

Stage 6B 的“离线实现 + 真实 HTTPS validation-only seal”完成。正式 migration、正式 historical run、策略 evaluator、6C walk-forward、6D holdout 和任何交易模式仍未授权，不能由本验收推导开放。

验收记录提交后，KB 应立即撤销本轮短期 Token。
