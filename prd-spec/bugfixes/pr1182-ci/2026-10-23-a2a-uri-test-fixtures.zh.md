# 去除 A2A URI 测试中的密码形态夹具

[English](2026-10-23-a2a-uri-test-fixtures.md)

## 范围与证据

- Change ID：`pr1182-ci`
- 创建/修订：2026-10-23
- 状态：实现和历史修复完成；发布已授权，CI 确认待完成。
- PR #1182 提交：`0e71e4aa`；基线：`cb9975df`。

Secret Scan 运行 `39893501693` 以退出码 183 失败。TruffleHog 3.99.4 报告 0 个已验证、3 个未经验证的 URI 发现。GitHub 注解定位到 `tests/cli/test_a2a_center_actions.py` 的两处夹具及 `tests/cli/test_a2a_center_registration.py` 的一处夹具；当前行号分别为 403、484 和 109。这些是刻意无效且含假密码的测试输入，并非已验证凭据。

## 需求与设计

- `FR-1`：保留 API 拒绝及展示过滤带用户信息 URL 的行为。
- `FR-2`：去除密码形态测试字面量，保留既有断言。
- `FR-3`：保持扫描门禁和全部生产行为不变。

将三处含密码输入替换为只有用户名的 URL。保留 `private-value` 或 `secret` 作为用户名，使既有不泄露断言仍然有意义。`_card_url` 和 `_display_url` 已拒绝非空用户名。端点过滤仍须只返回预期安全端点。测试使用 FastAPI TestClient 和模拟云调用，无需真实云端操作。

没有组件契约变化：注册校验、`CON-CARD-VIEW`、`CON-ENDPOINTS`、身份验证、权限、状态、并发和运行时行为不变。参见 [A2A 中心规范](../../../specs/mpa-collaborating-agents/README.zh.md)。UI、生成资源、依赖、扫描规则和用户文档均不受影响。

不采用排除项、编码密码或字符串拆分：去除不必要测试数据，而不是隐藏凭据形态内容。CI 工作流扫描提交历史，因此只追加修复提交仍会包含旧夹具。远端整改需另行从引入问题的提交中去除这些字面量，并保留后续改动、合并结构和作者信息。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| `FR-1`、`FR-2` | `T-1`：修改三处夹具 | `AC-1`：相同响应/过滤断言通过 | `uv run --extra dev pytest tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py -q` | pass：修复前后均为 88 个测试 |
| `FR-2` | `T-2`：对照扫描结果 | `AC-2`：原夹具扫描产生 URI 发现，修复文件不产生 | TruffleHog 3.99.4 filesystem 扫描，禁用验证，仅启用 URI 检测器 | pass：修复前 3 个发现/退出码 183；修复后 0 个发现/退出码 0 |
| `FR-3` | `T-3`：验证/审查 | `AC-3`：仅夹具和双语证据变化 | Ruff、Pyright、`uv run --extra dev pre-commit run --all-files`、`git diff --check` 和人工审查 | 本地 pass |

依次执行基线验证、T-1、T-2、T-3，然后报告剩余历史整改。需要撤销时，在保留后续用户改动的前提下，从 HEAD 恢复两个测试文件。

## 评审、风险与授权

- 用户要求诊断并修复 PR #1182 CI，并于 2026-10-23 以“帮我提交”批准所提历史修复和 PR 更新方案。授权提交、保留作者和合并拓扑的历史改写，以及使用显式 force-with-lease 发布。合并与部署仍不在范围内。
- `review-spec`：方案可行、改动最小、无 API 或契约影响；只有用户名的输入仍覆盖约定的用户信息边界，保留敏感文本断言。密码专用输入覆盖明确替换为用户信息覆盖；生产密码检查不变。
- 既有失败 CI 提供扫描失败基线。现有 API 测试用于确认修复前后行为；新增仅校验字面量格式的测试不能证明产品正确性。
- 这些是 API 路由测试，不在单元测试生成技能声明的适用范围内。无需新增测试用例。
- 本地 macOS 禁用验证的扫描只证明检测器行为，不证明 CI 历史扫描干净。最终 CI 确认需授权历史修复并重新运行。
- 其他排队检查不能报告为通过。实际验证结果记录于下文。

## 验证记录

2026-10-23，验证范围为 `0e71e4aa` 加本次本地修复，分支为 `fix/pr1182-ci`（从 PR 分支创建，并以 `git pull --ff-only` 同步）。

- 目标测试：修复前 pass（88 个，2.62s）、修复后 pass（88 个，1.15s），使用仓库 Python 3.10。两条依赖弃用警告不变。
- 扫描工具：下载 macOS ARM64 的 TruffleHog 3.99.4 至 `/tmp/veadk-pr1182-tools`，根据发布校验和验证 SHA-256；没有全局安装。基线副本存放于仓库外。
- 基线命令：`/tmp/veadk-pr1182-tools/trufflehog filesystem /tmp/veadk-pr1182-fixtures-before --include-detectors=URI --no-verification --no-update --json --fail`；fail/183，恰好 3 个 URI 发现。这一预期失败是负控证据。
- 修复后命令：`/tmp/veadk-pr1182-tools/trufflehog filesystem tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py --include-detectors=URI --no-verification --no-update --json --fail`；pass/0，0 个 URI 发现。
- 全量 pre-commit：pass，包括 Ruff check/format 和两项密钥门禁。`uvx pyright --pythonpath .venv/bin/python tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py`：pass，0 错误、0 警告。
- 差异/双语评审：pass；仅三行夹具变化，断言和生产文件不变。不会因扫描发现推断存在产品缺陷。
- 更广泛的本地 Python/前端/浏览器/云端测试：对此仅夹具变化为 not_applicable。远端既有前后端门禁、发布验证、smoke、许可证和 Python 3.12 检查通过；最后查询时远端 Python 3.10 测试仍在排队。
- 仓库辅助工具 plan 因缺少 Manifest 返回 `onboarding_required`；采用上述原生契约和检查，不引入仓库接入改动。
- 历史整改：本地 pass。以 `--rebase-merges` 变基至已获取的 `upstream/main`（`c662cc8d`），将引入提交 `46f60e12` 修正为 `497f4b65`，保留后续改动、合并拓扑、作者身份和作者日期。文档提交前的新头为 `f44063d4`。本地备份引用保留旧历史以便恢复，不发布该引用。
- 同步：相较旧 PR 头，额外树差异仅为上游 PR #1181 的六文件技能指标修正；没有冲突或对这些文件的手动修改。同步后目标测试加 `tests/skills/test_skill_telemetry.py`：pass，101 个测试，6.92s。
- 历史扫描：pass，0 个发现，命令为 `/tmp/veadk-pr1182-tools/trufflehog git file:///Users/bytedance/Desktop/github-code/veadk-python --since-commit=c662cc8d --branch=fix/pr1182-ci --skip-additional-refs --include-detectors=URI --no-verification --no-update --json --fail`。仅扫描改写后的 PR 历史，不能替代 CI 的完整检测器配置。
- 发布：已授权；预期旧远端头为 `0e71e4aa4888d8b7a79b4a59919d7b7a4289af62`。新远端 CI 结果需发布后确认。
