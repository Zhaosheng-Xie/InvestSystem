# InvestmentResearchKB Stage 6B 传输契约快照

此目录固定 KB 提交 `2c84277ef463b5dd9a3fda3f2976a30cade53af5` 的完整 Stage 6B
公共传输契约。字节只通过该 Git 对象取得；运行时、测试和 CI 均不得读取兄弟仓库。

它是 `../v1/` Stage 2A 核心数据契约快照的只读扩展，不替换或修改原快照。加载时必须同时验证：

- 本目录 `snapshot-lock.json` 的精确文件闭包、大小、Git blob 与 SHA-256；
- KB 自带的 `contract-locks.stage6b-transport.v1.json`；
- 四个 JSON Schema、完整 OpenAPI 目标操作，以及官方合成 fixture；
- `../v1/snapshot-lock.json` 的固定 SHA-256 和完整 Stage 2A 校验。

官方 fixture 只证明离线兼容性，不能证明数据来自已认证 KB 服务，也不能形成新 run 的
权威状态确认。HTTP 联调必须使用独立进程和只读凭据；导出包必须另有已认证传输回执或签名。
