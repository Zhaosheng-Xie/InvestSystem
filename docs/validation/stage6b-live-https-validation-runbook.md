# Stage 6B 真实 HTTPS validation-only seal 运行手册

文档状态：`prepared_not_executed`

本手册只说明如何在 KB producer handoff 到达后执行 Stage 6B 的真实公网验收。当前尚未读取 KB 临时目录、尚未发起公网请求、尚未创建 validation seal，也未完成 Stage 6B 真实 HTTPS 验收。

## 1. 固定边界

- 入口脚本：`scripts/validate-kb-stage6b-admission.py`。
- 只接受 Stage 3D 已验收的 `handoff_schema_version=1.0.0` Context Pack handoff；结构或哈希不一致时在 HTTP 和 SQLite 之前失败。
- 凭据文件只允许 `KB_BASE_URL` 与 `KB_BEARER_TOKEN` 两个键；Token 不得作为命令参数、输出字段、仓库文件或 seal 内容。
- 真实运行只连接批准 origin `https://82.157.112.120`，使用固定 transport snapshot `02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169`。
- validation root 必须位于仓库正式 `var/state`、`var/cache` 和整个 `var/` 之外。脚本不写正式状态库或正式缓存。
- 输出始终保持 `validation_only=true`、`authority_eligible=false`、`strategy_evaluator_calls=0`；不运行 historical evaluator，不打开 6C/6D，不产生仓位或订单。

## 2. Producer handoff 最小模板

KB 交付必须保持既有 Stage 3D handoff 的严格对象形状，并至少闭合以下承重字段；任何额外字段都不能增加 authority 或替代这些承重身份：

```text
handoff_schema_version = 1.0.0
production_base_url
transport_contract_source_commit
transport_contract_snapshot_lock_sha256
transport_compatible_with_is_snapshot = true
authority_eligible = false
context_pack_release_id
context_pack_id
context_pack_hash
source_graph_hash
knowledge_cutoff
manifest_hash
strategy_input_ref
context_pack_artifact
context_pack_schema_artifact
source_releases[exactly one Evidence Release]
  release_id
  manifest_hash
  load_bearing_artifacts[Evidence bundle + public schema]
```

每个 artifact 项必须提供精确 `artifact_id`、`sha256`、`size_bytes`、`content_type`、`item_type`、`schema_id`、`schema_version` 和 `record_schema_hash`。handoff 文件本身须由交付方另给 SHA-256；IS 不接受 `latest` 或未锁定引用。

## 3. 无网络预检

先在外部临时凭据仍有效时运行默认模式。默认模式会读取并校验 handoff、handoff SHA、base URL 和凭据文件形状，但不会构造 HTTP client、不会发出网络请求，也不会创建 validation root：

```powershell
$python = "E:\Conda\envs\Data_Analysis\python.exe"
$handoff = "<KB 提供的绝对 handoff JSON 路径>"
$credential = "<KB 提供的绝对临时 env 路径>"
$handoffSha256 = "<KB 提供的 handoff SHA-256>"
$codeCommit = git rev-parse HEAD

& $python .\scripts\validate-kb-stage6b-admission.py `
  --handoff $handoff `
  --handoff-sha256 $handoffSha256 `
  --credential-env $credential `
  --base-url "https://82.157.112.120" `
  --code-commit $codeCommit
```

预检成功输出必须包含：`acceptance=preflight_passed`、`network_requests=0`、`seal_created=false`、`authority_eligible=false`。

## 4. 真实 validation-only 执行

预检通过后，在仓库外创建一次性隔离根，并显式增加 `--execute`：

```powershell
$validationRoot = Join-Path $env:TEMP ("investsystem-stage6b-" + [guid]::NewGuid().ToString("N"))

& $python .\scripts\validate-kb-stage6b-admission.py `
  --handoff $handoff `
  --handoff-sha256 $handoffSha256 `
  --credential-env $credential `
  --base-url "https://82.157.112.120" `
  --code-commit $codeCommit `
  --validation-root $validationRoot `
  --execute
```

执行顺序固定为：

1. 通过真实 HTTPS 完整复跑 Stage 3D Context Pack/Evidence 内容、Schema、PIT 与引用闭包验证；
2. 再次获取精确 Release/Manifest/artifact，构造根 `ArtifactConsumptionReceipt` 与两 Release 的传递 `ReleaseRetentionClosure`；
3. 对 closure 中每个 Release 发起新的完整 status-history HTTPS 请求；
4. 在同一 admission 窗口签发 validation-only confirmation；
5. 将 Manifest、artifact、原始 status bytes、Observations、confirmation、Manifest、pin 与 seal 原子写入隔离 validation store。

任何 Release 非 `published`、状态过旧、时钟偏差、hash/size/Schema/closure 漂移、Token 权限不足或隔离目录错误，均不得留下 seal。

## 5. 验收记录与收尾

真实运行成功后，另建 Stage 6B 真实 HTTPS 验收记录，至少保存脚本的脱敏输出：handoff SHA、transport lock、`strategy_input_ref`、knowledge cutoff、内容响应哈希、artifact 哈希、fresh status response 哈希、receipt/closure/envelope/confirmation/seal 哈希、隔离事务 generation，以及专项和全仓质量门结果。

验收记录不得保存 Token、凭据文件内容或凭据文件副本。完成后应立即通知 KB 会话撤销短期 Token；Token 撤销不是 historical evaluator 的授权，6C 仍须独立批准。
