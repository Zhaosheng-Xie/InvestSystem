# Repository Guidelines

## Project Structure & Module Organization

This is a documentation-first workspace for verifiable A-share trading systems.

- `产业卡点及事件驱动系统/` is active. Its numbered folders cover requirements (`01_需求`), research (`02_研究`), rules (`03_规则与规格`), data (`04_数据`), implementation (`05_实现`), validation (`06_测试与验证`), and operations (`07_运行与复盘`).
- `题材扩散与资金轮动系统/` is a separate research project with the same numbered layout. Do not mix its signals, P&L attribution, or rules into the industrial-event system.
- `原始文档/` contains user-supplied sources. Treat it as an immutable baseline; put derived analysis in the relevant project.
- `归档/` contains historical outputs and screenshots. Use it for traceability, not as the current specification.

Read the root `README.md`, the relevant project `README.md`, and its PRD when one exists before changing downstream artifacts.

## Development & Validation Commands

There is no configured build, package manager, or automated test runner. Use these repository-level checks from PowerShell:

```powershell
rg --files -g "*.md"
rg -n "draft|hypothesis|placeholder|approved" "产业卡点及事件驱动系统" "题材扩散与资金轮动系统"
git diff --check
```

These inventory documentation, audit rule statuses, and find whitespace errors in a valid Git checkout. Document implementation tooling in the relevant project's `05_实现/README.md`.

## Writing Style & Naming Conventions

Write UTF-8 Markdown with one descriptive H1, short sections, and concise lists or tables. Preserve Chinese domain terminology; wrap states, fields, and commands in backticks. Name versioned artifacts clearly, for example `来源登记表_v0.2.md`. Record evidence revisions through versioning or `supersedes` lineage. Only `approved` rules are backtest-ready; `draft`, `hypothesis`, and `placeholder` values are non-production.

## Testing Guidelines

Place validation plans, golden cases, replay results, and bias checks under `06_测试与验证/`. Every rule change should identify evidence, point-in-time assumptions, success and failure cases, and an `ABSTAIN` case. Check internal links and citations manually until automation is added.

## Commit & Pull Request Guidelines

Git history is unavailable, so no existing convention can be inferred. Use short, imperative subjects such as `docs: clarify PIT evidence rules`. Keep commits focused. Pull requests should summarize the decision, list affected folders, link evidence or issues, identify status/version changes, and report validation. Add screenshots for visual-output changes.

## Security & Operational Boundaries

Never commit credentials, broker tokens, or account data. Research agents must not access trading credentials or submit orders. Live outputs require a data snapshot, rule version, test report, and human approval record.
