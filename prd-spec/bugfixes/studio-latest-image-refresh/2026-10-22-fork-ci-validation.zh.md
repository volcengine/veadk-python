# Fork CI 验证与前端门禁超时修复

[English](2026-10-22-fork-ci-validation.md)

变更 ID：studio-fork-ci-validation。日期：2026-10-22。状态：implemented。

## 证据与范围

PR #1178 的 `86d56c47` 已通过单测、许可证、密钥扫描、依赖策略和后端检查。
共享前端门禁的两个调用方均在 `npm ci --ignore-scripts` 阶段超时。
运行 `39593230026` 和 `39593230579` 明确报告超过 3 分钟上限；汇总门禁因
前端结果为 cancelled 而失败。锁文件含 npmmirror 地址，但该镜像站是否导致
延迟尚未证实。现有发布验证任务已使用 npm 官方源和
`replace-registry-host=always`。

用户要求修复 CI，并先在自己的 fork PR 中完整运行，避免等待上游批准。
范围仅为 CI 配置和契约测试；运行时、UI、镜像选择、依赖和锁文件内容均不变。

## 需求与设计

- FR-1：任一调用方使用共享前端任务时，采用 npm 官方源、替换锁文件仓库域名，
  并设置有界的 10 分钟预算。保留覆盖率、前端测试、并行执行及失败关闭的汇总检查。
- FR-2：fork 中的 PR 执行同一共享门禁与 Studio 打包及冒烟验证。
  仅对 PR 验证移除上游仓库限制。
- FR-3：fork PR 或 push 不启用发布和通知。版本分配、发布及通知仍要求
  上游 `main` 上的手动触发；工作流权限保持 `contents: read`。

受影响的调用方是独立共享工作流和调用它的发布工作流。无需修改组件规范：
应用 API、持久状态、权限、部署和运行时契约不变。增加 CI 预算和扩展验证触发
由工作流自身负责。不引入新密钥、依赖、缓存、重试或发布能力。

## 任务与验收

1. T-1 / AC-1：扩展既有 YAML 契约测试，在修改工作流前证明失败。
   断言仓库配置、10 分钟超时、PR 验证、只读权限及不变的发布守卫（FR-1/2/3）。
2. T-2 / AC-2：修改 `.github/workflows/harness-sidecar-release-gate.yaml` 和
   `.github/workflows/publish-studio-release.yaml`；执行契约测试、变更 Python
   的 Ruff/Pyright、全部 pre-commit、实际前端覆盖率及测试，并将生产构建输出
   到临时目录（FR-1/2）。
3. T-3 / AC-3：创建 fork PR，基线分支固定为上游 `main`，执行全部适用的 PR CI，
   验证发布和通知跳过。如有失败须报告，不能将本地通过等同于云端 CI（FR-2/3）。
4. T-4：fork 验证通过后，将已验证修复带回上游 PR #1178 并提供 fork 证据。
   上游云端批准仍可能需要等待。

## 评审、风险与交付

用户授权：“当前ci又有几个没过 先去修一下”，随后要求先在自己的 fork PR
中完整验证。直接设计评审（无可用 review-spec 技能）：确认两个调用方共享任务，
完整验证不依赖凭据，发布守卫不变，测试覆盖全部变更的 YAML 值，中英文等价。
无阻断项。公共网络缓慢仍可能超过 10 分钟上限，超时仍判失败。
fork 分支保护不能证明上游策略。无可执行生产代码增量，因此增量生产覆盖率
不适用；配置由 YAML 契约检查覆盖。

2026-10-22 本地验证：通过，两个工作流契约及镜像解析/服务共 272 项 Python
测试；两个回归均在修改工作流前失败。仓库固定的 Ruff 0.11.12、使用项目 Python
的 Pyright 及全部 pre-commit 通过。前端 Sidecar 覆盖率通过（22 项测试，行覆盖率
100%、分支覆盖率 94.44%），前端测试通过（1389 项 Node 测试和 118 项 Vitest
测试），生产构建输出到 `/tmp/studio-fork-ci-build-20261022` 并通过。本地 Node
25.2.1 / npm 11.6.2 不同于 CI 固定的 Node 22.17.0 / npm 10，仍需云端验证。
格式化器调整了一个测试文件，重跑全部 pre-commit 后通过。未固定版本的 Ruff
及未指定项目 Python 的 Pyright 调用不适用；上述固定版本及项目环境命令通过，
未添加规则豁免。

fork 云端 CI：通过（AC-3），[fork PR #1](https://github.com/PolarisCzh/veadk-python/pull/1)，
head 为 `7ee50a79a4bbd5d59d2116dd76dc369eb737b9c6`，base 为
`5e5deb6a8a663fed4918f1ab6b2822c93a6c989b`。全部 7 个工作流、14 个验证任务
自动运行成功，无需维护者批准：

- [Unit Tests](https://github.com/PolarisCzh/veadk-python/actions/runs/39716494115)：
  Python 3.10：7633 passed、46 skipped、4 xfailed；Python 3.12：7636 passed、
  43 skipped、4 xfailed；Codex 冒烟成功。跳过和 xfail 用例不计为通过。
- [共享门禁](https://github.com/PolarisCzh/veadk-python/actions/runs/39716494063)：
  后端、前端和汇总全部成功；前端耗时 66 秒。
- [发布验证](https://github.com/PolarisCzh/veadk-python/actions/runs/39716494045)：
  共享前后端及汇总、完整 Studio 打包、模拟用户更新、启动与安装包冒烟验证均成功；
  其前端耗时 58 秒。版本分配、发布和通知均按 FR-3 要求跳过。
- 许可证 `39716494036`、密钥扫描 `39716494022`、依赖策略 `39716494030` 和
  pre-commit `39716494050` 全部成功。

GitHub 曾暂停该 fork 的工作流，尽管 API 显示 Actions 启用；已通过 Actions 页面
重新启用。诊断时短暂调整默认分支，随后恢复为 `main`，原提交保留。
fork main 包含其他工作，因此本次 PR 使用固定为上游 main 的专用基线分支。
已验证的 CI 修复连同本次仅文档证据更新同步到上游 PR #1178；上游运行及批准
属于独立状态，不能由 fork 成功推定。本次未创建云端 MPA 或重新部署应用。
