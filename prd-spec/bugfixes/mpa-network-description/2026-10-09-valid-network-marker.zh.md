# 托管网络合法描述与拒绝意图恢复

[English](2026-10-09-valid-network-marker.md)

变更 ID：mpa-network-description。创建/修订日期：2026-10-09。状态：implemented。

## 证据、目标与范围

新账号创建在 `network` 失败：CloudTrail 确认 `CreateVpc` 返回 `InvalidDescription.Malformed`。共享注册表保留 `vpc_dispatched=false`、无 VPC ID、描述含冒号的 VPC 意图。VPC/子网描述规则不允许冒号：[CreateVpc](https://docs.volcengine.com/docs/VirtualPrivateCloud/CreateVpc-CreatingaVPC?lang=en)、[CreateSubnet](https://docs.volcengine.com/docs/VirtualPrivateCloud/CreateSubnet-Creatingasubnet?lang=en)。保留核验账号/地域的归属哈希及名称。此处不记录凭据或原始审计载荷。

用户在诊断后要求修正，批准本次限定修复。不改变前端、IAM、PG、APIG、Runtime/聊天或镜像；编码代理不执行真实云创建或数据库维护。真实部署仍通过获授权的创建/重试请求执行。

## 需求与场景

- FR-1：新 VPC/子网请求以 `mpa-account-network-v1-<scope hash>` 为 Description，保留名称、账号/地域哈希及归属校验。
- FR-2：持久化旧意图仅描述不同，且派发标记明确为 false、无已登记资源 ID、按名称查询无匹配资源时，才能改为新描述。其他请求字段必须完全一致。因请求体改变，生成新的 ClientToken；在现有锁内先保存后派发。
- FR-3：结果不确定/在途旧意图不得再次 Create。可恢复查询到的旧资源。归属仅接受当前范围精确的旧/新标记；无关描述、错误账号、CIDR、VPC 或可用区仍失败。已有资源不改写、不删除、不重建。
- FR-4：相同请求体被明确拒绝权限时仍保留原 ClientToken。取消/超时保留意图，避免重复创建。

场景：新账号通过服务商描述校验；旧 VPC/子网拒绝意图以修正描述和新 token 恢复；CIDR/项目/可用区改变仍拒绝；结果不确定且查询无资源时安全失败；旧资源从注册表或精确范围名称/标记恢复复用。

## 设计与受影响文件

`managed/network.py` 管理合法/旧范围标记及 `_create` 内仅描述不同的精确兼容。现有资源等待和归属检查只接受这两个范围标记。现有 `NetworkCloudError` 明确拒绝派发标记作为恢复证据；标记缺失不代表明确拒绝。不新增表或 API，不将错误转换成成功。

组件契约：[Studio 创建](../../../specs/studio-mpa-creation/README.zh.md)、[Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)。同步双语版本及 managed README。测试位于 `tests/integrations/mpa_managed/test_deployment_network.py`，使用隔离云端/注册表夹具。

## 任务与验收

| 需求 | 任务 | 验收 |
| --- | --- | --- |
| FR-1 | T-1：服务商格式失败回归及合法标记 | AC-1：两种创建载荷满足描述允许字符 |
| FR-2 | T-2：精确拒绝意图恢复 | AC-2：同一智能体可重试成功；仅描述/token 改变，并先保存后派发 |
| FR-3、FR-4 | T-3：兼容及安全测试 | AC-3：旧资源恢复/复用、结果不确定不重复创建、输入变化拒绝、相同请求 token 保留 |
| FR-1–4 | T-4：双语同步及检查 | AC-4：managed 回归、Ruff/Pyright、密钥/差异检查通过 |

命令：`uv run --extra dev pytest tests/integrations/mpa_managed`，变更文件 Ruff/Pyright 和 pre-commit。前端/构建/浏览器/sidecar 检查为 not_applicable：没有前端或 sidecar 改动。全仓检查及真实 smoke 单独记录；未请求提交或部署。

## 审查、批准与风险

直接审查（review-spec 不可用）：已检查精确范围兼容、false 与标记缺失的区别、变更请求体使用新 token、云调用前锁内持久化、资源归属及部分失败。双语语义等价，无阻塞项。批准来源：用户在获知描述/拒绝意图修复方案后要求修复。保留已有资源。结果不确定的旧意图仍可能需要运维核对，不重置它来宣称成功。验证记录见下。

## 验证与交付记录

2026-10-09，基于 `ef0ad519` 工作区，仅涉及网络描述/恢复。保留此前 IAM/账号工作及用户无关改动。

- pass：测试先行的服务商格式回归在修改代码前出现 3 个预期失败（`InvalidDescription.Malformed`）。
- pass：`uv run --extra dev pytest tests/integrations/mpa_managed/test_deployment_network.py tests/integrations/mpa_managed/test_deployment_network_cloud.py -q`：62 项通过，覆盖 VPC/子网拒绝意图修正、未知结果查询恢复/阻止、旧资源复用、载荷冲突和相同请求 token 保留。
- pass：最终 `uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py -q`：508 项通过；仅有既有依赖弃用警告。
- pass：两个变更 Python 文件的 `uvx --from ruff==0.11.12 ruff check` 和 `ruff format --check`。最终 `uvx pyright --pythonpath .venv/bin/python veadk/integrations/mpa/managed/network.py tests/integrations/mpa_managed/test_deployment_network.py`：0 错误、0 警告。初次测试夹具字典推断问题通过原地 update 修正，未绕过生产类型检查。
- pass：Python 和双语文档变更文件的 `uv run --extra dev pre-commit run --files`：Ruff 检查/格式及硬编码密钥扫描通过。YAML 扫描 not_applicable（无 YAML 改动）。
- pass：双语标识、设计相对链接和 `git diff --check`。Studio 配置描述与此前 STS 账号修复同步。
- not_applicable：前端测试/构建/浏览器、生成 web 产物及 sidecar 门禁；没有 UI 或 sidecar 改动。
- not_run：全仓回归/all-files pre-commit，因未请求提交且变更限于部署；真实重试/云资源变更由用户提交创建/重试请求后执行。诊断审计是只读查询，不代表创建 smoke 成功。

审查完成：其他输入保持不可变，仅接受精确范围的新/旧标记，不重置结果不确定的派发，请求体变化时重新生成 token 并在云调用前保存。AC-1–4 通过隔离检查满足，不宣称完整真实创建成功。保留已有资源和记录，直到获授权的重试执行限定意图修正。
