# Stage 3D 真实公网 Context Pack 验收

> 验收日期：`2026-08-11`
> 结论：`completed_with_scope_limits / Stage 3 closed by owner on 2026-08-12`
> 分支：`codex/stage3d-context-pack`
> 实现提交：`81c5101a0c7e43a9159edbac6a78df323f38da97`
> 权限结论：`authority_eligible=false`

## 1. 验收结论

InvestSystem 使用仓库自有只读 HTTP Client、固定 transport snapshot 和
`scripts/validate-kb-stage3d-context-pack.py`，直接访问真实公网
`https://82.157.112.120`。Context Pack Release、Evidence Release、两份 Manifest、
完整 Status/hash chain、两份主制品和两份公开 Schema 均通过正式 HTTPS 获取并闭合；
两个 Release 的当前状态均为 `published`。

Context Pack 查询端点返回的 `data` 与下载制品 JSON 完全相同。IS 独立验证了
`context-pack.v1`、`schema_version=1.0.0`、Context Pack 自哈希、产业图哈希、
source Release 身份、Document/Span/Fact/CandidateEvent/EvidenceLink/EvidenceRef、
node/edge/source/company mapping 的引用闭包及承重 PIT 时点。未知字段由固定 Schema
失败关闭；transport snapshot 无需重固定。

provider-neutral 映射、四制品消费回执、三类只读 Observation 和 validation-only
`StrategyRunManifest` 均由 IS 自行构造。正式策略规则尚未获准消费真实输入，且材料
显式保留 7 个 missing items 和不可恢复字段，因此策略入口安全返回 `ABSTAIN`，没有
虚构正向证据。

## 2. 固定身份

| 项目 | 验收值 |
|---|---|
| Base URL | `https://82.157.112.120` |
| Handoff SHA-256 | `7602c54fd1cfdfc96d8949b49fbc86c5636428cdc688c27ed66f5fd6928a1243` |
| Transport source commit | `aab36fe229104779b50ec71e2dc37a9fad81d285` |
| Transport snapshot lock | `02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169` |
| Context Pack Release | `rel_fc8be9b554aa414ca8ad5a14aaec69d9` |
| Context Pack ID | `ctx_cb6b42a9e8acb4b5f81773a2d95e50f4` |
| Context Pack semantic hash | `3a21920b0c14dafb3771a32210c9eda611894576fcba47f86325f59b2e9f0e35` |
| Source graph hash | `dc9edc02e771bcf1d3ec2bc66c008b5c86ec5a6ecbe2c7197c23099525fb15cb` |
| Evidence Release | `rel_02f1148031c04036a5f7d5cda9807fb5` |
| Knowledge cutoff | `2026-07-28T14:13:31.303929Z` |

`strategy_input_ref` 为：

```json
{
  "dataset_release_id": "rel_fc8be9b554aa414ca8ad5a14aaec69d9",
  "knowledge_cutoff": "2026-07-28T14:13:31.303929Z",
  "manifest_hash": {
    "algorithm": "sha256",
    "value": "1a6759f2563d9708ec1973ab5f701c059e870d2ba12d1c84b11d1578b1cdaf92"
  },
  "release_manifest_schema_version": "1.0.0",
  "schema_version": "1.0.0"
}
```

## 3. 制品和响应头闭合

| Release | Artifact | SHA-256 | Size |
|---|---|---|---:|
| Context Pack | `ctx_cb6b42a9e8acb4b5f81773a2d95e50f4` | `b42e3b7b290868a26d3c2e7194e6cf6aa08295c7e2f7d832812ec2081a1e01b8` | 21745 |
| Context Pack | `ctx_cb6b42a9e8acb4b5f81773a2d95e50f4-record-schema` | `ae5965fe5edfb4bf4053a6471653e2bd003c1ae55ece180820f651118e2fbe17` | 10667 |
| Evidence | `optical-evidence-bundle-v1` | `540ba608404bf550672d9168166c2f71b6888aaca7e4e15e20b8bd385b547fd6` | 16085 |
| Evidence | `optical-evidence-bundle-v1-record-schema` | `ab410a1d25b93c9fece1fe266f9a02622ffbe0ff02632932734c1c29f5692ee7` | 9530 |

四个下载响应均验证了 `Content-Type`、`Content-Length`、`ETag`、
`X-Artifact-ID`、`X-Artifact-SHA256` 和 `X-Dataset-Release-ID`。Context Pack 和
Evidence Schema 的物理字节哈希分别如上；规范 JSON 语义哈希分别固定为
`a6432ef884861eae5652faa59b0593841e1f1e68d67b7b615510271820d16e68` 和
`660a2c3ce25a3bb4d541c8a532c9ff062a702f40d495753031ce87feae9b0658`。

## 4. 本次实测响应 SHA-256

动态 HTTP meta 会改变响应字节，因此以下值只记录本次最终实测，不作为 Stage 3B/3C
响应字节的等值要求：

| 响应 | SHA-256 |
|---|---|
| Context Release | `9bf3a4297f1cacb131d9c811a53ea516d1f65fc3d17c5d849066348571a375f2` |
| Context Manifest | `917eafd3b7e66dcd4382e4f46746f1f4939890e5b2c73f69d3a85ca5bc61b8e8` |
| Context Status | `cf107b5e6e26be371797e0b57ade20c3e9d8bc331f436e49e6d0bb6383175829` |
| Context query | `9a9fc6211588206eda3d283e8d0e7ea1178bf24c40cf9d6b32e0dc0710449041` |
| Evidence Release | `8c32f9726c15882d6b8c817c65b6092f293b8edc64e4cdf30422989cf6b7656d` |
| Evidence Manifest | `bb0f778446f66b6b330977293d302c7957542565c9fbf7583a3108affeb68850` |
| Evidence Status | `0ce64fae2740e635ae786ee473cd3eeb66c03e2471fc7421a140ec1eaf364c35` |

## 5. IS 投影与策略 smoke

| 输出 | 值 |
|---|---|
| ArtifactConsumptionReceipt hash | `5d7a5f3e76f95aab419f63a3efe3fb77661fbaa716b1d1de75d2787b0103c421` |
| Provider-neutral input hash | `9df74234ec2e82a8990d37cbf438119cbc7424452c52ed71fda6f463ef75093a` |
| StrategyRunManifest hash | `80c346e95ad3ed9e2d5fee57633d6c677d1c796299da116e865e3c38d143aee5` |
| Strategy smoke hash | `afbfa22cc25c92fe97816baeaeb87b2c7bc8276a1217f30dd0b1c577fa30327a` |
| Outcome | `ABSTAIN` |
| Admission | `unconfirmed` |

闭包包含 3 个 Document、4 个 Span、3 个 Fact、1 个 CandidateEvent、4 个
EvidenceLink、6 个 node、3 个 edge、9 个 EvidenceRef 和 3 个 company mapping。
Evidence Manifest 另外包含 6 个非本次 Context Pack 承重制品；验证器显式记录该数量，
不把它们冒充为已下载或已消费。7 个 missing items、counterexamples、conflicts 和
unrecoverable fields 均按原内容保留；本次实际 counterexample 数为 0。

## 6. 验证结果

- Stage 3D Context Pack/HTTP/transport 专项：`18 passed`。
- 全仓 `pytest -q`：`951 passed, 4 skipped`；4 项均因当前 Windows 账户不能创建
  测试用 symlink/junction，不是失败。
- `ruff check .`：通过。
- `ruff format --check .`：`109 files already formatted`。
- `mypy`：`107 source files` 通过。
- `compileall -q src tests`：通过。
- `git diff --check`：通过。

## 7. 安全和剩余边界

- Bearer Token 只由执行进程读取 owner 指定的绝对路径；未进入命令参数、输出、仓库、
  测试报告、Git diff 或提交。
- 没有使用 mock、`TestClient`、KB SQLite、KB Python 包、KB 源码、KB 本地
  `published` 目录或同进程服务；没有修改 KB。
- `authority_eligible=false`，未签发 `RunReleaseStatusConfirmation`，没有写 CAS、
  Observation、SQLite 或任何业务运行状态。
- 没有授权 backtest、paper、shadow、live、真实账户/仓位/订单、券商连接或资金部署。
- Stage 3D 的真实传输、provider-neutral 映射和 validation-only smoke 已关闭。owner 于
  `2026-08-12` 批准按该 scope-limited 边界正式关闭 Stage 3，不再以 run authority 为尾项。
- 若以后需要正式准入，Stage 6 必须独立实现并验收 historical-validation admission、已认证
  状态证据、run-scoped confirmation 和 IS 自有原子持久化；Stage 7 当前 shadow/paper
  admission 另行过门。两者都不能从本次 validation-only 对象推导权限或回开 Stage 3。

本轮短期 Token 已无继续用途；KB 会话应立即撤销该 Token。
