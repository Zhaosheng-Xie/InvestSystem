# Stage 3B 正式跨仓只读 HTTP 验收

> 验收日期：`2026-08-08`
> 结论：`completed`
> 范围：精确 transport snapshot 重固定、独立 KB RC 进程、本机只读 HTTP 兼容验收
> 权限结论：`authority_eligible=false`
> 不包含：tcloud、Stage 3D 策略 smoke、CAS/Observation 持久化、run authority、策略结论或交易权限

## 1. 结论

InvestSystem 已按 KB 机器交接清单，把 Stage 6B 公共传输快照从 Stage 3A 基线重固定到
KB 精确 Git 提交 `aab36fe229104779b50ec71e2dc37a9fad81d285`，并由本仓
`scripts/validate-kb-stage3-http.py` 通过独立 KB RC 进程完成真实只读 HTTP 验收。

验收没有使用 mock、同进程 `TestClient`、KB Python 包、数据库、`raw/`、`staging/`、
`published/` 或 KB 工作树文件作为响应替代。KB 仓库没有被修改。Bearer Token 仅从交接
secret 文件短暂载入进程环境，未进入命令参数、日志、证据或提交，并在 `finally` 中清除。

本轮证明本机 RC 的 transport compatibility，不证明 tcloud，也不执行正式 Context Pack
策略入口。虽然所下载制品是 Context Pack，仍未进行 provider-neutral 映射、
`StrategyRunManifest`、策略 smoke 或 run-scoped 当前状态确认，因此 Stage 3D 未开始。

## 2. 交接与固定身份

| 项目 | 验收值 |
|---|---|
| KB handoff SHA-256 | `cf7226f5245ee0cd91a23b44e2d2ea3688a787071848159df0f6b11b9b8c3d89` |
| KB source commit | `aab36fe229104779b50ec71e2dc37a9fad81d285` |
| KB parent commit | `2c84277ef463b5dd9a3fda3f2976a30cade53af5` |
| KB source tree | `ab64c1cab45eb646ee767e25a50fb78ef3cc57c8` |
| KB contracts tree | `ff106b15c815e5d34a2675827485d2b5576e3f7b` |
| IS transport snapshot lock SHA-256 | `02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169` |
| Provider transport lock | `2943` bytes / `d30bba912a20ddd084fdabc7c0813d4ca806e465e63ce67ae5ab0f7d77241fc0` |
| OpenAPI | `236533` bytes / `864f7fd590f4d356afa49e5cf12d8ace279c2aacf5749e273c9d4566b9623c64` |
| RC endpoint | `http://127.0.0.1:18080` |
| Credential identity | Token ID `7201d9ca-84dd-41b6-a2bd-8e83db432dbd` |
| Read-only scopes | `research:read`、`export:read` |

七文件 transport closure 中，四个 transport Schema 和官方 fixture 的 Git blob 与 Stage 3A
相同；provider transport lock 与 OpenAPI 按新提交更新。两份更新文件均从精确 Git object
取得，并在 IS 中逐字节核对大小和 SHA-256。没有从 KB 工作树复制公共契约。

新 OpenAPI 为 `ReleaseManifest` 正式增加可选 `context_pack_build`。IS 现在按固定 OpenAPI
的具体 path/status response Schema 校验整个 HTTP payload，同时继续校验稳定 envelope、
状态链和跨文档语义；没有放宽或改写 Stage 2A 核心 Manifest Schema。新增测试证明合法
`context_pack_build` 可消费，未契约字段仍失败关闭。

## 3. HTTP 验收输出

以下是 IS 脚本的脱敏原始结构化输出；响应哈希由本次消费者请求自行计算，不沿用 handoff
中的 provider 诊断哈希：

```json
{
  "artifact": {
    "artifact_id": "ctx_cb6b42a9e8acb4b5f81773a2d95e50f4",
    "sha256": "b42e3b7b290868a26d3c2e7194e6cf6aa08295c7e2f7d832812ec2081a1e01b8",
    "size_bytes": 21745
  },
  "authority_eligible": false,
  "contract_snapshot_lock_sha256": "02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169",
  "contract_source_commit": "aab36fe229104779b50ec71e2dc37a9fad81d285",
  "current_status": "published",
  "knowledge_cutoff": "2026-07-28T14:13:31.303929Z",
  "manifest_response_sha256": "b1c2c6c6682381ab4a629e018e66703914a54a83ca0a4626e1d770388937f477",
  "note": "compatibility smoke only; no RunReleaseStatusConfirmation was issued",
  "release_id": "rel_fc8be9b554aa414ca8ad5a14aaec69d9",
  "release_response_sha256": "b78e424fab412edf6989c23b2fad67fae17ff2bfb94c021d4660181111a7ce60",
  "status_response_sha256": "21469d632d4d6d989e6052d9be566f161ab0cad18c6a04a7f90c7a9423507f16"
}
```

脚本成功校验 exact Release、Manifest、完整 status hash chain、`published` current head、
Release/Manifest/status identity closure，以及 artifact 的 Manifest 期望、headers、实际大小和
SHA-256。执行完成后已确认 `INVEST_SYSTEM_KB_BEARER_TOKEN` 不再存在于进程环境。

## 4. 验证结果

- 专项测试：`14 passed`；覆盖 snapshot identity/篡改、官方 HTTP 用例、Context Pack Manifest
  新字段、OpenAPI 未契约字段失败关闭、状态链、bundle closure 与 artifact bytes/headers。
- `pytest -q`：`768 passed, 4 skipped`；四项跳过均因当前 Windows 账户不能创建测试用
  symlink/junction，不是失败。
- `ruff check .`：通过。
- `ruff format --check .`：`79 files already formatted`。
- `mypy`：`78 source files` 通过。
- `compileall -q src tests scripts`：通过。
- `git diff --check`：通过。

## 5. 剩余阻塞与未授权范围

- Stage 3C 尚未开始：真实 tcloud endpoint、远端实例身份和新的短期只读凭据必须单独验收。
- Stage 3D 尚未开始：须把正式交付的精确 Context Pack 映射为 provider-neutral 输入，并从
  同一策略入口执行允许 `ABSTAIN` 的只读 smoke。
- 本轮未把 HTTP 响应或 artifact 写入 InvestSystem CAS/SQLite，没有形成 Fetch/Status/
  Admission Observation，也没有签发 `RunReleaseStatusConfirmation`。
- `authority_eligible` 必须保持 `false`。Stage 3B 不授权 backtest、paper、shadow、live、
  仓位、组合、订单或资金部署，也不扩大 Stage 4 已批准规则的 scope。

因此 Stage 3 总体继续为 `in_progress`；只关闭 3B，不得把“真实 HTTP 兼容通过”解释成
“正式策略数据已准入”或“完整引擎已可运行”。
