# 数据

本目录承接数据字典、PIT 契约、来源授权、快照清单、质量规则和修订血缘。

第一批需要定义的对象：

- SecurityMaster / SecurityStatus
- Document / Evidence / Event
- SupplyChainNode / SupplyChainEdge
- FinancialVersion / EstimateRevision
- MarketRule / FeeSchedule
- DataSnapshot / RunManifest

原始证据只追加不覆盖；修订通过 `supersedes` 建立血缘。

