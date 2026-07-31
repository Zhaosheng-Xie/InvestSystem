# 依赖管理

InvestSystem 支持 Python `>=3.12,<3.13`。本地开发使用
`E:\Conda\envs\Data_Analysis\python.exe`，但该共享解释器不是依赖契约，也不能成为
InvestSystem 与 InvestmentResearchKB 之间的代码依赖。

## 文件职责

| 文件 | 职责 |
|---|---|
| `pyproject.toml` | 项目元数据、Python 范围、直接 runtime/dev 依赖和构建后端 |
| `requirements.lock` | 带哈希的完整 runtime 依赖锁；由脚本生成，不手改 |
| `requirements-dev.lock` | 带哈希的完整 runtime + dev 依赖锁；由脚本生成，不手改 |
| `requirements-build.in` | 纳入 runtime/dev lock 的构建工具输入；不直接安装进共享环境 |
| `config/default.toml` | 不含凭证的运行配置；不声明 Python 依赖 |

当前直接依赖保持最小化：runtime 只有 `jsonschema>=4.23,<5` 和
`rfc3339-validator>=0.1.4,<1`（保证 JSON Schema 的 `date-time` 不是静默注解），dev 只有
`mypy>=1.17,<2`、`pytest>=9,<10` 和 `ruff>=0.15,<0.16`。增加依赖必须说明用途、许可与安全影响，并确认
不引入 InvestmentResearchKB 包、兄弟目录、editable URL、VCS URL 或本地路径依赖。

## 生成锁文件

从仓库根目录运行：

```powershell
& ".\scripts\compile-locks.ps1"
```

脚本使用指定的 Python 创建一次性虚拟环境，在其中安装固定的 `pip==25.3` 和
`pip-tools==7.6.0`，然后
从 `pyproject.toml` 与 `requirements-build.in` 生成两个带哈希的 lock，最后删除临时环境。
`pip-tools` 只是一次性编译器，不会写入项目 lock；`setuptools` 和 `wheel` 作为无构建隔离
安装所需工具进入 lock。脚本不向 `Data_Analysis` 安装 `pip-tools`。只有有意重新解析全部
版本时才使用：

```powershell
& ".\scripts\compile-locks.ps1" -Upgrade
```

如需使用另一支 Python 3.12 解释器，应显式传入：

```powershell
& ".\scripts\compile-locks.ps1" -PythonPath "C:\path\to\python.exe"
```

生成后应审阅 diff，并验证每个非注释依赖行都有哈希。锁文件属于版本化构建输入，应与
对应的 `pyproject.toml` 变更一起提交。

## 共享环境安装纪律

任何安装前，先按 [环境基线](environment-baseline.md) 保存 `conda list --explicit`、
`pip freeze` 和 `pip check`。随后先预演 dev lock：

```powershell
$python = "E:\Conda\envs\Data_Analysis\python.exe"
& $python -m pip install --dry-run --no-deps --require-hashes -r requirements-dev.lock
```

若预演将升级、降级或卸载任一已安装包，立即停止并报告影响。只有变更清单全部属于“当前
缺失且 lock 已精确固定的包”时，才可执行同一命令去掉 `--dry-run`。项目自身始终只按以下
方式注册，不让 pip 解析依赖：

```powershell
& $python -m pip install -e . --no-deps --no-build-isolation
```

安装后重新保存三份基线并运行本项目测试。`pip check` 可以继续报告安装前已经存在的冲突，
但不得新增冲突。未经用户单独批准，不修复、升级、降级或卸载共享环境中的既有包。

当前共享环境还预先安装了 `mypy==2.1.0`，高于本项目声明的 `<2` 上界。因将其降级会影响
共享环境，本项目不改动该包；正式类型检查使用 dev lock 固定的 `mypy==1.20.2` 在隔离环境
完成，共享环境的 mypy 2.1 结果只作为附加检查，不作为依赖可复现证明。

## 干净环境与 CI

CI 和可复现验证必须创建独立 Python 3.12 环境，不得使用 `Data_Analysis`、KB 工作树或 KB
服务。开发验证的最小安装顺序为：

```powershell
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install -e . --no-deps --no-build-isolation
python -m pip check
python -m mypy
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

只运行应用时使用 `requirements.lock`。CI 不得从未声明的共享包、`PYTHONPATH`、submodule、
符号链接、junction、共享数据库或共享缓存取得能力。
