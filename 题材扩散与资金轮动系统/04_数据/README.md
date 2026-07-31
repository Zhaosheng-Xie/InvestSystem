# 数据

当前状态：`deferred / not_started`。未来优先定义输入契约，并建立逐时点题材词典、成员 `valid_from/valid_to`、来源时间、历史交易规则和首次可成交数据。禁止使用今天的概念成分回填历史。

本目录不承担 KB 的原始采集、raw、staging、SQLite、审核或 Release 发布职责。题材策略可以与产业策略分别引用同一个 KB Published Release，但必须独立验证并保存自己的 `strategy_input_ref`、消费回执和 `StrategyRunManifest`。两套策略可以只读复用 InvestSystem 内部 provider-neutral、内容寻址且不可变的已验证 Release 缓存；不得共享 raw 存储、可变策略缓存、数据库、迁移目录或运行状态。
