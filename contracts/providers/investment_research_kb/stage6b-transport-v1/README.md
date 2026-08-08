# InvestmentResearchKB Stage 6B 传输契约快照

此目录固定 KB 提交 `aab36fe229104779b50ec71e2dc37a9fad81d285` 的完整 Stage 6B
公共传输契约。字节只通过该 Git 对象取得；运行时、测试和 CI 均不得读取兄弟仓库。

它是 `../v1/` Stage 2A 核心数据契约快照的只读扩展，不替换或修改原快照。加载时必须同时验证：

- 本目录 `snapshot-lock.json` 的精确文件闭包、大小、Git blob 与 SHA-256；
- KB 自带的 `contract-locks.stage6b-transport.v1.json`；
- 四个 JSON Schema、完整 OpenAPI 目标操作，以及官方合成 fixture；
- `../v1/snapshot-lock.json` 的固定 SHA-256 和完整 Stage 2A 校验。

官方 fixture 只证明离线兼容性。Stage 3B 已使用独立 KB RC 进程、只读凭据和真实 HTTP
完成兼容验收，但该结果仍固定 `authority_eligible=false`，没有形成新 run 的权威状态确认。
远端传输、正式 Context Pack 策略 smoke 和 authority policy 须分别验收；导出包必须另有已认证
传输回执或签名。
