# 功能验证 Case 执行报告（dev-loop 步骤 7）

> 执行日期：2026-09-11
> 分支：`feat/mpa-agent-oneclick-provision`
> 被测范围：`veadk/cli/cli_mpa.py`、`veadk/integrations/mpa/*`、`veadk/integrations/ve_faas/ve_faas.py`（deploy_image 扩展）

## 执行汇总

| Case | 需求 | 命令 / 操作 | 结果 | 证据 |
| --- | --- | --- | --- | --- |
| VC-1 | FR-1 | `uv run veadk mpa --help` + `uv run veadk --help` | pass | 见下「VC-1」 |
| VC-2 | FR-2 | `pytest -k missing_required_param_named_error` | pass | test_cli_mpa |
| VC-3 | FR-2/8 | `pytest -k prompts_hidden_for_feishu_secret` | pass | test_cli_mpa |
| VC-4 | FR-3 | `pytest test_ve_faas_deploy_image_key_auth -k with_key_auth` | pass | test_ve_faas_deploy_image_key_auth |
| VC-5 | FR-3/AC-10 | `pytest -k compat_returns_three_tuple` | pass | 兼容守卫，3 元组不变 |
| VC-6 | FR-4 | `pytest -k seed_writes_seven_required_fields` | pass | test_mpa_meta_seed |
| VC-7 | FR-4/11 | `pytest -k seed_private_can_mirror_public` | pass | private==public |
| VC-8 | FR-4 | `pytest -k seed_aborts_when_required_field_unresolved` | pass | 写前中止、无行 |
| VC-9 | FR-4 | `pytest -k idempotent / fills_only_empty` | pass | 非空不覆盖 |
| VC-10 | FR-5/10/11 | `pytest test_mpa_provision_env` | pass | IDENTITY_STARTUP_ENABLED=false + csi-<account_id> |
| VC-11 | FR-6 | `pytest -k verify_fails_*` | pass | readiness/agent-card 失败即 fail |
| VC-12 | FR-6 | `pytest -k verify_passes_when_all_probes_ok` | pass | 三探测全通过 |
| VC-13 | FR-7 | `pytest -k full_flow_orchestration` + dry-run 输出 | pass | agent-card.json + endpoint 出现在输出 |
| VC-14 | FR-8 | `uv run veadk mpa create ... --dry-run` | pass | 见下「VC-14」，密钥掩码 |
| VC-17 | 边界 | 参数缺失/连接前置校验（dry-run 不触发部署/播种） | pass | dry-run 断言 deploy/seed 零调用 |
| VC-15 | FR-9 | `git -C mpa-agent status --porcelain` | pass | 见下「VC-15」，空输出 |
| VC-16 | FR-9 | `uv run pytest tests/cli` | pass | 见「回归」 |
| VC-18 | FR-7 | 真机 Studio A2A 聊天 | deferred | 需真实云部署，见步骤 15 |
| VC-19 | 回归 | 不同 session 不同沙箱 | deferred | 同上（运行时既有行为，代码未改动） |
| VC-20 | 回归 | 飞书拉群 | deferred | 同上 |

单测级：25/25 通过（`test_ve_faas_deploy_image_key_auth` 3 + `test_mpa_meta_seed` 6 + `test_mpa_provision_env` 6 + `test_mpa_verify` 4 + `test_cli_mpa` 6）。

## VC-1（命令注册）

`veadk mpa --help` 列出 `create`；`veadk --help` 同时列出 `mpa` 与既有 `deploy/studio/agentkit/harness/...`，无缺失。

## VC-14（dry-run 密钥掩码）

`--dry-run` 输出运行时 env（掩码后）：`MODEL_AGENT_API_KEY=m***********`、`OPENVIKING_API_KEY=o********`、`PGPASSWORD=p********`；`CLAW_SPACE_ID=csi-2100000001`、`IDENTITY_STARTUP_ENABLED=false`、`MPA_CODEX_WORKER_ENDPOINT_PREFERENCE=public`；并列出 7 个待播种 `mpa_meta` 字段。结尾声明「no cloud or database changes were made」。明文 `pg-secret`/`model-secret`/`ov-secret` 未出现。

## VC-15（mpa-agent 零改动）

`git -C ~/workspace/bytedance/mpa/mpa-agent status --porcelain` 输出为空 —— 本变更未触碰 mpa-agent 仓库。

## 真机 Case（VC-18/19/20）说明

VC-18/19/20 需要一次真实 `veadk mpa create` 部署（真实云凭据 + 可达 PostgreSQL/OpenViking + Studio）。这些属于运行时既有行为（本变更未修改 mpa-agent 的 A2A/沙箱/飞书路径），在步骤 15（门禁+E2E）由用户在真实环境执行并回填脱敏证据。
