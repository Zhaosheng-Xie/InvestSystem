# Stage 0 Git remote 防误推护栏验证

验证日期：`2026-07-31`

结论：`passed`

## 目标

保留 `upstream` 的只读 fetch 能力，同时使通过 remote 名 `upstream` 发起的 push 在联网前确定失败；默认 push 仍指向可写 fork `origin`。

## 当前 clone 配置

```text
upstream fetch = https://github.com/dnaouo/invest_system.git
upstream push  = disabled://upstream-push-prohibited
protocol.disabled.allow = never
remote.pushDefault = origin
origin push = git@github.com:Zhaosheng-Xie/InvestSystem.git
```

对应的 clone-local 配置命令为：

```powershell
git config --local --replace-all protocol.disabled.allow never
git config --local --replace-all remote.upstream.pushurl disabled://upstream-push-prohibited
git config --local --replace-all remote.pushDefault origin
```

## 功能验证

执行：

```powershell
git push --dry-run upstream HEAD
```

实际结果：退出码 `128`，并在联网前返回：

```text
fatal: transport 'disabled' not allowed
```

因此当前 clone 不能误把分支推送到 `upstream`。该配置不能替代 GitHub 权限控制，也不能阻止有意修改本地配置或直接使用真实 URL；新 clone 必须重新应用并验证此护栏。
