# 两轮 Code Review 报告（dev-loop 步骤 8-9）

> 日期：2026-09-11 分支：`feat/mpa-agent-oneclick-provision`
> 范围：`veadk/cli/cli_mpa.py`、`veadk/cli/cli.py`、`veadk/integrations/mpa/*`、`veadk/integrations/ve_faas/ve_faas.py`（deploy_image 扩展）、对应 tests。

## 第一轮：显性问题（语法/运行/逻辑/接口/命名）

| 项 | 结论 | 处理 |
| --- | --- | --- |
| ruff 静态检查 | 初次 1 处 `F401`（test_mpa_verify 未用 `pytest`） | 已移除，复检 All checks passed |
| `deploy_image` 返回签名兼容 | 默认三元组不变；key-auth 分支五元组 | AC-10 守卫测试通过 |
| `_create_application` 调用 | 由位置参数改为 `enable_key_auth=` 关键字，避免与 `enable_mcp_session` 串位 | 已确认 |
| APIG 接口路径 | `self.apig_client.apig_client` 为 `APIGApi`，具备 `list_consumers`/`list_consumer_credentials` | SDK 反射确认存在 |
| KeyAuthCredential 字段 | `APIKey`/`Enable`（attribute_map → `api_key`/`enable`） | 读取字段与 SDK 一致 |
| 命令注册 | `cli.py` 仅新增 import + `add_command(mpa)`，未改既有命令 | `veadk --help` 全命令在列 |
| 全部新测试 | 25/25 通过；既有 `tests/cli` 1273 passed/4 skipped | 无回归 |

## 第二轮：隐性问题（边界/资源/规范/覆盖一致性）

| 项 | 结论 | 处理 |
| --- | --- | --- |
| 密钥泄漏面 | env 掩码集 `SECRET_ENV_KEYS`；验证报告仅含 status/label；dry-run 掩码 | 已覆盖 VC-14/verify_report_contains_no_secret |
| `mpa_meta` 写前完整性 | `require_complete` 默认 True，缺字段 `MpaMetaSeedError` 且不写行 | VC-8 通过 |
| 幂等/不覆盖非空 | fill-empty 仅补空字段 | VC-9 通过 |
| A2A agent-card 可达性 | 两阶段部署：拿到 public endpoint 后 `update_function_envs_and_release` 回填 `A2A_PUBLIC_URL`，使 agent-card `url` 指向真实端点（Studio 连接依赖此项） | 已补，运行时 `app/a2a/app.py:115` 读取该值 |
| httpx client 资源释放 | 自建 client 在 finally close；注入 client 不代管 | 已确认 |
| PostgreSQL 驱动 | `psycopg2` 可用；DSN 用 `postgresql+psycopg2` + `sslmode` connect_arg | 已确认可用 |
| 覆盖矩阵一致性 | FR-1..FR-11 均有 Case；无“代码改了但 Case 未覆盖”缺口 | 见执行报告 |
| 真机 Case（VC-18/19/20） | 延后到步骤 15（需真实云/Studio），运行时路径未改动 | 明确标注 deferred |

## 结论

- 无 P0/P1 遗留问题。
- 隐性问题「agent-card url 需指向真实端点」在二轮中发现并修复（两阶段 re-release），否则 Studio 虽能取到 card 但 `url` 会是占位/bind 地址，影响 FR-7 真机连接。
- 待步骤 15 执行门禁（`pre-commit run -a`）与真机 E2E（VC-18/19/20）后交付。
