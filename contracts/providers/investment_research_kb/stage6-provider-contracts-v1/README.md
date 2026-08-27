# InvestmentResearchKB Stage 6 通用提供方契约快照

本目录固定 KB `main@4352c10c6c639e25d4c190dfc9ec58ee9e76aa86` 中合并的
provider-neutral draft contract。它只用于离线 Adapter 契约验证，不是 KB 源码、
Published Release、真实数据或 transport repin。

## 精确来源

- provider contract 原提交：`50604ea46e14580be976e1cf46c349a2d3088740`
- KB 普通 merge commit：`4352c10c6c639e25d4c190dfc9ec58ee9e76aa86`
- IS ADR-0002/Consumer Profile 批准提交：`eb702559511083d2d0d603725be50997e0c22bbe`
- 获取方式：仅通过 KB Git object 原始 blob；不读取 KB 工作树文件。
- 文件闭包：1 个 supporting defs、15 个 active provider draft Schema、provider catalog、
  benchmark/factor registry 和官方 synthetic fixture，共 19 个文件。

逐文件 Git blob、size 和 SHA-256 固定在 [`snapshot-lock.json`](snapshot-lock.json)。
`vendor/` 受 `.gitattributes -text` 保护，不得格式化或改写换行。

## 边界

- loader 和测试只读取本目录；不得发现或访问兄弟 KB 仓库。
- `strategy-input-ref.v1` 继续由既有 v1 snapshot 兼容，本快照不复制 legacy 文件。
- 五个旧耦合 draft 只在 provider catalog 中登记为 `superseded_never_published`，不进入
  本快照 active 文件闭包。
- H00985 身份可以离线选择，但其完整历史、PIT 和再分发许可仍未证明。
- factor fixture 只交付 raw-basis hash，没有 raw basis records；可以验证定义和闭包，
  不能把 fixture 冒充数值重算证据。
- transport 继续是固定的 v1；本目录不改变现有 Stage 6B transport snapshot。
- 不授权网络、真实 Release、Token、handoff、candidate、coverage、historical run、
  holdout、migration 或交易。

显式依赖更新使用：

```powershell
& "E:\Conda\envs\Data_Analysis\python.exe" scripts/vendor-kb-stage6-provider-contracts.py `
  --kb-repository "D:\Python\Python_Project\InvestmentResearchKB" `
  --destination "contracts\providers\investment_research_kb\stage6-provider-contracts-v1"
```

脚本要求目标目录不存在；未来升级必须使用新的版本化目录，不能覆盖历史快照。
