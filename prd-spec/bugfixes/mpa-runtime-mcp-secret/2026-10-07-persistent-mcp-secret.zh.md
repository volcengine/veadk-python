# MPA Runtime 固定 MCP 密钥

[English](2026-10-07-persistent-mcp-secret.md)

- 变更 ID：`mpa-runtime-mcp-secret`；日期：2026-10-07；状态：implemented。
- 契约：[Runtime 创建](../../../specs/mpa-runtime-provisioning/README.zh.md)、[Studio 创建](../../../specs/studio-mpa-creation/README.zh.md)。

## 背景和范围

旧创建入口及托管 Studio/CLI 创建默认均未注入 `MCP_TOKEN_SECRET`。MPA 因而使用进程内临时密钥，无法在实例替换或跨副本时校验已有 token。用户认可生成一次并保存配置的方案后，明确要求从主分支实现。

范围包括创建配置、持久化、参考模板隔离和密钥脱敏。MPA JWT 格式、Meegle OAuth、前端流程、自动修改存量部署及真实云发布不在本次范围内。

## 需求和设计

- `FR-1`：首次创建向 Runtime 环境变量注入密码学随机的 32 字节密钥，编码为 64 位十六进制字符串。空白值视为未配置。
- `FR-2`：显式非空值优先；否则先沿用目标 Runtime 已有非空值，再考虑生成。不修改调用方传入的环境变量字典。
- `FR-3`：创建、地址/API Key 回填及重试使用同一密钥。托管创建在 CreateRuntime 前，将 `mcp_token_secret` 保存至 Agent 专属 PostgreSQL 的 `mpa_deployment_settings` 表。原子插入或保留已有值处理重试及并发生成；显式值和当前 Runtime 值仅在检查未完成请求摘要之后同步至数据库，避免被拒绝的重试覆盖原密钥。成功及失败均释放连接，数据库错误在云创建前向上传播。
- `FR-4`：参考 Runtime 模板排除 `MCP_TOKEN_SECRET`，新 Agent 获得独立密钥；保留显式 JSON 模板值的配置能力。dry-run 脱敏显式值，正常返回值及非敏感部署登记记录不包含密钥。
- `FR-5`：旧创建入口通过 Runtime 环境变量持久化。创建响应丢失后，按名称发现已有资源并沿用其密钥。已有托管未完成请求如摘要不兼容，继续按原恢复契约阻断。

不变更函数签名、OAuth 权限及凭证访问范围。复用标准库 `secrets`、SQLAlchemy 和 Runtime SDK 对象。PostgreSQL 存储沿用 Agent 数据库的访问边界，Runtime 环境变量仍是验签配置来源。dry-run 无需生成随机值。不新增 UI 或依赖。

## 任务和验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1、FR-2 | T-1：旧入口注入 | AC-1：生成、显式/空值、复用及输入不变 | `tests/integrations/test_mpa_runtime.py` |
| FR-3 | T-2：托管密钥持久化及注入 | AC-2：重试/回填保持密钥，失败释放连接 | 托管数据库及部署测试 |
| FR-4 | T-3：参考隔离和脱敏 | AC-3：排除参考密钥，输出脱敏 | 托管部署及环境变量测试 |
| FR-1–FR-5 | T-4：回归、增量覆盖、检查和审查 | AC-4：增量可执行行覆盖率超过 95%，记录所需检查 | pytest-cov、diff coverage、pre-commit、Pyright |

涉及文件：`mpa_runtime.py`、`mpa_provision.py`、`managed/runtime.py`、`managed/database.py`、对应现有测试，以及上方关联的两组双语契约。

## 审查和验证记录

`review-spec` 不可用，已直接审查职责归属、重试、密钥隔离、数据库清理、错误传播、兼容性及双语一致性，无设计阻断。用户批准：2026-10-07 在本会话明确要求实现，基于此前已认可的生成一次并持久化方案。用户指令授权检查后 commit/push。

2026-10-07 验证记录：分支 `fix/mpa-runtime-mcp-secret`，基线为 `superops/main` 的 `056e8acd0096b6b7b0ee8203ef0f4f11f1efbfcc`。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 实现前回归 | pass | 缺少密钥、复用及托管持久化用例在对应修复前失败；修改密钥的重试被拒绝却覆盖存值的问题，在把写入移到摘要检查之后前也已复现。 |
| 修改的测试文件 | pass | 93 个用例，其中新增 21 个参数化用例。 |
| 覆盖率及部署边界契约 | pass | 113 个用例；将 `git diff --unified=0 superops/main` 与覆盖率 XML 的行命中数据求交，新增可执行行覆盖 23/23（100%）。 |
| 受影响的托管创建回归 | pass | 复跑及同步后的最终覆盖率运行均为 478 个用例通过，主分支基线为 457 个。首次运行中一个未修改的子进程诊断用例暂时失败，复跑通过。 |
| Pre-commit 及空白检查 | pass | `uv run --extra dev pre-commit run --all-files`、`git diff --check`；Ruff 和凭证扫描通过。 |
| 八个修改 Python 文件的 Pyright | fail（基线问题） | 本分支及主分支均为 34 条诊断，文件/消息/规则集合完全一致，无新增诊断。现有 SDK 别名构造参数声明及假客户端可空属性导致失败。 |
| 全仓无关回归 | not_run | 范围为 MPA 创建，不改变共享依赖及运行执行逻辑；已运行受影响的托管创建回归。 |
| 真实云/PostgreSQL/飞书 | not_run | 仅使用离线 SDK/数据库假实现；本任务授权源码修改，未要求云发布。 |

覆盖率采集在主分支和本分支均遇到 SDK/Pydantic 延迟导入错误。在 pytest-cov 启动前预加载未修改的 SDK，可以避免该交互，不替换 SDK，也不改变应用行为。可执行命令与英文版一致：

```bash
uv run --extra dev python - <<'PYTEST'
import agentkit.sdk.skills.types
import pytest
raise SystemExit(pytest.main([
    "tests/integrations/test_mpa_runtime.py",
    "tests/integrations/test_mpa_provision_env.py",
    "tests/integrations/mpa_managed/test_agent_deployment.py",
    "tests/integrations/mpa_managed/test_deployment_database_unit.py",
    "tests/integrations/mpa_managed/test_runtime_deployment_edges.py",
    "-q", "--tb=short",
    "--cov=veadk.integrations.mpa.mpa_runtime",
    "--cov=veadk.integrations.mpa.mpa_provision",
    "--cov=veadk.integrations.mpa.managed.runtime",
    "--cov=veadk.integrations.mpa.managed.database",
    "--cov-report=xml:/tmp/mpa-mcp-secret-coverage.xml",
]))
PYTEST
```

扩大受影响回归时，再预加载 `from pydantic import RootModel`，使用托管测试目录及两个旧入口测试文件，不开启覆盖率。Pyright 通过 `--pythonpath` 指定项目 `.venv/bin/python`；对照基线诊断，不把类型检查宣称为完全通过。

实现审查：显式配置优先；空值正确生成/复用；当前 Runtime 值同步到持久化值；重试保持请求身份；参考模板排除密钥；调用方字典及公开结果安全；数据库引擎在成功及失败时均释放。离线范围内 T-1 至 T-4、AC-1 至 AC-4 已完成。

风险：数据库准备新增写入 Agent 专属配置表的权限需求；调用方显式覆盖密钥属于主动轮换。旧版遗留未完成请求如摘要不兼容，仍须按原恢复流程处理。报告及测试快照不得包含真实凭证。
