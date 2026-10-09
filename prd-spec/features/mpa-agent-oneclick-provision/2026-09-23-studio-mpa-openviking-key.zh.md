# Studio MPA OpenViking 凭据

[English](2026-09-23-studio-mpa-openviking-key.md)

- 变更 ID：`studio-mpa-openviking-key`
- 日期：2026-09-23
- 组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-11

## 背景与证据

旧 ArkClaw 流程会同时注入 `OPENVIKING_USER=default`、地址、API Key 和资源 ID。当前 Studio 托管配置没有用户设置或 API Key，但向导声称部署服务一定提供密钥。创建任务会把非密钥请求参数持久化到 SQLite 并通过任务快照返回；直接把密钥加入该参数会泄漏。

## 目标、非目标与场景

在 OpenViking 步骤增加遮罩的 API Key 输入框。地址、资源 ID 和密钥三项同时填写时，向新 Runtime 注入与旧 ArkClaw 相同的四个变量；三项全空时不注入，并清除模板或参考 Runtime 继承的旧值。密钥须传至子进程，不得进入浏览器存储、任务 SQLite、状态响应、日志或错误详情。本次不创建 OpenViking 资源，不改已有智能体或旧 CLI。

## 需求与设计

- **FR-1：**OpenViking 步骤显示可选的密码型 `openvikingApiKey` 字段（最多 512 字符）及准确说明。密钥只保留在组件内存，不进入会话草稿。失败重试可重新输入；浏览器重启后必须重输。
- **FR-2：**鉴权 POST 接收密钥，在持久化非密钥任务参数前将其移除，并单独通过标准输入传给固定子进程。任务快照和 SQLite 均不包含密钥；未知敏感字段会被拒绝。
- **FR-3：**三项输入必须全部填写或全部留空。填写时，runner 注入 `OPENVIKING_URL`、`OPENVIKING_RESOURCE_ID`、`OPENVIKING_API_KEY` 和 `OPENVIKING_USER=default`。全空时，新 Runtime 清除全部四项，包括继承值。
- **FR-4：**保持原有请求身份、重试和取消行为。配置接口不返回凭据。

涉及文件：Studio 创建 UI/API/国际化、`frontend/server/mpa_creation.py`、托管任务与配置代码、双语组件契约和运维文档。信任边界仍是鉴权 Studio 服务端；密钥仅为临时进程数据，包括子进程发起的 Runtime 部署请求。任务参数持续保留但不含密钥。服务端重启无法恢复未发送的密钥，用户重试时重新提供。

## 任务、测试与验收

1. 先添加前端、路由、任务存储和 Runtime 环境变量的失败测试，覆盖密钥传递与不落盘。
2. 实现遮罩输入、单独传递密钥、Runtime 覆盖及默认用户设置。
3. 更新双语契约和使用文档；运行定向 Python 测试、前端测试/构建、Ruff、Pyright、资源检查及浏览器验证。

验收：测试密钥到达子进程和 Runtime 环境；浏览器草稿、任务响应及 SQLite 不包含它；三项全空时即使有继承值也不注入四项；部分填写会被拒绝；启用时用户值为 `default`。单元验证不需要真实 OV/Runtime 云操作。

## 审查与验证

设计审查覆盖 API 边界、密钥生命周期、重启后重试、双语字段、兼容性和取消。现有任务库不能安全保存密钥，因此设计明确将其排除在持久化参数之外。2026-09-23，定向托管创建测试通过（最终新增的留空回归测试前为 348 项），前端测试通过（1,305 项 Node 与 36 项 Vitest）、TypeScript 与 Pyright 通过、生产构建和打包资源检查通过，`git diff --check` 通过。完整 Ruff 检查报告所触及模块原有的导入顺序/行长问题；忽略原有 E501 的 E/F 检查通过。浏览器检查到达本地登录页，但未继续接受其服务条款；未执行真实 OV/Runtime 云端创建。

2026-09-23 的全填或全空补充修改通过 363 项托管创建测试、1,305 项 Node 和 36 项 Vitest 前端测试、TypeScript、Pyright、忽略原有 E501 的 Ruff E/F、生产构建、打包资源检查及 `git diff --check`。Runtime 环境变量测试覆盖模板、参考 Runtime 和平铺配置下的全空及完整输入。未执行真实 OV/Runtime 云端创建。

更广范围的并行 Python 回归未完成：首次运行出现失败，原因尚未核实，随后停止以定位问题；快速失败的重跑在收集测试时因自托管沙箱示例缺少可选 `anthropic` 包而停止。这不影响托管创建定向测试的通过结果。

2026-09-23 基于 `17f392f7` rebase 后，最终工作区改动通过 371 项托管创建测试、1,305 项 Node 测试、36 项 Vitest 测试、前端生产构建、打包资源检查、pre-commit Ruff/格式/密钥检查及 `git diff --check`。默认双进程 Python 回归在收集阶段因可选自托管沙箱示例导入了当前环境缺失的 `anthropic` 包而停止。本轮未运行 Pyright，因为当前环境没有安装该命令；rebase 前的较早检查曾通过。
