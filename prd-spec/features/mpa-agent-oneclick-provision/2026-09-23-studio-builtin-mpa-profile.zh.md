# Studio 内置 MPA 创建配置

[English](2026-09-23-studio-builtin-mpa-profile.md)

- Change ID: `studio-builtin-mpa-profile`
- Date: 2026-09-23
- Status: 用户要求移除 Studio YAML 依赖，已批准该范围
- Component: [Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)

## 背景与证据

Studio 当前在配置检查和任务提交时读取 `VEADK_MPA_CREATE_CONFIG`，默认路径为 `mpa-create.config.yaml`；子进程再次读取同一文件。文件缺失会在云资源检查前阻止创建。现有北京地域私有配置包含非密钥的账号、资源、镜像和模型默认值，以及模型 API Key 的环境变量引用。部署凭据已从服务端环境或凭据服务取得。

## 目标、非目标与场景

Studio 创建流程无需 YAML 文件即可运行。保留现有北京地域账号、VPC/子网、APIG、Runtime/worker 镜像、模型和 PostgreSQL 自动准备默认值。密钥仍留在源码之外。CLI 的 `--config` YAML 流程、既有任务记录、现有智能体及其他地域不改变行为。本改动不执行真实资源创建。

- 没有 YAML，但模型密钥环境变量和部署凭据有效时，配置检查返回正常的安全摘要，创建任务使用内置配置。
- `VEADK_MPA_CREATE_CONFIG` 指向失效路径时，Studio 忽略该变量；CLI 仍读取显式传入的 YAML 路径。
- 模型密钥或部署凭据缺失时，Studio 在云写入前返回安全的配置错误。
- 任务开始后，固定子进程不读取 YAML 路径，而是使用同一内置配置；重试保留原智能体 ID 和参数。

## 需求与设计

- **FR-1：**新增代码内置的北京地域 Studio 配置，匹配当前私有 YAML 中的非密钥默认值。固定账号/资源 ID、镜像和 Runtime 环境参数保留在内置配置中。运行时继续解析 `VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY`；不得写入 API Key、PG 密码、访问密钥或会话令牌字面值。
- **FR-2：**Studio 的检查和提交均选择内置配置，不受 `VEADK_MPA_CREATE_CONFIG` 影响。内置配置沿用现有托管配置校验及 Studio Identity 复用逻辑。
- **FR-3：**任务管理器向固定子进程传递明确的内置配置标记；子进程按请求地域加载它。CLI 和既有任务 API 的 YAML 路径处理保持兼容。
- **FR-4：**任务参数、响应与日志不含模型或部署密钥。不支持的地域或环境凭据缺失时，在云写入前返回安全错误。

内置配置有意限定于当前北京地域部署。更换账号、地域或镜像需要修改代码并审查。Studio 部署仍须提供模型密钥及云凭据环境变量，不再需要 YAML 路径。信任边界仍是 Studio 服务端及固定子进程；不增加浏览器输入或持久化任务字段。

涉及文件：托管配置加载与内置默认值、Studio 创建路由、任务到子进程传递、子进程入口、双语组件契约、双语运维文档及定向测试。CLI 配置解析继续支持 YAML。

## 任务与测试

1. 先添加失败测试，覆盖无 YAML 的内置配置检查、失效 YAML 路径、默认值一致性、缺少密钥、不支持地域及子进程配置选择。
2. 通过现有校验器加入内置配置，并仅将 Studio 切换到该配置。
3. 更新双语组件契约及运维文档；运行托管创建和前端测试、构建/资源检查、Ruff、环境允许时的 Pyright 及 pre-commit 检查。

## 风险与验收

写死的资源 ID 可能失效，固定镜像也可能过时；错误须明确，不能静默选择其他账号的资源。已有任务重试不得改变部署身份。验收要求 Studio 创建不读取 YAML，CLI YAML 路径继续可用，源码没有密钥字面值，子进程使用相同的内置配置。测试应模拟云服务；真实部署另行验证。

## 审查与交付记录

设计审查：内置配置经过现有校验器，不增加第二套解析器；源码只含非密钥常量，Studio 无文件路径与 CLI 显式文件路径边界清晰。用户请求已授权该范围。

2026-09-23 对未提交工作区差异的验证记录：

- **pass：**托管创建与 CLI 测试（`394 passed`）；前端测试（`1305` 项 Node 和 `36` 项 Vitest 通过）；前端构建与 Web 资源检查；pre-commit Ruff 和密钥检查；内置配置与原私有 YAML 经校验后的内容一致，比较过程未输出密钥。
- **fail（无关的可选依赖）：**并行 Python 回归达到 `5096 passed, 11 skipped, 2 xfailed` 后，`tests/cloud/test_harness_app_contract.py::TestHarnessConfig::test_spawn_applies_resource_overrides_to_clone_only` 因缺少 `llama_index` 失败；单独重跑复现了缺依赖。收集时排除了两个需要缺失的 `anthropic` 依赖的 Runtime 模块。
- **not_run：**Pyright、真实浏览器创建流程和真实云资源创建。最终检查时本地 Studio 未监听 8000 端口；需要部署或重启服务才能观察到新行为。
