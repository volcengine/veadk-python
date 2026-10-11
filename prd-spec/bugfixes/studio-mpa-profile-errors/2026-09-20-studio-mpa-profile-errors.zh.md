# Studio MPA Profile 错误处理修复

[English](2026-09-20-studio-mpa-profile-errors.md)

## 元数据

- Change ID：`studio-mpa-profile-errors`
- 创建日期：2026-09-20
- 修订日期：2026-09-20
- 状态：`implemented`
- 相关组件规范：[Studio MPA Control Plane](../../../specs/studio-mpa-control-plane/README.zh.md)、[MPA Runtime Control](../../../specs/mpa-runtime-control/README.zh.md)

## 背景与证据

本地 Studio Profile 验证暴露了三个独立问题：

- Studio 未带 `--dev` 启动且没有配置 Studio TOS 存储时，`GET /web/mpa/agent-operations?status=active` 返回 `503 mpa_operation_service_unavailable`。
- 当前选中的 Runtime `r-yev5cmzp4wzn6n5iodgd` 位于 `cn-beijing`，状态为 `Ready`，但仍运行较旧的 MPA 镜像 version 14。它通过 `/web/runtime-proxy/.../api/v1/sessions` 调用原生 Session API 时返回 `401 {"detail":"X-Jwt-Token header is required"}`。
- 同一 Runtime 的 Profile status endpoint 返回普通 `404 {"detail":"Not Found"}`，此前会显示为原始 safe error，而不是现有的 `profile_not_found`/orphan Runtime 状态。
- 当前 MPA Runtime 镜像可能只通过 A2A virtual app 暴露 Agent 元数据。例如 Runtime `r-yeuujrrcowb21078p9jh` 的 `/web/agent-info/a2a-default` 返回 `200`，但 `/web/agent-info/default` 返回 `404`，此前会表现为“无法加载 Agent 详情”。

第一个问题属于本地启动模式问题。后两个问题属于旧 Runtime 镜像兼容性与展示问题；这些镜像早于 AgentKit `Authorization` 适配和 Profile status 契约。

## 目标

- 本地 Studio 使用无需生产 TOS 的配置启动时，应可启用 MPA operation service。
- 保持 Runtime 鉴权 fail-closed；不得伪造或转发 `X-Jwt-Token`。
- 对旧 Runtime 镜像展示可操作、本地化的错误，并保留 Profile 页面中的 Runtime 身份和能力状态。
- Runtime 契约不兼容时，禁用 Profile 写入、Session 配置和 Debug 控件。

## 非目标

- 不执行云端 Runtime mutation、镜像发布或自动 Runtime 升级。
- 不改变 Runtime 鉴权契约：当前 AgentKit-mode Runtime 镜像继续使用 `Authorization`。
- 不提交本地浏览器证据或其他测试产物。

## 需求

| ID | 需求 |
| --- | --- |
| `FR-1` | 本地 `veadk studio --dev --vite` 在未配置 Studio TOS 时必须启用进程内 MPA operation repository，使 active operation recovery 返回 `200`。 |
| `FR-2` | 上游 `401` 且 detail 要求 `X-Jwt-Token` 时，必须归类为 `runtime_legacy_auth_unsupported`，不能表现为泛化的 session-list 或 runtime request failure。 |
| `FR-3` | `GET /web/mpa/agents/{mpaInstanceId}/view` 对旧版或缺失 Profile endpoint 的 Runtime 必须返回正常 `MpaAgentView`、Runtime 元数据和 safe error，不能让整个页面失败。 |
| `FR-4` | Profile 页面必须展示本地化说明，并在 Runtime 镜像不兼容时禁用 Profile 写入、Session 配置和 Debug 控件。 |
| `FR-5` | Runtime-backed Agent 详情在 `default` Agent 元数据缺失时，必须回退读取 A2A virtual app 元数据。 |

## 方案

`frontend/server/mpa/runtime_client.py` 现在会对上游字符串错误进行归一：

- `X-Jwt-Token header is required` 归类为 `runtime_legacy_auth_unsupported`。
- `GET .../profile-status` 返回的普通 404 文本归类为 `profile_not_found`。

`frontend/server/mpa/routes.py` 将 `runtime_legacy_auth_unsupported` 作为 Profile view 的安全错误处理。响应保留 `bindingStatus=bound` 与 Runtime 元数据，不返回 Profile 状态，并设置 `canWrite=false`、`canDebug=false`。

`frontend/src/adk/client.ts` 对 Session list failure 使用结构化错误解析。MPA Runtime session 列表遇到旧版 `X-Jwt-Token` 401 时，会展示本地化升级提示，并保留原始 detail 用于诊断。

`frontend/src/ui/AgentWorkspace.tsx` 将 `safeError.code` 映射为本地化 MPA 控制面文案，并使用 `capabilities.canWrite` 判断 Profile apply 按钮是否可用。

`frontend/src/adk/client.ts` 现在会在 `/web/agent-info/{app}` 返回 404 时回退请求 `/web/agent-info/a2a-default`。非 404、鉴权错误和服务端错误仍继续向上抛出。

本地验证使用：

```bash
APP_ENV=development VEADK_MPA_TEST_SCENARIOS=0 uv run veadk studio --dev --host 127.0.0.1 --port 18179 --vite --no-open
VEADK_API_TARGET=http://127.0.0.1:18179 npm --prefix frontend run dev -- --host 127.0.0.1 --port 5179
```

## 涉及文件

- `frontend/server/mpa/runtime_client.py`
- `frontend/server/mpa/routes.py`
- `frontend/src/adk/client.ts`
- `frontend/src/ui/AgentWorkspace.tsx`
- `frontend/src/i18n/resources/en-US/adk.json`
- `frontend/src/i18n/resources/zh-CN/adk.json`
- `frontend/src/i18n/resources/en-US/ui.json`
- `frontend/src/i18n/resources/zh-CN/ui.json`
- `tests/frontend/server/mpa/test_runtime_profile_routes.py`
- `frontend/tests/runSseAbort.test.mjs`
- `frontend/tests/agentWorkspace.test.mjs`

## 验证

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 后端 Profile routes | pass | `uv run --extra dev pytest tests/frontend/server/mpa/test_runtime_profile_routes.py -q` 返回 28 passed。 |
| 前端源码契约测试 | pass | `npm --prefix frontend test -- agentWorkspace.test.mjs runSseAbort.test.mjs` 返回 1244 passed，因为该脚本仍会执行仓库前端测试集合。 |
| i18n 一致性 | pass | `npm --prefix frontend run check:i18n` 对 2 个 locale、21 个 namespace 检查通过。 |
| 本地 operation recovery endpoint | pass | 带 `--dev` 启动后，经 Vite 访问 `GET /web/mpa/agent-operations?status=active` 返回 `200 {"operations":[]}`。 |
| 旧 Runtime Profile view | pass | `GET /web/mpa/agents/r-yev5cmzp4wzn6n5iodgd/view?...` 返回 `200`、Runtime 元数据、`bindingStatus=orphan_runtime`、`canDebug=false` 和 `safeError.code=profile_not_found`。 |
| 旧 Runtime session list | expected limited | `GET /web/runtime-proxy/r-yev5cmzp4wzn6n5iodgd/api/v1/sessions?...` 仍返回上游 `401 X-Jwt-Token header is required`；客户端现在会将其展示为旧 Runtime 镜像兼容性提示。 |
| A2A Agent 元数据回退 | pass | `GET /web/runtime-proxy/r-yeuujrrcowb21078p9jh/web/agent-info/default?...` 返回 `404`，而 `/web/agent-info/a2a-default?...` 返回 `200`；`getAgentInfo` 现在会重试 A2A 路径，前端回归由 `runSseAbort.test.mjs` 覆盖。 |

## 风险与后续

当前选中的 Runtime version 14 无法仅通过 Studio 侧修复到完全兼容。若要完整验证 Session 列表和聊天链路，需要将该 Runtime 镜像更新到当前 MPA AgentKit 兼容版本，例如已验证过的 version 62 路径。
