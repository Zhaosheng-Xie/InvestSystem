# Stage 6 最小历史公共数据消费契约 v0.2

状态：`owner_approved_governance_contract / zero_runtime_authority`

批准日期：`2026-08-26`

生效范围：`Stage 6 historical public data requirements and future KB handoff governance only`

本文件完整取代 [v0.1 draft](stage6-minimum-public-data-consumption-contract-draft-v0.1.md)作为后续 KB Schema/backfill/Release 规划的 IS 需求基线。v0.1 原始字节保持不变：

- v0.1 Markdown SHA-256：`205a0c7d403d9fbadd988f2c3081882cb61594a5e4c36a6d4cc6db559e253182`
- v0.1 machine draft SHA-256：`65b9288b7bf2279b061174869181b6e92c85f76db567c6297ff67996e49a1359`

Owner 原始批准指令：

> 批准 S6DATA-01—10，S6DATA-02 固定 H00985，其余按 IS v0.1 推荐口径执行。仅授权形成 v0.2 正式消费契约和治理谱系，不授权真实 handoff、backfill、candidate、coverage、historical run、migration 或 holdout。

## 1. 十项批准决定

- [x] `S6DATA-01`：首版 target universe 固定为 SSE/SZSE 普通人民币 A 股；BSE deferred。ST/*ST、退市、失败、新股和代码变化证券仍保留在基础 universe 与分母中，由 IS 标记 eligibility/support reason。
- [x] `S6DATA-02`：Beta benchmark 固定为中证全指全收益指数 `H00985`，provider=`CSI`，return type=`gross_total_return`，currency=`CNY`。禁止静默替换为 `000985`、`N00985`、`H00300` 或自建当前成分股历史序列。
- [x] `S6DATA-03`：Beta120 使用 decision session 之前恰好 120 个 exchange sessions 的 daily paired PIT total returns，采用带截距 OLS slope；窗口不足、missing、benchmark variance=0 或 PIT 不可证明时 incomplete，不缩短、不插值、不填零。
- [x] `S6DATA-04`：ADV20 使用 decision session 之前恰好 20 个 exchange sessions 的 CNY turnover 算术平均；证明全天停牌才记零，missing/未知状态不得记零。
- [x] `S6DATA-05`：KB 同时发布 marks/calendar/actions/benchmark 等 raw basis 和版本化 ADV20/Beta120；factor 必须携带 basis hashes、formula/window identity 和 available_at，IS 进行确定性抽样重算。
- [x] `S6DATA-06`：`common-reference-factors` 默认并入 `historical-security-market-reference` family；如 KB 工程上保留独立 child Release，必须精确依赖 raw market-reference closure。
- [x] `S6DATA-07`：三个 source families 上方必须发布一个单一 root aggregate Release `historical-stage6-public-input-2019-2025.v1`，以满足一次 run 只能有一个 `strategy_input_ref`。
- [x] `S6DATA-08`：公司行动 P0 范围固定为 Stage 5D 五类：cash dividend、share distribution、split/consolidation、rights/allotment、delisting/cash-out。
- [x] `S6DATA-09`：Release/Manifest/Schema/dependency、exchange calendar/MarketRuleSet intervals 和 security entity lifecycle identity 使用 `100%` 硬门；不能用总体高覆盖率掩盖身份、规则或时间缺口。
- [x] `S6DATA-10`：只增加 artifact Schema/catalog 时 transport protocol 保持现有 v1；只有 API envelope、endpoint、headers 或 auth 语义变化才形成 transport v2 并完整重验。

十项决定只能整组作为 v0.2 使用；不得以部分决定或 v0.1 pending 状态生成另一套正式合同。

## 2. Beta benchmark 精确身份

| 字段 | 批准值 |
|---|---|
| benchmark_id | `H00985` |
| benchmark_name | `中证全指全收益指数` |
| provider | `CSI / China Securities Index` |
| return_type | `gross_total_return` |
| currency | `CNY` |
| frequency | `daily` |
| role | `generic market factor for beta120` |

H00985 只定义 Beta 市场因子，不定义 target universe。即使指数 methodology 含 BSE 或排除 ST/*ST，也不改变 `S6DATA-01` 的 target universe；两者必须分别版本化。

KB 必须先验证 H00985 2019—2025 正式日线的合法可得性、source identity、methodology effective interval、PIT 和完整性。若不可交付，状态保持 blocked；任何 fallback 都需要新 owner 决定和契约版本。

## 3. P0 最小公共数据域

1. Document/Span/Fact/Event/Evidence 与历史 available/revision/conflict lineage；
2. Company/Security 有效期映射、上市/退市、ST/*ST、失败和代码变化；
3. 完整 exchange calendar；
4. effective-dated MarketRuleSet；
5. per-security/session SecuritySessionState；
6. 未复权 OHLC/close、volume、turnover、observed/available/source；
7. Stage 5D 五类公司行动和 total-return raw basis；
8. Stage 4/5/6 承重财务报表/指标及 restatement lineage；
9. PIT 一级行业和流通市值；
10. H00985 daily gross total-return basis；
11. ADV20/Beta120 raw basis 和版本化 factor；
12. declared missing/unrecoverable population。

tick/order-book、BSE、二三级行业、额外风格因子、预计算 20/120-session horizon returns、无关财务扩展指标和 intraday Beta 可后置；命中后置缺口的候选仍必须 unsupported，不能删除。

## 4. Universe 与覆盖硬门

### 数据身份硬门

- root/source Release、Manifest、Schema、dependency closure：`100%` verified；
- 2019—2025 exchange calendar 与 MarketRuleSet interval：`100%` session covered；
- SSE/SZSE 普通 A 股 entity lifecycle：`100%` identified；
- survivor-only forbidden；
- missing、退市、失败、ST/*ST、新股和 code changes 均显式保存。

### 后续 IS candidate 门

- aggregate support `>=80%`；
- 每个 2022—2025 fold/year `>=70%`；
- material category `>=60%`；
- target 与至少 5 个 selected peers 全部支持；
- 真实、可成交、已结束且完整对账交易至少 30 个，每 fold 至少 5 个；
- synthetic completed trade 不计入真实样本。

## 5. Release 架构

### 单一 root（P0）

`historical-stage6-public-input-2019-2025.v1`

root 只有在所有 source families published、producer validation 通过并形成完整 content-addressed closure 后才可发布。

### 三个 source families

1. `historical-public-evidence-2019-2025.v1`
2. `historical-security-market-reference-2019-2025.v1`
3. `historical-public-financials-2019-2025.v1`

security-market-reference 包含 security history、calendar、rules、session states、unadjusted marks、actions、H00985 basis、ADV20/Beta120。factor 若单独构建，只能作为该 family 的内容寻址 child Release。

## 6. Provider-neutral factor 语义

### ADV20

- previous exactly 20 exchange sessions；
- CNY turnover mean；
- decision session excluded；
- proven full-day suspension enters denominator with zero turnover；
- missing/unknown state makes factor incomplete；
- limit sessions use actual turnover；
- basis observations/calendar/state/formula hashes required；
- `available_at=max(basis available_at, factor published_at)`。

### Beta120

- benchmark exact `H00985`；
- previous exactly 120 exchange sessions；
- daily paired PIT one-session total returns；
- OLS slope with intercept；
- decision session excluded；
- no future backward adjustment；
- proven suspension may use carry-forward zero return；
- missing/unknown/short history/zero benchmark variance makes factor incomplete；
- limit sessions use actual legal close return；
- all paired return/basis/methodology hashes required。

## 7. Schema 与 transport

新增 public artifact Schema 从 `1.0.0` 开始：

- historical-public-evidence.v1
- company-security-history.v1
- trading-calendar.v1
- market-rule-set.v1
- security-session-state.v1
- unadjusted-market-daily.v1
- corporate-action.v1
- historical-public-financials.v1
- benchmark-total-return-daily.v1
- common-reference-factor.v1
- historical-stage6-public-input-manifest.v1

现有 transport identity 保持：

- transport source commit：`aab36fe229104779b50ec71e2dc37a9fad81d285`
- IS snapshot lock：`02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169`

KB 新 Schema/catalog/fixtures 必须进入新的 public-contract commit。IS repin 固定发生在 source/root Release candidate 和 producer validation 完成后、真实 Token/handoff 前。transport 语义未变化时不升级 API v2。

## 8. Provider-neutral 最小消费 envelope

一次 run 只接受：

```text
Stage6HistoricalPublicInputContract
  schema_version / contract_id / contract_hash
  strategy_input_ref
  root_release_id / manifest_hash / knowledge_cutoff
  transport_source_commit / historical_contract_commit / snapshot_lock
  source_releases[]
  artifacts[] = role / schema / bytes_hash / size / record_count
  domain_profiles[] = grain / keys / date_range / missing / duplicates / orphans / PIT
  universe_identity
  market_basis_identity
  h00985_benchmark_identity
  adv20_beta120_factor_identity
  financial_identity
  declared_missing_items / unrecoverable_items
  contains_holdout_content=false
  contains_outcome_content=false
  authority_eligible=false
```

不得包含 strategy candidate、support flag、returns summary、NAV/P&L、completed-trade count、coverage 或 champion 结果。

## 9. 下一实施顺序

1. KB 在当前 draft Schema pilot 中把 H00985 和十项批准决定完整物化到 Schema/fixtures/catalog/mapping；
2. 只读检查 H00985 source/licensing/2019—2025 availability，失败不得 fallback；
3. 使用正常/ST/停牌/退市/公司行动/数据不足样本做小型纵向 pilot；
4. 冻结完整 SSE/SZSE security lifecycle universe；
5. backfill market-reference + PIT lineage，再构建 H00985/ADV/Beta；
6. backfill evidence 和 financial PIT lineage；
7. 发布并验证三个 source families；
8. 发布单一 root Release；
9. 冻结 public-contract commit/Schema/catalog/fixtures；
10. IS 在 Token 前 repin；
11. 最后生成 handoff JSON、producer report 和短期只读 Token。

## 10. 授权边界

本批准只形成需求治理契约和 approval lineage。以下全部保持 false：

- 真实 KB handoff、Token 或 artifact 消费；
- KB backfill、Schema/Release 发布授权；
- IS parser、candidate、coverage、peer portfolio；
- historical run、Stage 6C、6D、migration；
- backtest、paper、shadow、live、仓位或订单；
- 2026 holdout 读取或推断。
