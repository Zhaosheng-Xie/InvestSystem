# Stage 5 / 5D 公司行动、估值、P&L、完整回放与原子持久化批准记录 v0.1

批准状态：`approved`

批准时间：`2026-08-09T07:52:58.767380Z`

批准人：`repository_owner`

批准来源：当前 Codex task 中 owner 明确回复“Owner 已原子批准 Stage5D 规则包第13节全部48项，仅授权既定 stage5_synthetic_execution_validation”

批准范围：`stage5_synthetic_execution_validation`

## 1. 批准对象

owner 原子批准[《Stage 5 / 5D 公司行动、估值、P&L、完整回放与原子持久化精确规则包 v0.1》](Stage5_5D公司行动估值P&L完整回放与原子持久化精确规则包_v0.1.md)第 13 节全部 48 项。被批准的 owner-review draft 文档 SHA-256 为：

`db09ab438836167e0736aaa459d82fc24c6a22de6868ef7b0952e6546b410f46`

原零权限 draft machine proposal 原始文件 SHA-256 为：

`a17de440604be1bd3bd1d981af3bbf0dd458e0db97251830053b4aaf711f29d2`

原零权限 draft machine proposal canonical bundle SHA-256 为：

`88189304fa4a68262c2ee72a0ca74f3d6235f995ffb4858bece32087ce579d22`

原零权限 draft machine proposal canonical rules SHA-256 为：

`04b693c343fd85e07284bbf1b15eef09fa5b00b9a3dfc01ad82cf4597e3606ac`

四十八项 draft decision objects canonical SHA-256 为：

`38bfe202d8583c531a4ce17a08d5ce3c2d02fe55db9bddf70850de4e0ab7e337`

批准只允许生成独立 approved machine bundle、approval record 和精确的 Stage 5D 匿名合成 `research` 验证 capability。原规则包和 draft proposal 保持原始字节不变，作为不可变批准谱系。本批准不表示 Stage 5D evaluator、Ledger V2、公司行动、mark、NAV、P&L、complete replay、SQLite v4 或 durable persistence 已实现或验收；5D-2 仍必须等待 5D-1 独立验收。

## 2. 四十八项原子批准确认

以下 48 项在同一 exact draft、approved bundle 和本批准记录下整体批准；少于 48 项不形成 partial capability。

### A. 范围、谱系与实施顺序

- [x] `5D-01`：批准本包仍只属于 `stage5_synthetic_execution_validation`、匿名合成 `research`、`validation_only`，当前 draft 为 `zero_runtime_authority`；四十八项只能在同一 exact bundle/document/approval record 中整包原子授权，partial capability/部分实现授权禁止，且任何未来 capability 不得继承 Stage 2B、Stage 4 或 Stage 5B/5C capability。
- [x] `5D-02`：批准精确固定第 2.1 节 Stage 5A bundle/rules/approval/specification/document identities，保留全部既有 Stage 5A 文件原始字节不变；任一身份漂移必须重新批准。
- [x] `5D-03`：批准 Stage 5C 行为基线精确固定为 Git commit `7f64c584c5c7be5e2385a177fab9e5d31e3f665b`，Ledger V2 改动必须提升 schema、绑定实际 code commit 并重验 Stage 5A—5C。
- [x] `5D-04`：批准先完成无 I/O、无 SQLite、无副作用的 `5D-1 pure complete replay`，只有其独立验收通过后才允许开始 `5D-2 SQLite v4 atomic persistence`。
- [x] `5D-05`：批准 5D-2 只能持久化 5D-1 已完整验证的 canonical envelope，不得在 storage 层重算业务、补事件、补余额、补 mark 或补 P&L。
- [x] `5D-06`：批准 5D-1/5D-2 继续保持零 backtest/paper/shadow/live、零真实账户/仓位/订单、零券商连接、零 KB 内部读取或写入，且不证明策略收益、容量或费用模型有效。

### B. Typed PIT 输入与账户范围

- [x] `5D-07`：批准公开入口只接受 raw `Stage5DCompleteReplayCase`，并在同次调用内从 `raw_stage5c_case` 内部重新运行 Stage 5C；caller-supplied Stage 5C result、ledger state、NAV、P&L 或 PASS 不得成为权威输入。
- [x] `5D-08`：批准 `CorporateActionCoverageSet/ElectionSet` 为内容寻址 typed 输入，逐证券声明覆盖区间、完整性及第 4 节各状态自己的经济与知识时点；每个 action 固定 `NOT_APPLICABLE/MANDATORY/CHOICE_REQUIRED`，choice-required 绑定 made/available/deadline、显式 default available、deadline/default rule、source、revision/supersedes 和 canonical hash，空集合或缺字段不得代表未知。
- [x] `5D-09`：批准 `UnadjustedMarkObservationSet` 保存逐证券 observed/available 时点、未复权合法价格、session/rule/source identities、覆盖区间和完整性，禁止未来、零价或复权价回填。
- [x] `5D-10`：批准 `SyntheticExternalCashFlowSet` 按 strategy/account 隔离并保存 flow id、方向、CNY 金额、economic/knowledge/cash-state times、recognized time、合成授权来源和 hash，只在第 5.4.2 节 exact cash posting 时改变余额；交易、股息与公司行动现金不得冒充 external flow。
- [x] `5D-11`：批准 `OpeningLotAttributionSet` 覆盖账户内每个 opening lot 的 benchmark principal、slippage、fee、tax、corporate-action basis 和 full-cost identity；分量缺失时不得声称 complete P&L，也不得使用未知补差桶。
- [x] `5D-12`：批准一个 5D case 只允许一个产业 strategy/account，但支持 account-wide multi-security positions；所有非零 lot 必须有 opening attribution 和公司行动覆盖，每个 valuation point 只对该 prefix 中 `actual_quantity>0` 的证券要求 mark coverage，已清仓证券不强制期末 mark，并按 security/lot 规范排序。

### C. Ledger V2、成本与结算

- [x] `5D-13`：批准 Ledger V2 posting 显式分离 `asset_unit` 与 `security_id` dimension；现金为 `CNY/null`，逐证券成本/应收应付为 `CNY/security`，数量为 `SHARE/security`，禁止跨证券成本净额补差。
- [x] `5D-14`：批准第 5.3 节完整 priority map：`5/10/20/30/40/50/51/60/70/80/90/95/100—106` 与 `effective_at → priority → ledger_event_id`，任何变更需新版本和批准。
- [x] `5D-15`：批准 lot cost components 固定为 benchmark principal、execution slippage、fees、taxes、corporate-action basis adjustment，且每个 lot 的 components sum 必须等于 full cost。
- [x] `5D-16`：批准买入 fee/tax 资本化进入逐证券 `SECURITY_COST` 和 lot components，卖出 fee/tax 从应收扣除；事件类型和归因保持分离，禁止重复扣减。
- [x] `5D-17`：批准卖出继续按 `acquired_at → lot_id` FIFO，并按确定性比例移除每个 cost component；最终处置精确耗尽尾差，不能自动 plug 或改写旧 fill。
- [x] `5D-18`：批准新增显式 `EXTERNAL_CAPITAL`、corporate-action/other receivable 和 payable 账户；external flow、公司行动应收应付、trade clearing 与 P&L 不得混账。
- [x] `5D-19`：批准第 5.4 节 `Ledger V2 exact event semantic map v1` 为 closed-world allowlist：每个 Stage 5C/5D event/phase 的账户、security scope、借贷 signed formula、lot 五分量、clearing 归零和 recognized time 必须 exact；每事件后逐证券闭合 lot/full-cost/`SECURITY_COST`、现金、预留、应收应付、数量与 sellable，任何额外/缺失/不平为 `RECONCILIATION_BLOCKED` 且零自动补差。
- [x] `5D-20`：批准 Stage 5C replay 入口继续拒绝全部 5D 事件，Stage 5D 使用独立完整 policy；首版对任何非空 settlement `special_exception_id` 继续 fail-closed，未获批准的例外不得绕过 MarketRuleSet。

### D. 五类公司行动

- [x] `5D-21`：批准所有公司行动使用 typed complete coverage、原始未复权价格/gross cash 条款及第 4 节每状态独立 PIT 时间；资格由 action terms/MarketRuleSet 从 entitlement prefix 派生，不能用 sellable 代替 entitlement；choice/default phase 分别使用第 4 节 `election_recognized_at/default_recognized_at` 的 max 公式，所有 accepted events 严格匹配第 5.4.2 节，未知分支在首事件前失败关闭。
- [x] `5D-22`：批准 `CASH_DIVIDEND` 严格执行第 5.4.2 节 recognize/fee-tax/paid/available exact phases：gross 应收与收益控制、typed fee/tax 各自独立归因但同 phase compound、paid 后才转 settled cash、cash available 后才可用，未来状态不得提前进入 NAV。
- [x] `5D-23`：批准 `SHARE_DISTRIBUTION` 严格执行第 5.4.2 节 recognized/unsettled→delivered/unsellable→sellable phases，以 append-only lineage 增加 quantity 且五成本分量和同证券总 full cost 不变；不同证券分配或成本规则缺失时失败关闭，不自动设零成本。
- [x] `5D-24`：批准 `SPLIT_OR_CONSOLIDATION` 严格执行第 5.4.2 节各 quantity bucket 的 exact rational delta 与 lot effect，五成本分量绝对额/总成本不变；fractional cash-in-lieu 复用 gross cash+fractional basis disposal 子语义，禁止静默截断、净额冒充 gross 或舍入补差。
- [x] `5D-25`：批准 `RIGHTS_OR_ALLOTMENT` 严格执行第 5.4.2 节 `DECLINE/EXERCISE/MANDATORY`；前两者必须有截止前作出且 PIT 可得的 choice 或条款显式 default，exercise phase 不早于相应 election/default recognized time，并形成 reserve、逐证券 cost/payable、unsettled lot、paid→delivered→sellable，subscription fee/tax 资本化且不得伪造成市场 order/fill。
- [x] `5D-26`：批准 `DELISTING_OR_CASH_OUT` 严格执行第 5.4.2 节；强制退出为 `MANDATORY`，自愿 `ACCEPT_CASH/DECLINE` 为 `CHOICE_REQUIRED` 且 phase 不早于有效选择或显式 default 可得时点，再依次形成 gross receivable、clearing 归零、lot 五成本移除、realized、paid 与 cash-available；未知 gross/basis/时点或选择不得清仓。
- [x] `5D-27`：批准公司行动分数股、不同证券分配、cash-in-lieu、权利交易和自愿退出的每个未覆盖分支均独立失败关闭；缺选择不得推断为 `DECLINE`，截止后只允许条款显式、版本化、内容寻址且已可得的 default，不能使用最常见市场惯例。
- [x] `5D-28`：批准公司行动事件与 lot effect 必须绑定 action/election/deadline/source/rule/revision hashes；同 prefix 只允许一个 active election，同字节幂等、异字节冲突，只有条款允许且截止前作出的 revision 可在其可得后用 reversal + replacement 生效，不得覆盖历史、回写 phase、复写 fill 或改变其他 strategy/account ledger。
- [x] `5D-29`：批准复权价格仅可作为独立研究交叉检查，永远不得成为 Stage 5 fill、mark、lot cost、公司行动现金流或缺失条款替代值。

### E. Mark、stale 与 NAV

- [x] `5D-30`：批准每个 valuation point 只对该 prefix 中 `actual_quantity>0` 的证券选择 `observed_at/available_at <= valuation_at` 的最后合法未复权正价格，并要求 exact security/session/rule/source scope；零持仓 market value 为零且无需 mark，同刻不同内容为歧义失败。
- [x] `5D-31`：批准只有有效 session state 证明持续停牌时才能沿用 stale mark，并保存 stale flag、起点、时长和来源；stale mark 永不代表 executable price。
- [x] `5D-32`：批准 mark 先按唯一优先级分流：scope/coverage/completeness/source/PIT 缺失或冲突为 `PRECHECK_BLOCKED`，ledger 不平为 `RECONCILIATION_BLOCKED`；只有完整 coverage 中持仓证券无历史合法 observation 且 ledger 已对账时，全账户 valuation/P&L 才固定为 `ABSTAIN + incomplete_pnl`，禁止 partial NAV 和任何价格回填。
- [x] `5D-33`：批准 `MARK_TO_MARKET` 为 typed append-only memo event，不修改现金、数量或历史成本；mark 更正只用 reversal/replacement，所有余额变动事件仍须双分录。
- [x] `5D-34`：批准第 7 节 closed-world account-to-NAV 映射：三类 cash、trade/公司行动/other receivable-payable 各一次，加逐证券 market value；`SECURITY_COST` 由 market value 替代，clearing/control/P&L/`EXTERNAL_CAPITAL` 不直接进 NAV，caller snapshot 只能交叉核对。
- [x] `5D-35`：批准 beginning/ending valuation 使用同一规范 journal 的两个 inclusive prefix 并覆盖账户全部证券；本期唯一为 `(beginning_at,ending_at]`，未来 scheduled event 不进入较早 prefix，任一点 `actual_quantity>0` 的证券缺合法 mark 即不得声称完整账户 NAV/P&L，已清仓证券不强制 ending mark。

### F. 二维 P&L 与全账户对账

- [x] `5D-36`：批准第 8.2 节恰好十八格 closed-world `3 × 6` matrix 及十三个 allowed signed formulas、五个 `FORBIDDEN=0` 规则；每个 as-of 物化完整十八格，cell 是唯一可加总事实，source lineage 只通过 contribution 加总。
- [x] `5D-37`：批准 row/column/grand-total 都只是 derived disclosure；只有十八个 cells 可加总，marginal 或 total 再加回、forbidden cell 非零、contribution 与 cell 不等均为 `RECONCILIATION_BLOCKED`。
- [x] `5D-38`：批准第 8.1—8.2 节逐 driver 符号与公式：普通卖出 gross=`TB+TS`，公司行动 basis disposal gross=`CAD`，五个 disposed/remaining cost components各只进 price/slippage/fee/tax 一格，`corporate_action_basis_adjustment` 只进 price，corporate-action cash 始终为 gross，任何 gross/net 互换或双计禁止。
- [x] `5D-39`：批准 period 严格为两个 inclusive prefix 的 `(beginning_at,ending_at]` 差：`period_cell=C_end-C_begin`，ending-at 事件纳入、beginning-at 事件 period contribution 为零，并与 `ending_equity-beginning_equity-net_external_cash_inflow` 精确相等；external capital 不进入 P&L。
- [x] `5D-40`：批准先逐证券闭合第 8.2 节十八格、source contributions、cost/NAV/equity，再精确汇总到账户；只有完整 mark coverage 中缺合法 observation 且 ledger 已对账时为 `ABSTAIN/incomplete`，任一 formula/gross/basis/cash/equity/cell/matrix 不平固定为 `RECONCILIATION_BLOCKED`，不得降级或产生 complete P&L authority。

### G. Complete replay 与 audit replay

- [x] `5D-41`：批准 complete replay 只完整到 inclusive `ending_at <= injected_clock`；内部重算 Stage 5C，并按第 4/5.4 节只接受 `effective_at<=ending_at` 且对应状态/选择/default 自身知识已可得的事件，恰好 ending-at 纳入，未来 settlement/action/election/default/payment/cash-available/delivery/sellable 仅留 plan，不能泄漏到 current state。
- [x] `5D-42`：批准 replay envelope 使用第 9 节显式 included/excluded allowlist，绑定全部承重规则、输入、action/election/deadline/default/revision、事件、valuation、P&L、代码、配置、Decimal 和 clock，排除运行、路径、端点与 rowid 噪声。
- [x] `5D-43`：批准 `audit_replay` 只用原输入/规则/代码/horizon 精确复现并固定 `audit_only=true`、`authority_eligible=false`；无论成功失败均严格内存零写，不得调用 5D-2、创建/更新 SQLite 或形成新的 current decision、target、approval、position、fill、NAV/P&L authority 或 head。

### H. 同库 SQLite v4

- [x] `5D-44`：批准 5D-2 仅对 InvestSystem `var/state/invest_system.sqlite3` 执行原子 `user_version 3 → 4`，新增且仅新增 `stage5_artifacts/stage5_run_aggregates/stage5_run_artifacts/stage5_ledger_events/stage5_run_ledger_events/stage5_account_generations` 六表；一次原子组完整包含 Manifest、Stage 4/5 canonical roles、projected/accepted events、marks、valuation、P&L、replay seal/root/members 和 generation/head，原样保留 v3，禁止第二数据库和 KB 表复制。
- [x] `5D-45`：批准同 replay/key 同 canonical bytes 幂等、同 identity 不同内容冲突；semantic config 与 SQLite path/WAL/synchronous/timeout 等 operational config 严格分离，单连接固定 `WAL + synchronous=FULL + foreign keys + bounded busy_timeout + BEGIN IMMEDIATE`，以唯一约束和 expected prior head CAS 防止 last-write-wins。
- [x] `5D-46`：批准 5D-2 写前和六表 read-back 均使用 approved typed codec 解码、canonical 重编码并复验 schema/role/hash/order/reference/head/semantic invariants；只有 `pnl_complete=true`、已对账、无资金/持仓变化的完整业务 `BLOCKED/ABSTAIN` 可 sealed 且不推进状态，mark-missing `ABSTAIN/incomplete_pnl` 与技术、hash、并发、reconciliation、SQLite/中断/read-back 失败全部零写。

### I. Golden、回归与排除项

- [x] `5D-47`：批准第 11 节为最低验收门，特别包括每个 exact event/phase、同刻 compound、十八格数值、closed-world NAV、mark outcome precedence、清仓 mark scope、election/default/revision 的 made/available/deadline/recognized PIT、beginning/inside/ending 边界，以及 5D-2 分流/失败注入、确定性、migration、并发和全仓回归；任一门失败不得标记 Stage 5D 完成。
- [x] `5D-48`：批准本包不授权真实数据、真实账户、真实订单、broker、backtest/paper/shadow/live、策略收益结论、Stage 6 或跨产业/题材共享 ledger/P&L；所有未逐项定义的公司行动、mark、成本、P&L 和 persistence 行为默认失败关闭。

## 3. 权限结论

本批准只允许在 exact approved bundle、approval record 和 fail-closed verifier 下开始 `5D-1 pure complete replay` 的匿名合成 `research` 实现。只有 5D-1 独立验收通过后，才可按同一批准规则进入 5D-2 实现；当前批准谱系本身不实现或执行 SQLite 写入。

本批准明确不授权：

- backtest、paper、shadow、live 或 Stage 6；
- 真实数据、KB current-status authority、真实账户、资产、仓位、订单、券商连接或资金部署；
- 读取或写入 KB SQLite、`raw/`、`staging/`、工作树或内部包；
- 策略收益、容量、费用模型有效性或任何资金使用结论；
- 题材策略复用产业策略的信号、Manifest、组合、账本、成交或 P&L。

批准后的 evaluator、Ledger V2、公司行动、mark/NAV/P&L、complete replay 与 SQLite v4 仍须依次形成实现、专项测试、golden、独立验收和明确状态记录；任何未通过项保持失败关闭。
