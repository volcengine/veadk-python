# YAML 密钥门禁 Hotfix

[English](2026-09-23-yaml-secret-guard.md)

## 元数据

- Change ID：`yaml-secret-guard`
- 创建日期：2026-09-23
- 修订日期：2026-09-23
- 状态：`implemented`
- 相关组件规范：不变更组件契约

## 背景与证据

`examples/piagent_with_mcp/piagent-mcp-agentkit.yaml` 被 Git 跟踪为 AgentKit 启动配置。该文件包含账号相关 Runtime 元数据和具体的 `runtime_apikey` 值。填写后的启动 YAML 属于本地运行产物，不应提交到仓库。

仓库已经通过 `agentkit.yaml` 和 `agentkit*.yaml` 忽略本地 AgentKit 启动配置，但这无法保护此前已经被跟踪的文件。现有密钥扫描也没有提供稳定的仓库本地 YAML 规则，来拒绝敏感 YAML key 的具体值并允许文档占位符。

## 目标

- 删除被跟踪的 PiAgent AgentKit 启动 YAML。
- 更新示例文档，说明如何创建本地忽略配置，保持示例可运行。
- 增加仓库本地 pre-commit YAML 扫描，拒绝具体密钥值。
- 允许安全占位符和 GitHub Actions secret 引用。

## 非目标

- 不重写 Git 历史，也不执行凭据轮换。
- 不改变 AgentKit Runtime 行为、MPA 创建行为或公开 CLI 契约。
- 不大范围重写无关 YAML 示例。

## 需求

| ID | 需求 |
| --- | --- |
| `FR-1` | 含 Runtime ID、Endpoint 和 API key 的已填写 AgentKit 启动 YAML 不得被跟踪。 |
| `FR-2` | YAML 文件中 `password`、`secret`、`token`、`api-key`、`access-key`、`credential` 或 `runtime_apikey` 等敏感 key 对应具体值时，pre-commit 必须失败。 |
| `FR-3` | `.example.yaml` 占位符、环境变量引用和 GitHub Actions `${{ secrets.* }}` 引用必须继续允许。 |
| `FR-4` | 扫描器只报告路径、行号和 key 名，不得打印密钥值。 |

## 方案

删除 `examples/piagent_with_mcp/piagent-mcp-agentkit.yaml`。更新示例 README，要求操作者使用 `veadk agentkit config` 生成本地配置，可按需重命名，并保持在 Git 之外。现有 `.gitignore` 已忽略 `agentkit.yaml` 和 `agentkit*.yaml`。

新增 `scripts/scan_yaml_secrets.py` 并通过本地 pre-commit hook 执行。脚本默认扫描 Git 跟踪的 YAML；在 pre-commit 传入路径时扫描对应 YAML。规则结合 key 名和 value 形态判断，使占位符保持合法，长的具体凭据值失败。

## 涉及文件

- `.pre-commit-config.yaml`
- `scripts/scan_yaml_secrets.py`
- `examples/piagent_with_mcp/README.md`
- `examples/piagent_with_mcp/piagent-mcp-agentkit.yaml`
- `prd-spec/bugfixes/yaml-secret-guard/2026-09-23-yaml-secret-guard.md`
- `prd-spec/bugfixes/yaml-secret-guard/2026-09-23-yaml-secret-guard.zh.md`

## 验证与验收

| 需求 | 验收标准 | 命令 | 结果 |
| --- | --- | --- | --- |
| `FR-1` | 已删除被跟踪启动 YAML，README 指向本地忽略配置生成流程。 | `git status --short` 和 README review | `pass`：YAML 已删除；README 现在说明生成本地配置并保持在 Git 之外。 |
| `FR-2`, `FR-4` | 临时 YAML 中 `runtime_apikey` 配具体值时失败，且不打印具体值。 | `python3 scripts/scan_yaml_secrets.py <tmp-file>` | `pass`：扫描器退出 1，只报告路径/行号/key，输出不包含具体值。 |
| `FR-3` | 占位符和环境变量引用 YAML 通过。 | `python3 scripts/scan_yaml_secrets.py <tmp-file>` | `pass`：占位符和 `${MPA_MODEL_API_KEY}` 引用通过。 |
| 全部 | pre-commit 执行新 YAML hook。 | `uv run --extra dev pre-commit run --all-files` | `pass`：Ruff、Ruff format、gitleaks 和 YAML secret scan 通过。 |

## 风险与待确认问题

- 本修复从当前 Git 状态删除疑似泄露 YAML，但不重写仓库历史。
- 如果该值是真实凭据，凭据轮换属于运维后续动作，不在本代码 hotfix 范围内。

## 评审与交付记录

- 2026-09-23：已实现范围内删除和 YAML 门禁。定向单测、全仓 YAML 扫描和 pre-commit 通过。
