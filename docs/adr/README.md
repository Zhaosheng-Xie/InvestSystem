# 架构决策记录

本目录保存 InvestSystem 已批准的架构决策。ADR 只冻结职责、接口和工程约束，不证明对应 Adapter、策略或运行能力已经实现。

| ADR | 状态 | 决策 |
|---|---|---|
| [ADR-0001](ADR-0001-kb-investsystem-boundary.md) | `approved` | KB/InvestSystem 边界、单输入、双传输面、自有 SQLite/cache 及撤回审计政策 |
| [ADR-0002](ADR-0002-kb-provider-contract-consumer-profile-boundary.md) | `approved by exact external approval record` | KB 通用 provider contract 与 IS Consumer Profile/Adapter/authority 的所有权边界；[批准记录](../validation/stage6-provider-consumer-boundary-approval-v0.1.md)，零运行权限 |
