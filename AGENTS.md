# Repository Guidelines

## Project Structure & Module Organization

This is a documentation-first workspace for verifiable A-share trading systems.

- `产业卡点及事件驱动系统/` is active. Its numbered folders cover requirements (`01_需求`), research (`02_研究`), rules (`03_规则与规格`), data (`04_数据`), implementation (`05_实现`), validation (`06_测试与验证`), and operations (`07_运行与复盘`).
- `题材扩散与资金轮动系统/` is a separate research project with the same numbered layout. Do not mix its signals, P&L attribution, or rules into the industrial-event system.
- `原始文档/` contains user-supplied sources. Treat it as an immutable baseline; put derived analysis in the relevant project.
- `归档/` contains historical outputs and screenshots. Use it for traceability, not as the current specification.

Read the root `README.md`, the relevant project `README.md`, and its PRD when one exists before changing downstream artifacts.

## Development & Validation Commands

The Stage 1 engineering skeleton uses Python 3.12, setuptools, hash-locked dependencies, pytest, Ruff, and GitHub Actions. Use these repository-level checks from PowerShell:

```powershell
& "E:\Conda\envs\Data_Analysis\python.exe" -m pytest -q
& "E:\Conda\envs\Data_Analysis\python.exe" -m ruff check .
& "E:\Conda\envs\Data_Analysis\python.exe" -m ruff format --check .
& "E:\Conda\envs\Data_Analysis\python.exe" -m mypy
& "E:\Conda\envs\Data_Analysis\python.exe" -m compileall -q src tests
git diff --check
```

Generate reproducible locks with `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\compile-locks.ps1`. Do not install the full dev lock into the shared environment when that would change existing packages. Document implementation tooling in the relevant project's `05_实现/README.md`.

## Writing Style & Naming Conventions

Write UTF-8 Markdown with one descriptive H1, short sections, and concise lists or tables. Preserve Chinese domain terminology; wrap states, fields, and commands in backticks. Name versioned artifacts clearly, for example `来源登记表_v0.2.md`. Record evidence revisions through versioning or `supersedes` lineage. Only `approved` rules are backtest-ready; `draft`, `hypothesis`, and `placeholder` values are non-production.

## Testing Guidelines

Place validation plans, golden cases, replay results, and bias checks under `06_测试与验证/`. Every rule change should identify evidence, point-in-time assumptions, success and failure cases, and an `ABSTAIN` case. Check internal links and citations manually until automation is added.

## Commit & Pull Request Guidelines

Git history is unavailable, so no existing convention can be inferred. Use short, imperative subjects such as `docs: clarify PIT evidence rules`. Keep commits focused. Pull requests should summarize the decision, list affected folders, link evidence or issues, identify status/version changes, and report validation. Add screenshots for visual-output changes.

## Security & Operational Boundaries

Never commit credentials, broker tokens, or account data. Research agents must not access trading credentials or submit orders. Live outputs require a data snapshot, rule version, test report, and human approval record.

## Cross-Repository Isolation

`InvestmentResearchKB` is an independent provider. This repository may consume only pinned, versioned public contracts and exact Published Release artifacts. Implementation, tests, and CI must not read the sibling repository's SQLite, `raw/`, `staging/`, `published/`, source package, worktree, or temporary directories; do not add sibling-path imports, the KB editable install as a dependency, submodules, symlinks, junctions, shared writable caches, databases, migrations, project runtimes, or CI checkouts.

The approved local-development exception is the workstation Conda environment `E:\Conda\envs\Data_Analysis` with Python 3.12. Treat it only as a shared interpreter, not as the dependency contract: InvestSystem owns its `pyproject.toml`, hash-locked runtime/dev requirements, TOML configuration, cache, database, and runtime directory. Register this project with editable `--no-deps`; never import the KB package from the shared environment. Before and after adding an InvestSystem package, record the environment baseline and run `pip check`; install only exact locked missing packages without changing existing shared packages unless the user separately approves that impact. CI and reproducible validation must build an isolated environment from the InvestSystem lock.

KB credentials must be read-only and limited to the published delivery surface. Preserve `origin` as the writable fork remote, never push to `upstream`, and establish and verify a technical no-push guard on `upstream` during Stage 0 before that stage can complete.

ADR-0001 is approved. The first version permits exactly one `strategy_input_ref` per run and supports both versioned read-only HTTP API and authorized immutable export packages. InvestSystem owns `var/state/invest_system.sqlite3` and the content-addressed cache at `var/cache/kb-releases/`; the cache has a 20 GiB soft limit, and historically referenced artifacts must never be automatically deleted. A withdrawn or unconfirmable Release blocks every new run. Preserved historical material may be used only for explicitly labeled `audit_replay`, never for a new current decision, position, approval, or order.

The current clone's `upstream` push URL uses the prohibited `disabled` transport and `remote.pushDefault=origin`. This is clone-local: verify and reapply the guard in every new clone before development.

Industrial-event and theme-rotation strategies default to zero signal interchange. They may separately pin the same KB Release, read the same provider-neutral immutable content-addressed Release cache, and reuse provider-neutral execution or market-rule libraries, but each must own its input references, consumption receipt/observations, Manifest, states, rules, ledger, attribution, and P&L. Any future cross-strategy feature requires an approved ADR, a versioned contract, and revalidation of every affected strategy.

As of 2026-08-03, Stage 2A/2B passed re-entry review, Stage 3 is owner-deferred rather than completed, and Stage 4 is in `4A rule governance`. The checked-in Stage 4 P0 inventory contains 14 complete requirement IDs but every item remains `draft`. The `stage4_synthetic_research_validation` enum value only expresses a possible future approval scope: it grants no authority without an exact owner approval record, complete inventory evidence, and exact machine bundle. Never reuse the Stage 2B capability for Stage 4, and do not implement PRD `hypothesis`/`TBD` values as defaults. Backtest, paper, shadow, live, positions, and orders remain unauthorized.
