# 托管网络查询的空结果

[English](2026-10-09-empty-network-results.md)

变更 ID：mpa-network-discovery。创建/修订：2026-10-09。状态：implemented。

## 证据与范围

只读诊断确认托管 VPC 为 Available，尚无子网创建意图，成功的 DescribeSubnets 响应经当前 SDK 序列化为 `subnets=None, total_count=0`。`NetworkCloud._list` 将其视为无效结果，导致编排器无法创建第一个子网。本修复接续[归属描述修复](../mpa-network-description/2026-10-09-valid-network-marker.zh.md)。

目标：规范化明确的提供方空结果，在已记录的 VPC 中继续准备子网。非目标：修改 UI、IAM、PG、APIG、Runtime/聊天、资源名称或自动删除。本次验证不执行云写入、任务重试、数据库修改、提交或部署。

## 需求与场景

- FR-1：查询第一页时，`vpcs`/`subnets` 为 null 或缺失且整数 `total_count=0`，应解释为空列表。已有列表响应保持原有行为。
- FR-2：null/缺失集合但没有明确整数零、即使数量为零的标量集合、后续页面的 null 集合均拒绝。布尔/字符串/浮点数量不算整数证据。提供方错误不得转换为空结果。
- FR-3：已记录的托管 VPC 返回上述空子网结果时，继续创建一个子网。第二次 ensure 复用原 VPC 和子网；持久化意图、归属校验及未知结果防重复机制保持不变。

新 VPC 没有子网时，查询返回空列表并继续创建。查询不完整/畸形或提供方权限错误时，准备失败。分页非空结果之后出现 null/零响应时，不得丢弃之前的记录。

## 设计与契约影响

`managed/network_cloud.py` 的 `_list` 负责规范化，两个查询方法共用。仅在 `items is None`、`type(total_count) is int`、数量为零且为第一页时规范化。现有分页上限、错误、凭据及请求参数保持不变。不修改数据结构、公开签名、权限或配置，不新增依赖。[Studio 创建契约](../../../specs/studio-mpa-creation/README.zh.md) 负责区分空结果与错误；[Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md) 引用该契约。用户重试保留现有 VPC，无需迁移或清理。

并发、取消及超时处理不变，因为只规范化已经成功返回的查询载荷。不得将失败请求或未知 Create 结果解释为空查询。

## 任务、测试与验收

| 需求 | 任务 | 验收 |
| --- | --- | --- |
| FR-1 | T-1：先添加当前 SDK 及缺失集合的失败测试，再规范化 | AC-1：DescribeVpcs/DescribeSubnets 零记录响应返回空列表 |
| FR-2 | T-2：负向与分页回归 | AC-2：畸形响应/错误仍失败；非空分页记录保留 |
| FR-3 | T-3：隔离的编排器/适配器集成 | AC-3：恢复已记录 VPC，创建一个子网，重复调用复用 |
| FR-1–3 | T-4：双语审查及验证 | AC-4：相关测试、Ruff/Pyright、密钥/差异/文档检查通过 |

命令：`uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py -q`；修改文件的 Ruff/Pyright 和 pre-commit。真实云重试为用户另行提交的冒烟，不以模拟测试宣称真实创建成功。

## 审查、批准与风险

review-spec 不可用，直接执行设计审查。已审查提供方序列化、null 与畸形结果区别、分页一致性、归属、恢复、凭据脱敏与双语等价，无阻塞项。用户批准：诊断 null/零响应并提出空结果修复后，用户要求“帮我改正”。风险：没有明确整数零的 null 响应仍故意报错，不普遍吞掉畸形查询。保留工作区无关修改。

## 验证与交付

2026-10-09，基于 `ef0ad519` 的工作区。下文已记录先失败测试、实现及验证结果。前端/构建/浏览器/生成资源及 sidecar 检查为 not_applicable：未改变其契约。全仓库/全文件提交检查及真实云冒烟为 not_run：本次未请求提交或真实重试。


本次修复验证结果：

- pass：实现前，四个当前 SDK/缺失集合回归均因 `Network discovery returned invalid results` 失败；补全持久化 VPC 测试夹具后，编排回归也在同一查询错误处失败。
- pass：网络适配器/编排器专项：88 项通过。上述最终托管/Runtime 命令：534 项通过，5 条既有依赖弃用警告，用时 23.67 秒。
- pass：测试方法参数名称修正后的最终恢复专项：1 项通过；未修改生产行为。
- pass：对 `network_cloud.py`、`test_deployment_network_cloud.py`、`test_deployment_network.py` 运行 `uvx --from ruff==0.11.12 ruff check` 和 `ruff format --check`；同文件 `uvx pyright --pythonpath .venv/bin/python`：0 错误、0 警告。初始模拟对象/适配器方法参数名称不一致已修正，未使用类型抑制。
- pass：对三个 Python 文件及六份双语文档执行 `uv run --extra dev pre-commit run --files`：Ruff/静态/格式及硬编码密钥扫描通过。YAML 扫描为 not_applicable（未修改 YAML）。双语 FR/T/AC 标识、全部相对文档链接目标及 `git diff --check` 通过。

实现审查：只规范化明确的第一页空结果。拒绝的 null/非零及后续页面响应不会进入资源创建。已有列表响应、提供方错误透传、记录复用及创建前持久化恢复均有覆盖。隔离测试及最终文档/密钥检查满足 AC-1–4。不宣称真实重试成功。
