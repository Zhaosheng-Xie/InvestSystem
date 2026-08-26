# Stage 6 最小历史公共数据消费契约 v0.2 治理验收

验收日期：`2026-08-26`

结论：`PASS / owner_approved_governance_only / zero_runtime_authority`

## 验收对象

- 正式契约：[stage6-minimum-public-data-consumption-contract-v0.2.md](stage6-minimum-public-data-consumption-contract-v0.2.md)
  - raw SHA-256：`ea82f2e17b99ecaec0cafde7ce5fe0fdb5d6d6855f6348891369cd0b2f02db43`
- 完整机器契约：[stage6-minimum-public-data-consumption-contract-v0.2.0.json](machine/stage6-minimum-public-data-consumption-contract-v0.2.0.json)
  - raw SHA-256：`a7fd65c0d955d4e3610dcbefbaf6a2ec600689986aee0aa80123d167f8c88f6a`
  - canonical contract SHA-256：`4063575384771228433fb8849c0fedd9fac2ba78f704ce5551bb4e23fe8c3557`
- 独立审批记录：[stage6-minimum-public-data-consumption-contract-v0.2.0.approval.json](machine/stage6-minimum-public-data-consumption-contract-v0.2.0.approval.json)
  - raw SHA-256：`ab40ae5392a8c9d22e507c59066d20d84df7cec78ffcc77ff4aac4ce4a616b31`
  - canonical approval SHA-256：`4331087874dcbee885f71b2eb0fef5611dd6d24772a95cce10b3d7514fa603ec`
  - approved decisions SHA-256：`211f046282cb31f046db2fa382af38457810cbb03c20dfd60fb41162c84c5da4`

被取代的 v0.1 draft 继续保持原始字节：

- Markdown SHA-256：`205a0c7d403d9fbadd988f2c3081882cb61594a5e4c36a6d4cc6db559e253182`
- machine draft SHA-256：`65b9288b7bf2279b061174869181b6e92c85f76db567c6297ff67996e49a1359`

## 验收结论

1. `S6DATA-01—10` 在正文、完整机器契约和审批记录中顺序一致并整组批准，不存在部分批准或运行时合并。
2. `S6DATA-02` 精确固定 CSI `H00985` gross total return；`000985`、`N00985`、`H00300` 和静默 fallback 均不可用。
3. SSE/SZSE universe、ADV20、Beta120、五类公司行动、三个 source families + 单一 root、11 个 Schema、100% identity gates、transport v1 和 repin 时点均完整物化。
4. 本轮没有读取 KB、handoff、Token、artifact、收益或 holdout，没有计算 candidate/coverage，也没有持久化运行状态。
5. 正式 handoff、KB backfill、IS parser、candidate、coverage、historical run、migration、Stage 6C/6D、backtest/paper/shadow/live、仓位和订单权限全部保持 false。

## 实测质量门

- v0.1 + v0.2 专项：`14 passed`
- 全仓 pytest：`1149 passed, 4 skipped`
- Ruff check：`PASS`
- Ruff format check：`156 files already formatted`
- mypy：`Success: no issues found in 152 source files`
- compileall：`PASS`
- `git diff --check`：`PASS`

四项 pytest skip 均来自当前 Windows 账户缺少 symlink 权限，和本次治理变更无关。

## 下一门

KB 可把本契约作为 draft Schema/pilot 和后续 backfill 需求基线，但本文件不是 KB 实施授权。IS 继续等待未来 root Release candidate、producer validation 和 public-contract commit；随后才可在真实 Token 前单独执行 repin。任何真实 handoff 或 Stage 6 historical execution 仍需 owner 另行授权。
