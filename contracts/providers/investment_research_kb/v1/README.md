# InvestmentResearchKB v1 公共契约快照

本目录是 InvestSystem 对 InvestmentResearchKB 公共发布契约的固定依赖快照，不是
KB 源码副本，也不是 KB 项目安装。

## 固定来源

- 来源仓库：`Zhaosheng-Xie/InvestmentResearchKB`
- 来源提交：`58ed9c5cb5302e3e719f1696bed83a03c5d6313b`
- 选择范围：该提交中受官方 contract lock 保护的全部 14 份 v1 Schema，以及 Stage 2A
  所需的官方 hash vectors、reference consumer fixture、fixture lock 和说明。
- 逐文件 Git blob、大小和 SHA-256：[`snapshot-lock.json`](snapshot-lock.json)

`vendor/` 下的文件是直接从上述提交的 Git object database 提取的原始字节，受
`.gitattributes` 的 `-text` 规则保护。不得格式化、改写换行、重新排序 JSON 或根据
当前 KB 工作树重新生成。升级只能固定新的干净提交、重新核对公共 lock/fixture，并以
显式依赖更新提交更新本目录。

## 使用边界

InvestSystem 的实现和测试只能读取本目录已经固定的公共字节，不能在运行时或 CI 中读取
KB 工作树、Python 包、SQLite、`raw/`、`staging/` 或发布目录。

当前固定基线没有公开、锁定的 immutable export-package Schema/fixture，也没有独立锁定
的 HTTP envelope/OpenAPI Schema。因此 Stage 2A 首个切片只实现公共 Release 内容验证内核
和固定 reference fixture 验证；HTTP 外壳必须严格按已发布只读接口解析，export package
在正式公共契约发布前必须 fail closed 为 `not_supported`，不得复制 KB 内部 API 或采用
KB 当前未提交文件。

KB 的 `irkb-jsonl-v1` 与 InvestSystem 自有 canonical JSON profile 不同：前者要求 NFC，
并允许有限 JSON number。两套 canonicalizer 必须隔离，不能为了通过 provider vector 而
放宽 StrategyRunManifest、DecisionRecord 或 receipt 的无浮点约束。

## Reference fixture 窄投影

本切片只支持官方 Stage 6 fixture 的闭合形状：一个 Context Pack Release 精确引用一个
不晚于自身 `knowledge_cutoff` 的 Evidence Release，且图边必须闭合到已批准、已发布的
Fact、Evidence Link、Span 和 Document。投影以图边 `available_at` 作为 KB 权威 PIT 值，
以关联 Fact 的 `review.reviewed_at` 作为 `verified_at`，并原样带出关联 Document 的
`source_published_at` 和 `first_seen_at`。任何未映射集合、未来审核/发布时间、断链或
Fact/edge 语义冲突都会 fail closed。

公共 `verify_stage6_reference_fixture` 只接受已经通过 `snapshot-lock.json`、官方 contract
lock 和 fixture lock 校验的 catalog，不接受调用方替换 fixture 文档。测试中的篡改样本只
通过私有 failure-injection helper 进入，不是可用的生产输入入口。
