# Stage 3A 离线传输消费者验收

> 验收日期：`2026-08-08`
> 结论：`completed`
> 范围：固定公共字节、只读 Client、官方 fixture 离线验证
> 不包含：跨仓 HTTP、tcloud、正式 Context Pack、run authority、策略结论或交易权限

> 后续状态：本记录保留 Stage 3A 当时的固定身份。当前 transport snapshot 已在 Stage 3B
> 重固定到 KB `aab36fe229104779b50ec71e2dc37a9fad81d285`；见
> [Stage 3B 正式跨仓只读 HTTP 验收](stage3b-http-acceptance.md)。

## 1. 结论

InvestSystem 已按 Git 对象固定 KB RC 提交
`2c84277ef463b5dd9a3fda3f2976a30cade53af5` 的完整 Stage 6B 公共传输契约，
并在不读取 KB 工作树、SQLite、`raw/`、`staging/`、`published/`、内部包或运行缓存的
条件下完成消费者实现和离线验收。

Stage 3A 只证明：InvestSystem 能独立验证这组固定公开字节，并能按契约解析只读 HTTP
响应和不可变导出内容集。官方 fixture 是合成契约证据，不是已认证 provider 响应；所有
验证结果都固定 `authority_eligible=false`，不能构造新 run 的权威状态确认。

## 2. 固定身份

| 项目 | 固定值 |
|---|---|
| KB source commit | `2c84277ef463b5dd9a3fda3f2976a30cade53af5` |
| KB source tree | `dba8ed9dbdde7908e7f654ed5fd0216304d6a084` |
| KB contracts tree | `b61293d7ff5038d5ae2c3bd7c3ab6c8c9767fc52` |
| InvestSystem transport snapshot lock SHA-256 | `b9e5657fc88cd635a44f2870a4b3891117612f1669cf6d54a61528a10aaa5f78` |
| Stage 2A base snapshot source | `58ed9c5cb5302e3e719f1696bed83a03c5d6313b` |
| Stage 2A base lock SHA-256 | `4bd79d0e3032a3eeb7824a1b956282e5495dd52a01db81df8bf36b03a2d49092` |
| OpenAPI bytes | `230442` bytes / `4478144dcdae8b156bd75ccc4393f1b0336c3ea2a632f11179bd8150d414ac39` |

扩展快照共有七个 vendor 文件：四个传输 JSON Schema、OpenAPI、官方 transport fixture
和 provider transport lock。加载器同时检查精确文件闭包、大小、SHA-256、Git blob、provider
canonical hash、Schema、四个目标 GET operation、官方正例和撤回错误；任一字节变化都拒绝。

本机 Git 对象复核确认七个 transport 文件逐字节等于 `2c84277`。Stage 2A 的 20 个固定文件中，
19 个在 `58ed9c5` 与 `2c84277` 间 Git blob 不变；唯一变化是说明性
`contracts/fixtures/README.md`。因此本仓保留并继续验证原 Stage 2A 快照，不把 README 更新
解释为核心 Schema/lock/fixture 变更，也不静默重基线。

## 3. 已实现能力

### 3.1 只读 HTTP

- 只允许 `GET` exact Release、Manifest、完整状态历史和 Manifest 已知制品；客户端拒绝
  `latest`，即使 OpenAPI 的部分通用描述仍提到它。
- 默认只允许 HTTPS；本机 HTTP 必须显式打开且 host 必须是 loopback。
- Bearer token 不进入 `repr`、错误信息或输出；无自动重试，响应读取有明确字节上限。
- success/error envelope、operation data Schema、Release ID、状态连续序列、previous hash、
  event self-hash 和 current head 全部重算。
- Release、Manifest 和 status 可组成闭合 bundle；artifact 必须同时匹配 Manifest 期望、
  `Content-Length`、`ETag`、`X-Artifact-*`、Release header 和实际 SHA-256。
- 原始 JSON response bytes 与 `response_sha256` 一并返回，供后续 InvestSystem 自有 CAS 和
  Observation 使用；本阶段不签发 authority。

### 3.2 不可变导出

- 验证 package manifest Schema 和 self-excluding self-hash。
- 要求声明成员与实际成员精确闭合，拒绝绝对路径、反斜杠、`.`/`..`、大小写或 NFC 碰撞、
  ZIP 重复项、目录、加密项、symlink 和其他非普通文件。
- 每个成员重算大小与 SHA-256；metadata 必须是 provider canonical JSON/JSONL 原始字节。
- 重算 Manifest self-hash、完整状态事件链，并闭合 package、Dataset Release、Manifest、
  status head、artifact ID/path/media type/size/hash。
- ZIP 在内存验证完成前不提取；官方 fixture 验收确认没有产生解压目录。
- v1 package 只能证明内容完整性，不能自行证明发布者身份。

## 4. 验证结果

新增 Stage 3 测试覆盖：

- 固定提交、base snapshot 绑定、能力门和单字节篡改；
- 官方 HTTP status success 与 withdrawn artifact `410`；
- token 脱敏、`latest` I/O 前拒绝、状态 head 语义负例；
- Release/Manifest/status 闭合和 artifact header/bytes/Manifest 三方闭合；
- 官方 immutable export 正例、package/member 篡改、缺失成员、路径碰撞、状态链篡改；
- ZIP 无提取验收和 symlink carrier 拒绝。

专项测试：`23 passed`。

最终验证：

- `pytest -q`：`766 passed, 4 skipped`；四项跳过均因当前 Windows 账户不能创建测试用
  symlink/junction，不是失败；
- `ruff check .`：通过；
- `ruff format --check .`：`79 files already formatted`；
- `mypy`：`78 source files` 通过；
- `compileall -q src tests scripts`：通过；
- `git diff --check`：通过。

## 5. Stage 3B—3D 状态

### 3B：等待独立 KB RC 服务

本轮未发现已运行的 KB API 进程，也没有获得外部 base URL、
`INVEST_SYSTEM_KB_BEARER_TOKEN`、`research:read`/`export:read` 凭据或可供核验的精确
Release。KB 当前开发工作树存在未提交变更，因此没有从该工作树启动服务，也没有将其内容
复制为输入。

InvestSystem 已提供 `scripts/validate-kb-stage3-http.py` 作为 operator-run smoke。它只读取
本仓固定快照，通过独立 HTTP 进程获取 exact Release；token 只能来自环境变量。正式 3B
证据必须记录 KB RC 实例身份、精确 Release、只读 scope、响应哈希和结果，不能用 mock 或
同进程 TestClient 代替。

### 3C：未开始

只有 3B 跨仓联调通过后，才以相同固定 Client 连接真实 tcloud。凭据、endpoint 和 authority
policy 都须单独固定；本机通过不会自动授予远端信任。

### 3D：未开始

只有 KB 发布精确 Context Pack Release 后，才进入 provider-neutral 投影与正式策略 smoke。
正确结果可以是 `ABSTAIN`。Stage 3D 不要求 KB 为策略正例定制事实。

## 6. 未授权范围

Stage 3A 不授权 backtest、paper、shadow、live、仓位或订单；不启用受信 authority，不写
InvestSystem SQLite，不写 KB，不产生 `StrategyRunManifest`、`DecisionRecord` 或策略有效性
结论。Stage 4 各规则批准范围不因本验收扩大。
