# Stage 5D 普通证券完整生命周期承重输入物化验收

## 验收结论

状态：`completed_with_scope_limits / lifecycle_evaluator_unauthorized`

形成基线：`f8454ba85064f3a20a623bb63f0df009cc14725a`

输入预注册：[`stage5d-normal-lifecycle-exit-replay-preregistration-v0.1.md`](stage5d-normal-lifecycle-exit-replay-preregistration-v0.1.md)

输入锁：[`normal-lifecycle-exit-input-lock.v0.1.0.json`](../../tests/fixtures/stage5d/normal-lifecycle-exit-input-lock.v0.1.0.json)

本次只物化并冻结 full-EXIT raw Stage 5C case、60-session synthetic calendar、59 条 mark/coverage、validation-horizon exit mandate 和 Stage 5 rule/cost/impact/settlement closure。没有实现或调用 lifecycle evaluator，没有生成 complete replay、completed trade 或正式历史结果。

## 六个承重输入哈希

| 输入 | SHA-256 |
|---|---|
| full-EXIT Stage 5C case | `c7dab6721b8c6299af5d8f4f53fb468ca5da2e302838b3d820d175dd2279334e` |
| 60-session synthetic calendar | `346325ae94464daca7f1c6b87c9105567b0fd82e74c6761edbf33441281bae42` |
| 59-mark observation set | `742fca3fe0aacf4f31c6177ed162b2d03d844f2ab6c6897c6c7991a742387f1d` |
| mark coverage set | `cc78b0c7dd21a504e27fdf5d2e67e783651df51f6e5b1e0dcdbb035b0d96bece` |
| validation-horizon exit mandate | `9db68c853d1fe00e2e53b0e7dfb7f0cdda4fe40bfff2c62ed64de58e3b3ad23c` |
| rule/cost/impact/settlement closure | `c35194068e45b2508a941181cad5153aeb91d7ecef47e503738a71c7a92230a7` |

完整 input-set SHA-256 为 `60cad84334d110e910be897179bf76409f59c59b3bcd45fd733d29cf67829e30`。输入锁 raw SHA-256 为 `ba3b810be7a632ad1b909a7e0e0b942e0de9fb47010e9e3a5c80f77b60c6e8bc`。

## 物化闭环

新增纯 typed input contract `stage5d_lifecycle_inputs.py`，只负责内容寻址和局部失败关闭：

1. 固定 60 个 Monday—Friday synthetic sessions；明确不是 SSE 真实日历或 Published Release。
2. 固定 session `1—59` 的未复权 mark，逐条绑定 session/source/rule、`observed_at < available_at == valuation_at`，且 `executable=false`。
3. 固定完整 coverage set，缺 session、重复 mark、未来 mark 或 hash 漂移均拒绝。
4. 固定 `STAGE6C_VALIDATION_HORIZON_LIQUIDATION` mandate，并精确绑定 Stage 6C v0.2 specification/bundle/approval；明确不验证 Stage 4 `FR-EXIT-001`。
5. 构造新的 full-EXIT raw Stage 5C case：opening 200 股全部可卖、full cost `1613.23`、批准卖出 200 股、零公司行动、普通结算。
6. rule closure 精确绑定 raw case 内的 MarketRuleSet、TradingCalendar、CostSchedule、ImpactCurve 和 SettlementAvailabilityTerms。
7. exit account snapshot 只作未来同一 journal prefix 的 cross-check，不是第二 opening authority。

所有 session、mark、coverage、mandate、closure 和总 input-set hashes 必须非零。输入合同不包含 `evaluate_*` 入口，不进行 I/O、网络访问、状态写入或 KB 内部读取。

## 既有 Stage 5C 输入有效性检查

验收只调用已有 Stage 5C evaluator，证明 materialized raw case 可以产生预注册要求的 full EXIT；这不是新的 lifecycle evaluator：

| 项目 | 实测 |
|---|---:|
| Stage 5C status | `FILLED` |
| side / quantity | `SELL / 200` |
| benchmark / fill | `8 / 7.96` |
| gross notional | `1592` |
| fee + tax | `6.82` |
| cash effect | `1585.18` |
| ending quantity | `0` |

该结果只证明输入自身可执行。Stage 5C result/order/fill hash、67-event lifecycle journal、61-point valuation series、P&L、completed trade 和 complete/audit replay hashes仍全部为 `null`，不得提前解释为业务实现。

## 失败关闭与权限

专项负例覆盖：

- 60-session calendar 缺项；
- mark PIT 时点漂移；
- exit case/mandate/rule closure hash 漂移；
- evaluator、authority、persistence、broker、KB read/write 任一权限扩张；
- 非 200 股全量 EXIT、opening lot/cash/NAV 或公司行动边界漂移。

输入锁明确保持：

- `lifecycle_evaluator_exists=false`；
- `evaluator_implementation_authorized=false`；
- 全部 implementation-derived hashes 为 `null`；
- 无 formal historical run、coverage、peer basket、migration、backtest、paper、shadow、live、仓位或订单权限。

## 验证结果

- 新 input-materialization 专项：`14 passed`
- Stage 5C/5D 与 preregistration/census 相邻：`94 passed`
- 全仓 pytest：`1120 passed, 4 skipped`
- Ruff check：通过
- Ruff format check：通过
- mypy：`147 source files` 通过
- compileall：通过
- `git diff --check`：通过

四个 skip 均为当前 Windows 账户缺少测试 symlink privilege 的既有平台 skip。

## 下一门

下一步必须由 owner 独立批准 lifecycle evaluator。该批准最多允许使用本次精确 input-set 实现匿名合成、纯内存的连续 BUY→full-SELL journal、59 个 mark memo events、61 点 valuation series、十八格 P&L 和 complete/audit replay；不能自动打开真实候选 coverage、Stage 6C、peer basket、migration 或交易权限。
