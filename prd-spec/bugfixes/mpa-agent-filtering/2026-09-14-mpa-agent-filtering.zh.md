# MPA 智能体筛选修复

- Change ID: `mpa-agent-filtering`
- Created: 2026-09-14
- Status: approved
- English: [2026-09-14-mpa-agent-filtering.md](2026-09-14-mpa-agent-filtering.md)
- Related specs: [MPA Runtime Provisioning](../../../specs/mpa-runtime-provisioning/README.md), [Studio MPA Control Plane](../../../specs/studio-mpa-control-plane/README.md)

## 背景与证据

Studio 已新增 `CloudRuntime.agentCategory`，新对话选择器也可以展示 `MPA 智能体` 类型，但 MPA Runtime 不能稳定出现在该分类下。服务端分类必须使用显式 Runtime 标签；artifact URL 匹配会让历史测试镜像污染 MPA 筛选，不能作为产品分组依据。MPA Runtime 创建链路目前不会写入该标签；前端又是在加载一页 `/web/runtimes` 后再过滤，因此当某一页主要是通用智能体时，MPA Runtime 会被漏掉。“我的智能体”页面也还没有 `mpa` 类型选项。

## 目标

- 在 `veadk mpa create` 创建 MPA Runtime 时持久化稳定分类标签。
- 让 `/web/runtimes` 支持服务端按智能体分类过滤。
- 让新对话选择器和“我的智能体”页面使用同一套 MPA 分类。
- 保持未传分类参数的既有调用兼容。

## 非目标

- 不修改 mpa-agent 镜像或运行时协议。
- 本修复不推送镜像，也不修改 `~/workspace/bytedance/mpa/agentkit-mpa-agent`。
- 不在只读列表接口里自动修改云端 Runtime 标签。

## 需求

- `FR-1`: MPA Runtime 创建和按名称收敛更新必须包含 `veadk:agent-type=mpa`。
- `FR-2`: `/web/runtimes` 必须接受可选 `agentCategory=general|mpa`，并在暴露分页结果前完成服务端过滤。
- `FR-3`: 已有未打标签的 MPA Runtime 不得通过镜像名启发式归类为 MPA。只有显式补写 `veadk:agent-type=mpa` 后才进入 MPA 筛选。
- `FR-4`: 新对话和“我的智能体”类型筛选都必须展示 MPA，并且通用智能体中不得混入 MPA Runtime。

## 设计

`veadk.integrations.mpa.mpa_runtime.provision_runtime()` 新增 `tags` 映射参数。MPA CLI 传入 `{"veadk:agent-type": "mpa"}`。该函数在 `CreateRuntimeRequest` 和 `UpdateRuntimeRequest` 中都写入标签，确保重试复用同名 Runtime 时也会收敛到同一分类。

`GET /web/runtimes` 保持响应结构不变，新增可选查询参数 `agentCategory`。无效值返回 `400`。Runtime 分类只来自显式 Runtime 标签。当传入分类时，每个地域扫描器会持续读取控制面分页，直到得到足够的匹配项用于当前合并页，或远端游标结束。返回项仍包含 `agentCategory` 字段。

前端为 `getRuntimes()` 增加 `agentCategory` 参数。NewChatAgentPicker 不再对单页结果做本地二次过滤，而是向服务端请求 `mpa` 或 `general`。MyAgents 将 `mpa` 加入类型枚举，并对 `general` 与 `mpa` 共用 Runtime 列表路径；个人沙箱智能体类型保持不变。

## 任务

- `T-1`: 更新 MPA Runtime 标签写入和测试。
- `T-2`: 更新 `/web/runtimes` 分类过滤和测试。
- `T-3`: 更新前端 client、NewChatAgentPicker、MyAgents、i18n 和源码断言测试。
- `T-4`: 运行目标 Python/前端检查，并在前端输出变化时重建 Studio 资产。

## 验证与验收

| Requirement | Task | Acceptance criterion | Verification | Result |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1` | MPA create/update Runtime 请求包含 `veadk:agent-type=mpa`。 | `uv run --extra dev pytest tests/integrations/test_mpa_runtime.py tests/cli/test_cli_mpa.py` | pass |
| `FR-2` | `T-2` | `/web/runtimes?agentCategory=mpa` 只返回 MPA Runtime 分页，并拒绝非法分类。 | `uv run --extra dev pytest tests/cli/test_frontend_runtime_proxy.py::test_runtime_list_filters_agent_category_before_pagination -q` | pass |
| `FR-4` | `T-3` | 新对话和“我的智能体”都展示 MPA，并请求服务端分类过滤后的 Runtime 页。 | `node --test frontend/tests/newChatAgentPicker.test.mjs frontend/tests/myAgents.test.mjs`; `npm --prefix frontend test` | pass |
| All | `T-4` | Studio 构建产物与源码变化一致。 | `npm --prefix frontend run build -- --mode development`; `npm --prefix frontend run test:webui-assets`; `git diff --check` | pass |

## 风险

历史 MPA Runtime 如果没有 `veadk:agent-type=mpa`，仍会被归为通用智能体，直到执行显式标签修复。本修复不新增修复命令；它保证新建和更新后的 MPA Runtime 分类可靠，修复服务端分类分页语义，并避免按名称误纳入旧测试镜像。
