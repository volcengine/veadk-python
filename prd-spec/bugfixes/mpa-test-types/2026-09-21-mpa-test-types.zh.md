# MPA 编辑器类型诊断

[English](2026-09-21-mpa-test-types.md)

- ID：mpa-test-types；创建/修订：2026-09-21；状态：implemented。
- 组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)。

## 背景与范围

用户要求修复编辑器报红。对托管 MPA 实现、Studio 路由和测试执行 Pyright，发现测试替身和数字超时类型推断共 20 处错误。前端 `tsc --noEmit -p tsconfig.json` 通过。测试存在字面量推断过窄、动态添加未声明属性、用未声明类型的 namespace 代替 Profile、用元组代替 SDK 客户端、向 AsyncEngine 契约传入自定义替身等问题。与运行中的创建失败无关。

## 需求与设计

- FR-1：消除 20 处可复现的 Pyright 报错，不加忽略注释、不关闭检查、不用强制类型转换掩盖错误替身、不放宽生产对象契约。
- FR-2：服务测试使用真实 Profile/Managed 模型，显式声明替身能力和方法签名，SDK/engine 边界使用带 spec 约束的 mock。保留断言、故障注入和外部服务隔离。
- FR-3：runtime/network 超时秒数标注 float，准确描述本来支持的小数时长；保留默认值和运行逻辑。不修改依赖、配置、HTTP/UI、持久化或资源。

组件影响：维护契约无变化；类型标注明确现有数字行为，测试符合现有接口，无需修改组件规范。影响文件：`runtime.py`、`network.py` 和托管 MPA 下 test_agent_deployment、test_deployment_database_unit、test_deployment_network_cloud、test_gateway、test_runtime_deployment_edges、test_service。不顺手清理无关 lint。

## 任务与验收

| 需求 | 任务 | 验收 |
| --- | --- | --- |
| FR-1/2 | T-1：复现并修正类型化替身 | AC-1：完整托管 MPA 实现/路由/测试 Pyright 零错误，保留既有断言 |
| FR-3 | T-2：时长标注 | AC-2：默认值与超时/取消测试不变 |
| 全部 | T-3：验证和双语文档 | AC-3：MPA/CLI 回归、变更文件 Ruff/格式、TypeScript 检查、空白检查通过 |

已失败的 Pyright 是回归基线（20 处错误）。现有行为测试验证替身修正，类型改动无需重复增加行为测试。执行 `uv run --extra dev --with pyright pyright veadk/integrations/mpa/managed frontend/server/mpa_creation.py tests/integrations/mpa_managed`、`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` 及固定版本 Ruff 检查。

## 审查与批准

用户明确要求“有爆红啊，修一下”，并澄清“代码编辑器报红”。已说明方案：修复可复现的类型不匹配，不屏蔽检查。直接审查（review-spec 不可用）无契约/安全/双语阻塞项。风险：此命令以外的编辑器解释器专属错误仍可能需要具体文件/消息，不声称观察了编辑器状态。无需提交/推送/云操作或服务重启。

## 验证

2026-09-21 工作区差异：Pyright 基线 fail（20 处），TypeScript pass。最终检查 not_run（待执行）。浏览器/构建 not_applicable（无前端改动）；真实云 not_run（不相关）；pre-commit not_applicable（未请求提交）。


## 最终审查与验证（2026-09-21）

状态：implemented。T-1/T-2/T-3 和 AC-1/AC-2/AC-3 完成。生产差异仅为现有时长的 float 标注，默认值不变；替身修改保留行为/故障注入断言，使用真实 Profile 契约。未屏蔽检查，未放宽生产契约。

- pass：上述完整范围 Pyright — 0 errors、0 warnings（基线 20 errors）。
- pass：上述 MPA/CLI 回归命令 — 272 passed，一条上游 Starlette 弃用警告。
- pass：`frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json`（实际在 frontend 目录用等价相对路径执行），无前端修改。
- pass：变更文件 Ruff 检查/格式、相对链接、双语审查、差异空白检查。
- 迭代中签名对齐暴露一个无身份参数的替身锁调用，以及四个 mock engine 方言失败；已修正测试调用和显式方言绑定，最终 272 项通过，未遗留失败回归。
- not_run：全仓回归，改动仅涉及隔离 MPA 测试和时长标注，完整受影响组件/CLI 测试已通过。浏览器/构建/真实云：not_applicable。pre-commit/提交：not_applicable，未请求提交。

- pass：按仓库 Gitleaks 规则扫描全部 10 个变更代码/测试/设计文件，未发现密钥。
