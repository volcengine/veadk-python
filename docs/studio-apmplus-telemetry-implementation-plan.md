# Studio APMPlus 前端埋点实现方案

## 背景

Studio 通过 APMPlus Client / WebPro 统计部署实例、登录使用情况和 Agent 部署结果。当前
方案上报以下自定义事件：

- `studio_instance_loaded`：Studio 前端成功读取 `/web/ui-config` 后上报。
- `studio_user_authenticated`：用户身份解析完成，且 `/web/access` 返回用户身份后上报。
- `studio_agent_deploy_succeeded`：用户确认部署后，Agent Runtime 部署成功时上报。
- `studio_agent_deploy_failed`：用户确认部署后，Agent Runtime 部署失败时上报。
- `studio_sandbox_create_succeeded`：用户确认创建 Sandbox 后，Sandbox Session 创建成功时上报。
- `studio_sandbox_create_failed`：用户确认创建 Sandbox 后，Sandbox Session 创建失败时上报。

`veadk studio deploy` 会把 Studio 部署到 VeFaaS，并注入部署 ID、部署者 ID、用户池 ID、
区域、项目等环境变量。Studio 运行时通过 `/web/ui-config` 把部署元信息下发给前端；
通过 `/web/access` 返回当前登录用户 ID 和角色。

## 目标

- 统计被访问过的 Studio 实例数量。
- 统计访问过 Studio 的用户池数量。
- 统计登录使用 Studio 的用户数量。
- 统计 Studio 页面加载量和登录使用量。
- 统计 Agent Runtime 成功部署数和部署失败数。
- 统计 Sandbox 创建成功数和创建失败数。
- APMPlus 配置缺失或上报失败时，不影响 Studio 正常使用。

## 非目标

- 不把前端埋点当作严格的 CLI 成功部署审计。纯前端事件只能统计“部署后至少被打开过”
  的 Studio 实例。
- 不在本方案中实现 APMPlus 控制台看板或 SQL 查询。
- 不采集 prompt、对话内容、生成代码、环境变量值、构建日志等内容型数据。
- 不采集 `VOLCENGINE_SECRET_KEY`、`VOLCENGINE_SESSION_TOKEN`、`OAUTH2_CLIENT_SECRET`、
  Runtime API key 或其他密钥。

## 指标口径

| 指标 | 推荐事件 | 理想聚合方式 | 说明 |
| --- | --- | --- | --- |
| 被访问过的 Studio 实例数 | `studio_instance_loaded` | `count(distinct studio_deploy_id)` | 同一个实例被多人访问仍只算一个实例。 |
| 用户池数 | `studio_instance_loaded` 或 `studio_user_authenticated` | `count(distinct user_pool_id)` | 访问维度用实例加载事件；登录维度用用户认证事件。 |
| 登录用户数 | `studio_user_authenticated` | `count(distinct user_id)` | 登录成功并拿到后端权限身份后上报。 |
| Studio 页面加载量 | `studio_instance_loaded` | `count(*)` | 页面每次加载可计一次。 |
| 某个实例的登录用户数 | `studio_user_authenticated` | `count(distinct user_id) group by studio_deploy_id` | 观察单个 Studio 的覆盖范围。 |
| 成功部署 Agent 数 | `studio_agent_deploy_succeeded` | `count(*)` | 一次成功部署或更新对应一条成功事件。 |
| 部署失败次数 | `studio_agent_deploy_failed` | `count(*)` | 不包含用户取消和只打开确认弹窗的情况。 |
| 有结果的部署操作数 | `studio_agent_deploy_succeeded` + `studio_agent_deploy_failed` | 两个事件上报量相加 | 若看板不支持跨事件相加，则拆成两个卡片展示。 |
| Sandbox 创建成功数 | `studio_sandbox_create_succeeded` | `count(*)` | 一次成功创建 Sandbox Session 对应一条成功事件。 |
| Sandbox 创建失败数 | `studio_sandbox_create_failed` | `count(*)` | 不包含用户取消和只打开确认弹窗的情况。 |
| 有结果的 Sandbox 创建操作数 | `studio_sandbox_create_succeeded` + `studio_sandbox_create_failed` | 两个事件上报量相加 | 若看板不支持跨事件相加，则拆成两个卡片展示。 |

当前 WebPro 自定义分析看板如果只能选择 `COUNT` 等普通聚合，则字段级
`count(distinct <field>)` 可能需要用明细导出、查询能力或额外离线分析完成；前端埋点仍按
可去重的维度字段上报。

## 事件设计

### `studio_instance_loaded`

触发时机：

- 前端成功读取 `/web/ui-config`。
- APMPlus SDK 已完成初始化。
- 每次页面加载最多上报一次。

用途：

- 统计被访问过的 Studio 实例数。
- 统计用户池覆盖范围。
- 统计 Studio 页面加载量。

字段：

| 字段 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `studio_deploy_id` | string | `stddep_...` | 每次 `veadk studio deploy` 生成并注入的唯一 ID。 |
| `user_pool_id` | string | `up-...` | Studio 绑定的用户池 ID。 |
| `vefaas_application_id` | string | `app-id` | VeFaaS Application ID。 |
| `vefaas_function_id` | string | `func-id` | VeFaaS Function ID。 |
| `studio_region` | string | `cn-beijing` | Studio 部署区域。 |
| `studio_project` | string | `default` | VeFaaS 项目。 |
| `studio_version` | string | `bundled` | Studio 版本。 |
| `agents_source` | string | `cloud` | `/web/ui-config` 返回的 Agent 来源。 |

`studio_instance_loaded` 不包含 `user_id`、`user_role`、`user_source`，避免实例加载事件和用户
登录事件的语义混在一起。

### `studio_user_authenticated`

触发时机：

- `resolveIdentity()` 返回 `status === "authenticated"`。
- `/web/access` 返回非空 `telemetry.userId`。
- 当前页面生命周期内对同一个 `studio_deploy_id + user_id + user_role` 最多上报一次。

用途：

- 统计不同用户池下的登录使用人数。
- 统计某个 Studio 实例被多少用户使用。
- 统计不同角色的登录使用量。

字段：

| 字段 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `studio_deploy_id` | string | `stddep_...` | 关联 Studio 实例。 |
| `user_pool_id` | string | `up-...` | Studio 绑定的用户池 ID。 |
| `vefaas_application_id` | string | `app-id` | VeFaaS Application ID。 |
| `vefaas_function_id` | string | `func-id` | VeFaaS Function ID。 |
| `studio_region` | string | `cn-beijing` | Studio 部署区域。 |
| `studio_project` | string | `default` | VeFaaS 项目。 |
| `studio_version` | string | `bundled` | Studio 版本。 |
| `user_id` | string | `123456` | 后端根据 Studio 权限身份解析出的登录用户 ID。 |
| `user_role` | string | `admin` | `/web/access` 返回的 Studio 角色。 |
| `user_source` | string | `sso` | 区分 SSO 和本地用户名模式。 |

### `studio_agent_deploy_succeeded`

触发时机：

- 用户在确认弹窗里确认部署或更新。
- `ProjectPreview.performDeployment()` 调用 `onDeploy()` 成功返回 `DeployResult`。

用途：

- 统计成功部署或更新的 Agent Runtime 数量。
- 按创建入口、区域、网络类型拆分部署结果。

字段：

| 字段 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `studio_deploy_id` | string | `stddep_...` | 关联 Studio 实例。 |
| `user_pool_id` | string | `up-...` | Studio 绑定的用户池 ID。 |
| `vefaas_application_id` | string | `app-id` | VeFaaS Application ID。 |
| `vefaas_function_id` | string | `func-id` | VeFaaS Function ID。 |
| `studio_region` | string | `cn-beijing` | Studio 部署区域。 |
| `studio_project` | string | `default` | VeFaaS 项目。 |
| `studio_version` | string | `bundled` | Studio 版本。 |
| `user_id` | string | `123456` | 当前登录用户 ID。 |
| `user_role` | string | `admin` | 当前登录用户的 Studio 角色。 |
| `user_source` | string | `sso` | 区分 SSO 和本地用户名模式。 |
| `deploy_source` | string | `custom_create` | 创建入口：`custom_create`、`intelligent_create`、`code_package` 或 `unknown`。 |
| `deploy_action` | string | `create` | `create` 表示新建 Runtime，`update` 表示更新已有 Runtime。 |
| `deploy_region` | string | `cn-beijing` | Agent Runtime 部署区域。 |
| `runtime_network_type` | string | `public` | Runtime 网络类型：`public`、`private` 或 `both`。 |
| `feishu_enabled` | string | `false` | 是否启用飞书 Channel。 |
| `runtime_id` | string | `runtime-id` | 成功部署后返回的 Runtime ID。 |

看板主口径：

```text
事件 = studio_agent_deploy_succeeded
指标 = 上报量 / COUNT
```

### `studio_agent_deploy_failed`

触发时机：

- 用户在确认弹窗里确认部署或更新。
- `ProjectPreview.performDeployment()` 调用 `onDeploy()` 后抛出非取消异常。

用途：

- 统计部署失败次数。
- 按创建入口、区域、网络类型和失败阶段拆分失败分布。

字段：

| 字段 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `studio_deploy_id` | string | `stddep_...` | 关联 Studio 实例。 |
| `user_pool_id` | string | `up-...` | Studio 绑定的用户池 ID。 |
| `vefaas_application_id` | string | `app-id` | VeFaaS Application ID。 |
| `vefaas_function_id` | string | `func-id` | VeFaaS Function ID。 |
| `studio_region` | string | `cn-beijing` | Studio 部署区域。 |
| `studio_project` | string | `default` | VeFaaS 项目。 |
| `studio_version` | string | `bundled` | Studio 版本。 |
| `user_id` | string | `123456` | 当前登录用户 ID。 |
| `user_role` | string | `admin` | 当前登录用户的 Studio 角色。 |
| `user_source` | string | `sso` | 区分 SSO 和本地用户名模式。 |
| `deploy_source` | string | `custom_create` | 创建入口：`custom_create`、`intelligent_create`、`code_package` 或 `unknown`。 |
| `deploy_action` | string | `create` | `create` 表示新建 Runtime，`update` 表示更新已有 Runtime。 |
| `deploy_region` | string | `cn-beijing` | Agent Runtime 部署区域。 |
| `runtime_network_type` | string | `public` | Runtime 网络类型：`public`、`private` 或 `both`。 |
| `feishu_enabled` | string | `false` | 是否启用飞书 Channel。 |
| `failed_phase` | string | `build` | 失败时最近的部署阶段。 |
| `error_kind` | string | `build_failed` | 归类后的错误类型，不上报完整错误文案。 |

看板主口径：

```text
事件 = studio_agent_deploy_failed
指标 = 上报量 / COUNT
```

### `studio_sandbox_create_succeeded`

触发时机：

- 用户在确认弹窗里确认创建 Sandbox。
- `sandboxClient.startSession()` 或 `sandboxClient.startAgentSession()` 成功返回
  `SandboxSession`。

用途：

- 统计 Sandbox Session 创建成功数。
- 按 Sandbox 类型和入口拆分创建结果。

字段：

| 字段 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `studio_deploy_id` | string | `stddep_...` | 关联 Studio 实例。 |
| `user_pool_id` | string | `up-...` | Studio 绑定的用户池 ID。 |
| `vefaas_application_id` | string | `app-id` | VeFaaS Application ID。 |
| `vefaas_function_id` | string | `func-id` | VeFaaS Function ID。 |
| `studio_region` | string | `cn-beijing` | Studio 部署区域。 |
| `studio_project` | string | `default` | VeFaaS 项目。 |
| `studio_version` | string | `bundled` | Studio 版本。 |
| `user_id` | string | `123456` | 当前登录用户 ID。 |
| `user_role` | string | `admin` | 当前登录用户的 Studio 角色。 |
| `user_source` | string | `sso` | 区分 SSO 和本地用户名模式。 |
| `sandbox_kind` | string | `codex` | Sandbox 类型：`codex`、`openclaw` 或 `hermes`。 |
| `sandbox_source` | string | `new_chat` | 创建入口：`new_chat` 或 `my_agents`。 |
| `sandbox_session_id` | string | `session-id` | 成功创建后返回的 Sandbox Session ID。 |

看板主口径：

```text
事件 = studio_sandbox_create_succeeded
指标 = 上报量 / COUNT
```

### `studio_sandbox_create_failed`

触发时机：

- 用户在确认弹窗里确认创建 Sandbox。
- `sandboxClient.startSession()` 或 `sandboxClient.startAgentSession()` 抛出非取消异常。

用途：

- 统计 Sandbox Session 创建失败数。
- 按 Sandbox 类型、入口和错误类型拆分失败分布。

字段：

| 字段 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `studio_deploy_id` | string | `stddep_...` | 关联 Studio 实例。 |
| `user_pool_id` | string | `up-...` | Studio 绑定的用户池 ID。 |
| `vefaas_application_id` | string | `app-id` | VeFaaS Application ID。 |
| `vefaas_function_id` | string | `func-id` | VeFaaS Function ID。 |
| `studio_region` | string | `cn-beijing` | Studio 部署区域。 |
| `studio_project` | string | `default` | VeFaaS 项目。 |
| `studio_version` | string | `bundled` | Studio 版本。 |
| `user_id` | string | `123456` | 当前登录用户 ID。 |
| `user_role` | string | `admin` | 当前登录用户的 Studio 角色。 |
| `user_source` | string | `sso` | 区分 SSO 和本地用户名模式。 |
| `sandbox_kind` | string | `codex` | Sandbox 类型：`codex`、`openclaw` 或 `hermes`。 |
| `sandbox_source` | string | `new_chat` | 创建入口：`new_chat` 或 `my_agents`。 |
| `error_kind` | string | `unknown` | 归类后的错误类型，不上报完整错误文案。 |

看板主口径：

```text
事件 = studio_sandbox_create_failed
指标 = 上报量 / COUNT
```

## 部署元信息

`veadk studio deploy` 成功部署并二阶段 release 时，除现有环境变量外再注入：

| 环境变量 | 示例 | 说明 |
| --- | --- | --- |
| `VEADK_STUDIO_DEPLOY_ID` | `stddep_...` | 本次 Studio 部署的稳定 ID。 |
| `VEADK_STUDIO_USER_POOL_ID` | `up-...` | Studio 绑定的用户池 ID。 |
| `VEADK_STUDIO_DEPLOY_REGION` | `cn-beijing` | Studio 部署区域。 |
| `VEADK_STUDIO_PROJECT` | `default` | VeFaaS 项目。 |

`VEADK_STUDIO_DEPLOY_ID` 生成规则：

```text
stddep_<uuid4 hex>
```

`veadk studio deploy` 使用的火山 AK 仅用于部署云资源，不会作为前端埋点维度下发或上报。
如果后续产品需要“真实部署人”维度，需要接入云身份查询或审计侧数据，而不是使用部署 AK。

## `/web/ui-config` 字段

`UiConfig` 增加 `telemetry` 配置：

```json
{
  "telemetry": {
    "enabled": true,
    "provider": "apmplus",
    "apmplus": {
      "aid": 123456,
      "token": "<public web sdk token>",
      "domain": "apmplus.volces.com",
      "env": "production"
    },
    "studio": {
      "deployId": "stddep_...",
      "userPoolId": "up-...",
      "applicationId": "app-id",
      "functionId": "func-id",
      "region": "cn-beijing",
      "project": "default",
      "version": "bundled"
    }
  }
}
```

APMPlus 配置来源：

| 环境变量 | 说明 |
| --- | --- |
| `VEADK_STUDIO_APMPLUS_AID` | APMPlus Web 应用 ID；不内置默认值，由 release server 或部署环境注入。 |
| `VEADK_STUDIO_APMPLUS_TOKEN` | APMPlus Web SDK token；不内置默认值，由 release server 或部署环境注入。 |
| `VEADK_STUDIO_APMPLUS_DOMAIN` | 上报域名，默认固定为 `apmplus.volces.com`。 |
| `VEADK_STUDIO_APMPLUS_ENV` | 上报环境，默认固定为 `production`。 |

`Publish Studio Release` 会把 GitHub Environment 中配置的 APMPlus AID/token 发送给 release
server。release server 构建 bundle 时把它们写入内部发布配置；Studio 自更新解包后读取该配置，
删除内部配置文件，再把 `VEADK_STUDIO_APMPLUS_AID` 和 `VEADK_STUDIO_APMPLUS_TOKEN`
注入最终 VeFaaS Function 环境。

Python 侧埋点配置集中在 `veadk/cli/studio_telemetry.py`：部署参数校验、release AID/token
校验、`/web/ui-config.telemetry` payload 生成都走同一个模块，避免后续重构
`cli_frontend.py` 或 release 打包逻辑时出现多份规则漂移。

## 前端实现

`frontend/src/adk/telemetry.ts` 负责：

- 初始化 `@apmplus/web`。
- 维护全局 Studio telemetry context。
- 提供 `trackStudioEvent(name, categories, metrics)`。
- 对上报做错误兜底，失败只 `console.warn`，不抛出到业务流程。
- 通过内存 Set 对单页面生命周期内的关键事件去重。

关键接口：

```ts
export interface StudioTelemetryContext {
  deployId: string;
  userPoolId: string;
  applicationId: string;
  functionId: string;
  region: string;
  project: string;
  version: string;
}

export function initStudioTelemetry(config: UiConfig["telemetry"]): void;

export function identifyStudioTelemetryUser(args: {
  userId: string;
  role?: StudioRole;
  local: boolean;
}): void;

export function trackStudioEvent(
  name: StudioTelemetryEventName,
  categories?: Record<string, string | number | boolean | null | undefined>,
  metrics?: Record<string, number>,
): void;
```

接入点：

| 位置 | 改动 |
| --- | --- |
| `frontend/src/adk/client.ts` | 扩展 `UiConfig` 类型，解析 `telemetry`。 |
| `frontend/src/App.tsx` 的 `getUiConfig()` effect | 调用 `initStudioTelemetry(cfg.telemetry)`，随后上报 `studio_instance_loaded`。 |
| `frontend/src/App.tsx` 的 `/web/access` effect | 后端返回 role 与 `telemetry.userId` 后调用 `identifyStudioTelemetryUser()`，再上报 `studio_user_authenticated`。 |
| `frontend/src/ui/ProjectPreview.tsx` 的 `performDeployment()` | `onDeploy()` 成功后上报 `studio_agent_deploy_succeeded`；非取消异常上报 `studio_agent_deploy_failed`。 |
| `frontend/src/App.tsx` 的 `launchSandboxSession()` | Sandbox Session 创建成功后上报 `studio_sandbox_create_succeeded`；非取消异常上报 `studio_sandbox_create_failed`。 |

去重策略：

- `studio_instance_loaded`：单页面生命周期一次。
- `studio_user_authenticated`：`studio_deploy_id + user_id + user_role` 单页面生命周期一次。
- `studio_agent_deploy_succeeded` / `studio_agent_deploy_failed`：不去重，每个有结果的部署操作上报一次。
- `studio_sandbox_create_succeeded` / `studio_sandbox_create_failed`：不去重，每个有结果的创建操作上报一次。

字段规范：

- APMPlus `sendEvent` 的 `categories` 仅放字符串维度。
- 数值型耗时、数量放 `metrics`。
- Boolean 转成 `"true"` / `"false"`，避免控制台维度类型不稳定。
- 错误不上报完整 message，只上报归类后的 `error_kind`。
- Agent 部署结果第一版不依赖 `metrics`；看板用成功/失败事件的上报量统计。
- Sandbox 创建结果第一版不依赖 `metrics`；看板用成功/失败事件的上报量统计。

## 后端实现

`veadk/cli/cli_frontend.py` 负责：

1. `frontend_deploy()` 生成部署元信息。
2. `veadk_environments` 注入 APMPlus 配置和部署元信息。
3. 二阶段 `release_environment` 同步注入 `VEADK_STUDIO_DEPLOY_ID`、
   `VEADK_STUDIO_USER_POOL_ID`。
4. `/web/ui-config` 返回 `telemetry` 配置。
5. `/web/access` 返回 `telemetry.userId`。

## 测试

后端测试：

- `tests/cli/test_frontend_runtime_proxy.py`
  - `/web/ui-config` 在 APMPlus env 缺失时使用默认 WebPro 配置。
  - `/web/ui-config` 在 env 完整时支持覆盖 telemetry 配置。
  - 返回部署元信息字段使用当前 schema。

- `tests/cli/test_studio_deploy_target.py`
  - `veadk studio deploy` 生成 `VEADK_STUDIO_DEPLOY_ID`。
  - `veadk studio deploy` 注入 `VEADK_STUDIO_USER_POOL_ID`。
  - 二阶段 release 环境包含 telemetry 元信息。

- `tests/cli/test_studio_rbac.py`
  - `/web/access` 返回当前登录用户的 `telemetry.userId`。

前端测试：

- `frontend/tests/studioTelemetry.test.mjs`
  - `initStudioTelemetry` 调用 SDK init/start。
  - `trackStudioEvent` 使用自定义事件上报，并带上 Studio context。
  - 除 `studio_instance_loaded` 外，登录和部署结果事件都带用户字段。
  - Agent 部署只上报 `studio_agent_deploy_succeeded` 和
    `studio_agent_deploy_failed`，不额外上报 started 事件。
  - Sandbox 创建只上报 `studio_sandbox_create_succeeded` 和
    `studio_sandbox_create_failed`，不额外上报 started 事件。

- `frontend/tests/studioAccess.test.mjs`
  - 覆盖 `/web/access` schema 中的 `telemetry.userId`。

## 安全与隐私

- 禁止上传 `VOLCENGINE_SECRET_KEY`、`VOLCENGINE_SESSION_TOKEN`、
  `OAUTH2_CLIENT_SECRET`。
- 禁止上传 Runtime API key、构建日志、错误详情全文、环境变量全集、prompt、对话内容、
  生成代码或 Agent 输出。
- `user_pool_id`、`user_id`、`vefaas_application_id`、`vefaas_function_id`
  会作为统计维度原值进入 APMPlus。它们便于在看板中排查和分组，但需要按内部数据治理要求
  控制看板权限。
- 部署使用的火山 AK 不会作为 `deployer_id` 下发到前端或进入 APMPlus。
- APMPlus token 属于前端 SDK token，可通过 `/web/ui-config` 下发；若产品侧认为 token
  也需要隐藏，则改用服务端代理上报。

## 验收标准

- 配置 APMPlus token 后，打开 Studio 能看到 `studio_instance_loaded`。
- 登录成功后能看到 `studio_user_authenticated`。
- `studio_instance_loaded` 不包含 `user_id`。
- `studio_user_authenticated` 包含 `user_id`、`user_role`、`user_source`。
- `/web/ui-config` 不返回任何云密钥明文。
- 前端 `npm test`、`npm run build` 通过。
- 修改过的 Python 测试通过。

## 待确认项

- APMPlus 控制台是否支持字段级去重聚合；如果不支持，需要用查询、导出或离线分析实现
  `count(distinct ...)`。
- 当前不做 CLI/服务端部署成功上报；本方案只统计被打开和登录使用过的 Studio。
- 是否需要按天、周、月分别做去重口径；这属于看板或数据分析配置，不影响事件采集。
