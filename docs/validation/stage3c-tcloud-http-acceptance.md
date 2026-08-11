# Stage 3C 真实 tcloud 只读 HTTPS 验收

> 验收日期：`2026-08-11`
> 结论：`completed`
> 范围：真实公网 HTTPS、正式 Release/Manifest/Status、精确 artifact 字节与响应头闭合
> 权限结论：`authority_eligible=false`
> 不包含：`RunReleaseStatusConfirmation`、CAS/Observation、Stage 3D Context Pack 策略 smoke、任何业务运行或交易权限

## 1. 验收结论

InvestSystem 使用仓库自有的 `scripts/validate-kb-stage3-http.py`、已固定的 Stage 6B transport contract snapshot 和短期只读凭据，直接连接真实公网端点 `https://82.157.112.120`。正式 Release、Manifest 和完整 Status 均通过 HTTPS 获取并通过固定 OpenAPI/Schema、身份和哈希链校验；Release 当前状态为 `published`。

精确 artifact `market-daily-v1` 已通过 Manifest 期望、响应正文、大小、SHA-256 与强制响应头的闭合校验。验收没有使用 mock、`TestClient`、KB SQLite、KB Python 包、KB 源码或本机服务，也没有修改 KB。Bearer Token 只从 owner 指定文件载入执行进程环境，未进入参数、输出、文档、Git diff 或提交，并在执行结束后从进程环境清除。

本轮只证明真实 tcloud 的生产传输兼容性。该 Release 是正式 `market_daily` Release，不是正式 Context Pack；provider-neutral Context Pack 映射、策略入口 smoke 和 `ABSTAIN`/结论验证仍属于 Stage 3D。

## 2. 固定身份

| 项目 | 验收值 |
|---|---|
| Base URL | `https://82.157.112.120` |
| Release ID | `rel_10e257ad87734d7bb5cadc55e7b444e7` |
| Artifact ID | `market-daily-v1` |
| Contract source commit | `aab36fe229104779b50ec71e2dc37a9fad81d285` |
| Contract snapshot lock SHA-256 | `02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169` |
| Knowledge cutoff | `2026-07-30T15:14:46.995260Z` |
| Current status | `published` |

## 3. 实测响应与 artifact 闭合

| 响应或字段 | 实测值 |
|---|---|
| Release response SHA-256 | `23502bd8682f37de1455245faf309137db8538ff71d704ef94eadc89b32820aa` |
| Manifest response SHA-256 | `68295dabbda759cf85d2048444113f36aea500f7178ad38fdeb3ef57ce36b486` |
| Status response SHA-256 | `57540bd992b6f4cb16de5e2ef10b674ba4ceb8298afc9780cbf126906c1625d8` |
| Artifact response/body SHA-256 | `60f71e3b7a9b2cc7c2bac770c4e0453e2f99dafcc4f57077b3bc73399b8a7a6c` |
| Artifact size / `Content-Length` | `14814` |
| `X-Artifact-ID` | `market-daily-v1` |
| `X-Artifact-SHA256` | `60f71e3b7a9b2cc7c2bac770c4e0453e2f99dafcc4f57077b3bc73399b8a7a6c` |
| `X-Dataset-Release-ID` | `rel_10e257ad87734d7bb5cadc55e7b444e7` |
| `ETag` | `"60f71e3b7a9b2cc7c2bac770c4e0453e2f99dafcc4f57077b3bc73399b8a7a6c"` |

客户端同时要求非空 `Content-Type`。任何正文大小、正文哈希、`Content-Length`、`ETag`、`X-Artifact-ID`、`X-Artifact-SHA256` 或 `X-Dataset-Release-ID` 不一致都会失败关闭；本次全部通过。动态 HTTP meta 会改变 Release/Manifest/Status 的响应字节，因此这里只记录本次实测响应哈希，不要求与 Stage 3B 本机 RC 响应相同。

## 4. 脱敏脚本输出

```json
{
  "artifact": {
    "artifact_id": "market-daily-v1",
    "sha256": "60f71e3b7a9b2cc7c2bac770c4e0453e2f99dafcc4f57077b3bc73399b8a7a6c",
    "size_bytes": 14814
  },
  "authority_eligible": false,
  "contract_snapshot_lock_sha256": "02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169",
  "contract_source_commit": "aab36fe229104779b50ec71e2dc37a9fad81d285",
  "current_status": "published",
  "knowledge_cutoff": "2026-07-30T15:14:46.995260Z",
  "manifest_response_sha256": "68295dabbda759cf85d2048444113f36aea500f7178ad38fdeb3ef57ce36b486",
  "note": "compatibility smoke only; no RunReleaseStatusConfirmation was issued",
  "release_id": "rel_10e257ad87734d7bb5cadc55e7b444e7",
  "release_response_sha256": "23502bd8682f37de1455245faf309137db8538ff71d704ef94eadc89b32820aa",
  "status_response_sha256": "57540bd992b6f4cb16de5e2ef10b674ba4ceb8298afc9780cbf126906c1625d8"
}
```

## 5. 验证结果

- 真实公网 operator smoke：`passed`。
- HTTP Client 与 transport snapshot 专项：`14 passed`。
- 全仓 `pytest -q`：`947 passed, 4 skipped`；四项跳过均因当前 Windows 账户不能创建测试用 symlink/junction，不是失败。
- `ruff check .`：通过。
- `ruff format --check .`：`106 files already formatted`。
- `mypy`：`105 source files` 通过。
- `compileall -q src tests scripts`：通过。
- `git diff --check`：通过。

## 6. 权限与剩余边界

- `authority_eligible` 保持 `false`；没有签发 `RunReleaseStatusConfirmation`。
- 没有写入 InvestSystem CAS、SQLite、Receipt、Observation、Manifest 或任何业务运行状态。
- 没有保存 HTTP 响应正文或 artifact 到仓库；验收记录只保存非敏感身份与哈希。
- 没有授权 backtest、paper、shadow、live、真实账户、仓位、订单、券商接入或资金部署。
- Stage 3 总体继续为 `in_progress`；3A—3C 已完成，3D 正式 Context Pack 策略 smoke 尚未开始。
- owner 已于 `2026-08-11` 确认 KB 会话完成本轮短期 Token 撤销；该凭据不再用于 Stage 3D 或任何后续验收。
