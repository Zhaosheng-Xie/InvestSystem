# Stage 6B 真实 HTTPS validation-only seal 运行手册

文档状态：`prepared_not_executed`

本手册只说明如何在 KB producer handoff 到达后执行 Stage 6B 的真实公网验收。当前尚未读取 KB 临时目录、尚未发起公网请求、尚未创建 validation seal，也未完成 Stage 6B 真实 HTTPS 验收。

## 1. 固定边界

- 入口脚本：`scripts/validate-kb-stage6b-admission.py`。
- 只接受专用 `purpose=invest-system-stage6b-real-https-validation-only-admission`、`handoff_schema_version=1.0.0` producer handoff；结构或哈希不一致时在 HTTP 和 SQLite 之前失败。
- 凭据文件只允许 `KB_BASE_URL` 与 `KB_BEARER_TOKEN` 两个键；Token 不得作为命令参数、输出字段、仓库文件或 seal 内容。
- 真实运行只连接批准 origin `https://82.157.112.120`，使用固定 transport snapshot `02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169`。
- validation root 必须位于仓库正式 `var/state`、`var/cache` 和整个 `var/` 之外。脚本不写正式状态库或正式缓存。
- 输出始终保持 `validation_only=true`、`authority_eligible=false`、`strategy_evaluator_calls=0`；不运行 historical evaluator，不打开 6C/6D，不产生仓位或订单。

## 2. Producer handoff 固定边界

KB 交付使用专用 Stage 6B closed-world 对象，而不是 Stage 3D 查询 handoff。它必须固定以下承重身份：

```text
handoff_schema_version = 1.0.0
purpose = invest-system-stage6b-real-https-validation-only-admission
production_base_url
transport_contract.source_commit
transport_contract.snapshot_lock_sha256
authority_eligible = false
credential.scopes = [research:read, export:read]
root_release[Release + Manifest + published Status + complete artifact inventory]
source_releases[complete transitive Release inventory]
source_closure[exact root-to-source relations]
validation_evidence[producer report path + SHA-256]
```

每个 artifact 项必须提供精确 `artifact_id`、`sha256`、`size_bytes`、`content_type`、`item_type`、record schema 身份及已验证响应头证据。允许的公网面只有精确 Release、Manifest、Status 和 Artifact 四类 GET；本次 Token 没有 `evidence:read`，Context Pack 查询接口返回 `403` 是预期权限边界，脚本不得调用或把它当成失败。handoff 文件本身须由交付方另给 SHA-256；IS 不接受 `latest` 或未锁定引用。

## 3. 无网络预检

先在外部临时凭据仍有效时运行默认模式。默认模式会读取并校验 handoff、handoff SHA、base URL 和凭据文件形状，但不会构造 HTTP client、不会发出网络请求，也不会创建 validation root：

```powershell
$python = "E:\Conda\envs\Data_Analysis\python.exe"
$env:PYTHONPATH = (Resolve-Path .\src).Path
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

1. 通过真实 HTTPS 获取 handoff 中每个精确 Release、Manifest 和 Status，逐字段闭合发布状态、PIT、Manifest 身份和完整 artifact inventory；
2. 下载根与全部 Source Release 的所有 artifact，逐项闭合 ID、hash、size、Content-Type 和固定响应头，并从根 Context Pack artifact 复核 Source Release closure；不调用 Context Pack 查询接口；
3. 构造仅含根制品的 `ArtifactConsumptionReceipt` 与包含全部 Source 制品的传递 `ReleaseRetentionClosure`；
4. 对 closure 中每个 Release 发起新的完整 status-history HTTPS 请求；
5. 在同一 admission 窗口签发 validation-only confirmation；
6. 将 Manifest、artifact、原始 status bytes、Observations、confirmation、Manifest、pin 与 seal 原子写入隔离 validation store。

任何 Release 非 `published`、状态过旧、时钟偏差、hash/size/Schema/closure 漂移、Token 权限不足或隔离目录错误，均不得留下 seal。

## 5. 验收记录与收尾

真实运行成功后，另建 Stage 6B 真实 HTTPS 验收记录，至少保存脚本的脱敏输出：handoff SHA、transport lock、`strategy_input_ref`、knowledge cutoff、内容响应哈希、artifact 哈希、fresh status response 哈希、receipt/closure/envelope/confirmation/seal 哈希、隔离事务 generation，以及专项和全仓质量门结果。

验收记录不得保存 Token、凭据文件内容或凭据文件副本。完成后应立即通知 KB 会话撤销短期 Token；Token 撤销不是 historical evaluator 的授权，6C 仍须独立批准。
