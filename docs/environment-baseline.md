# Data_Analysis 环境基线

记录日期：`2026-07-31`

用途：在 InvestSystem 首次安装前保存共享工作站解释器的可比较基线。该环境只用于本地开发；
正式 CI 和可复现验收必须从 InvestSystem 自有 lock 创建隔离环境。

## 安装前摘要

以下结果来自 `E:\Conda\envs\Data_Analysis\python.exe` 的只读检查；本次检查未安装、升级、
降级或卸载任何包。

| 项目 | 安装前结果 |
|---|---|
| Python | `3.12.4` |
| pip | `26.1.1` |
| jsonschema | `4.23.0` |
| mypy | `2.1.0`（共享环境既有版本；不满足本项目 `<2` 范围，不在共享环境中降级） |
| pytest | `9.0.3` |
| rfc3339-validator | `0.1.4` |
| ruff | `0.15.12` |
| setuptools | `72.1.0` |
| wheel | `0.43.0` |
| pip-tools | 未安装；锁脚本只在一次性环境中使用 `7.6.0` |

`pip check` 的安装前结果为：

```text
opencv-python 4.12.0.88 has requirement numpy<2.3.0,>=2; python_version >= "3.9", but you have numpy 1.26.4.
```

这是 InvestSystem 安装前已经存在的 OpenCV/NumPy 冲突。本项目不得擅自修复，也不得把它
归因为 InvestSystem。安装后的验收标准是“不新增冲突”，不是把该既有冲突隐藏或改写为成功。

## 保存可比较快照

原始包清单可能包含工作站细节，保存在已忽略的 `var/environment-baseline/`，不作为依赖来源。
在安装前和安装后分别运行下列命令，并把 `before` 改为对应标签：

```powershell
$label = "before"
$baseline = "var/environment-baseline"
$python = "E:\Conda\envs\Data_Analysis\python.exe"
$conda = "D:\Anaconda3\Scripts\conda.exe"

New-Item -ItemType Directory -Force -Path $baseline | Out-Null
& $conda list --explicit --prefix "E:\Conda\envs\Data_Analysis" |
    Set-Content -Encoding utf8 "$baseline/$label-conda-explicit.txt"
& $python -m pip freeze |
    Set-Content -Encoding utf8 "$baseline/$label-pip-freeze.txt"
& $python -m pip check 2>&1 |
    Set-Content -Encoding utf8 "$baseline/$label-pip-check.txt"
```

安装后还应记录实际新增包列表，并确认没有既有包版本变化。若 `pip check` 出现安装前文本之外
的新问题，应停止 Stage 1 验收并回报，不得自行调整共享环境。

## 当前安装后状态

`registered_without_dependency_changes`（`2026-07-31`）：已生成 runtime/dev hash lock，并以
`python -m pip install -e . --no-deps --no-build-isolation` 注册 InvestSystem。没有把 lock 强装
进共享环境，因为现有 `jsonschema`、`pytest`、`ruff` 已满足项目声明，而 lock 中的较新固定版本
会改变共享包。共享环境既有 `mypy==2.1.0` 超出本项目声明的 `<2` 范围；本项目没有为满足开发
便利而降级这一共享包。正式类型检查证据来自按 `requirements-dev.lock` 安装的隔离环境，其中
固定 `mypy==1.20.2`；共享环境的 mypy 2.1 检查只作为额外的向前兼容检查。

安装前后完整清单位于已忽略的 `var/environment-baseline/`。`pip freeze` 的唯一新增项是本仓库的
editable `invest-system`；没有既有包升级、降级或卸载。安装后的 `pip check` 与安装前相同，仍只
报告上述既有 OpenCV/NumPy 冲突。项目导入解析到本仓库的 `src/invest_system/__init__.py`。
