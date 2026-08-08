# Stage 4 / 4A-4 市场预期、估值与退出合成研究验收

> 验收日期：`2026-08-08`
>
> 验收状态：`completed_with_scope_limits`
>
> 验收分支：`codex/stage4a4`
>
> 授权范围：`stage4_synthetic_research_validation`
>
> 不包含：完整 Stage 4 编排、backtest、paper、shadow、live、仓位、组合、成交、P&L 或订单

## 1. 验收结论

owner 已批准《Stage 4 / 4A-4 市场预期、估值与退出规则包 v0.1》第 10 节全部 24 项。仓库已保留原 draft 不变，新增精确 approved machine bundle、approval record、typed capability verifier、局部纯 evaluator 和测试证据。

本轮在匿名、provider-neutral 合成输入上完成 `FR-GATE-004`、`FR-GATE-005` 与 `FR-EXIT-001`。它可以评估公开经济预期、市场定价区间、合成研究估值与 Gate 4，以及 evidence/risk/time/value 退出判断；所有结果都是 validation label，不是可交易决定。

14 项 Stage 4 P0 inventory 现在全部 `approved`，但这只是完整能力的必要条件。四个局部 capability 不会自动合并；4B 完整编排和合成验收合同仍为零权限待批准草案，所以仓库当前没有完整 Stage 4 engine capability。

## 2. 精确规则与批准身份

| 项目 | SHA-256 |
|---|---|
| 4A-4 owner-review 规格文件 | `7f2f1238ff5d9bae1c7a96b212b87dd56a04ac8a9013715e46d2b6cc9d864a62` |
| 原 draft canonical bundle | `2d6ebeafeb93fd0d799ab31c1a93e88639e7979fc6416179a18158a9a4450055` |
| 原 draft canonical rules | `5692fae5ab76c233d2f3d3ff3c0e23002062a179426de843c46d5439c09d543c` |
| owner 批准记录文件 | `c793c776a309b418f9ec7de760a26899ce609b3541d71e957ad56cdbfa0d0724` |
| approved canonical bundle | `6ad34d6534b646eb0eb4fcab73c9da13e0738af0d3ae0d296143a48129ee1762` |
| approved canonical rules | `d1d2e03d78f0a78c63e073916da87f9177bb2e7151bd1d4d9ec959cd865545e2` |
| approval record canonical hash | `8b75674537a9b8939cd259e2efb5a46752282714f19b23e181d9509ae09b919e` |
| 更新后的 P0 inventory canonical hash | `fc07b10bb17d91b3447504fe7f5b2e346023fd98bb14da991e1a1dd85381bf53` |

approved 4A-4 bundle 还精确绑定 4A-1、4A-2 与 4A-3 的 approved bundle hash；任一 bundle、rules、approval record、scope 或权限字段漂移都不能构造 typed capability。

## 3. 已实现行为

- `FR-GATE-004`：PIT expectation snapshot、经济口径可比性、E4 前市场上下文、市场隐含事件价值区间，以及 `unexpected/partially_priced/fully_priced/unknown` 的确定性映射；区间接触或不可比较时不选有利端点，而是 `ABSTAIN`。
- `FR-GATE-005`：基础业务和 E4 有限期增量 FCF 分开估值、组件唯一归属、防重复计价、四情景区间一致性、显式合成价格与摩擦；Gate 4 使用基础/下行情景下界并精确执行 `0.15`、`2.00` 和最多 `120` 交易日 proof window。
- `FR-EXIT-001`：六类 evidence trigger、注册风险预算等号退出、120 日等号时间退出、价值等号退出、E5/E6 新证据重新承保、无持仓 `NOT_APPLICABLE` 及 confirmed 优先于 unknown。
- 所有版本化预期、市场上下文、估值、合成价格、proof plan 和 holding snapshot 均使用排除 self-hash 的规范内容哈希；篡改、未来回填、跨规则 holding、跨估值 holding、真实价格声明或 KB 内部读取均失败关闭。
- 退出输入自身无效只阻断退出判断，不追溯改写同一次 Gate 3—4；Gate 和退出都不生成订单、权重、approver 或执行权限。

## 4. 测试与工程检查

| 检查 | 结果 |
|---|---|
| Stage 4 专项 pytest | `161 passed` |
| 全仓 pytest | `802 passed, 4 skipped` |
| Ruff lint | `passed` |
| Ruff format check | `passed` |
| mypy | `passed / 80 source files` |
| compileall | `passed` |
| `git diff --check` | `passed` |

四个 skip 都来自当前 Windows 账户不能创建 symlink/junction 的既有平台限制，不是 4A-4 业务逻辑跳过。本轮未安装、升级、降级或卸载任何包。

## 5. 4B 零权限交接

[4B 完整引擎集成与合成验收规则包](../../产业卡点及事件驱动系统/03_规则与规格/Stage4_4B完整引擎集成与合成验收规则包_v0.1.md)已形成，但没有获得本次批准。其状态和身份如下：

| 项目 | 值 |
|---|---|
| 文字规格文件 SHA-256 | `d5c1ab50d76ea5d9444adcc92da24313b5ce5b51080c2e9258a5484a9417ca8d` |
| draft canonical bundle SHA-256 | `2b845a6c4df0dc7e28779b0117409cd39b390cc304fb7bc54f9062c44697b44c` |
| draft canonical rules SHA-256 | `1c7e8cb5acd89187e527a11be8f50baf77307b29561bf3a7fdc95bb32f3e1df9` |
| owner approval items | `16 pending / 0 approved` |
| allowed run modes | `[]` |
| complete capability | `false` |

只有 owner 另行批准 4B 第 9 节全部 16 项后，才能创建 approved 4B artifacts 并实现完整编排器。该未来批准即使完成，也仍只允许匿名合成 research validation。
