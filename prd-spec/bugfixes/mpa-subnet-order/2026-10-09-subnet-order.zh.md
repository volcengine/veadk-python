# 在子网顺序变化时保留托管 Runtime 的恢复能力

[English](2026-10-09-subnet-order.md)

- 变更 ID：`mpa-subnet-order`
- 创建/修订：2026-10-09
- 状态：implemented
- 契约：[Studio 创建](../../../specs/studio-mpa-creation/README.zh.md)、[Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)。

## 背景和范围

只读诊断发现 Runtime 的平台状态为 Ready，就绪接口为 HTTP 200，但创建任务在 V1 就绪后立即失败。共享注册记录与 Runtime 包含同样两个子网，顺序相反。validate_runtime 按有序列表比较 SubnetIds，抛出迁移错误。独立的合成样例已确认原因。AccountNetworkProvisioner.ensure 在恢复时重复该有序比较，采用平台顺序还会改变重试时已有的请求哈希。

目标：两处检查均忽略提供方仅改变子网顺序的情况，恢复原部署且不替换资源。非目标：验证时写云资源、修复注册记录、扩大诊断改造、修改 UI/聊天、权限、镜像或绕过真实网络变更。

## 场景和需求

- FR-1 / AC-1：两份子网列表成员相同、非空且无重复，仅顺序不同，首次 Runtime 校验和已有 Runtime 网络准备均接受。VpcId、EnableSharedInternetAccess 仍精确比较；增加、删除、替换、重复或格式错误的子网选择仍报错。
- FR-2 / AC-2：重试保留调用方请求中的子网顺序；没有显式选择且共享记录与当前 Runtime 成员一致时保留注册顺序，否则保留当前选择，不采用成员不同的共享默认值。这保留未改变输入的已持久化请求哈希和 ClientToken。不排序或改写旧部署记录，不放宽输入变更冲突检查。
- FR-3 / AC-3：模拟完整创建及已有待完成 V1 的恢复，平台元数据顺序相反时仍完成环境/密钥补齐和就绪检查，保留 Runtime/Skill Space/数据库标识且无重复资源。调用方输入和平台对象保持不变。

## 设计和契约影响

在 managed/network.py 共用一个小型子网成员比较函数，先验证列表格式、非空字符串 ID 和唯一性，再比较集合。network.py 和 runtime.py 仅对 SubnetIds 使用该函数，其他不可变字段仍严格比较。恢复时保留显式请求顺序；没有显式选择时，仅在共享注册记录与当前 Runtime 成员相同时使用注册顺序，否则保留当前智能体的选择。这同时解决迁移误判与重试哈希稳定性，不改变哈希格式或持久化结构。

Studio 创建拥有网络/恢复契约，Runtime 部署引用该契约。无 API/配置/结构/依赖/权限变化；通用智能体、旧 CLI 部署、异步截止时间、锁、取消、终态处理及凭据边界均不变。不盲目转换集合，格式错误列表仍拒绝。复用现有模拟云/注册记录生命周期测试，不涉及前端或生成资源。

## 任务和影响文件

- T-1（FR-1/AC-1）：在 test_deployment_network.py、test_runtime_deployment_edges.py 添加先失败测试，修改 managed/network.py、managed/runtime.py。
- T-2（FR-2、FR-3/AC-2、AC-3）：覆盖已有待完成 V1、原始哈希、反序元数据、同 ID 重试及无重复资源；网络准备保留显式或注册顺序。
- T-3：同步 Studio/Runtime 双语契约及 managed README 指南，运行目标和受影响部署回归、Ruff/Pyright、范围内 pre-commit/密钥扫描及文档链接/空白检查。

## 风险和验收验证

盲目转换集合可能隐藏重复或非法 ID：比较前验证并覆盖反例。采用平台顺序可能让旧待完成哈希无法恢复：通过生产重试路径验证已持久化原始请求。显式智能体覆盖可能与注册成员不同：不得以共享默认值替换。模拟测试不能证明云端发布，修复后的真实重试仍由操作者执行。交付代码修复不需要未经审查的云写操作。

## 审查和批准

用户于 2026-10-09 用“修复下”批准上轮提出的修复。保留哈希顺序是实现同 ID 恢复要求的必要细节。技能目录无 review-spec，修改生产代码/测试前已直接审查双语等价性、契约归属、错误边界、兼容性、安全、可测试性以及保留的并发/截止时间行为，无阻塞项。验证范围为 ef0ad519 加本次修复及已有未提交 MPA 修改。结果记录于下方；完整提交同步和门禁等待提交授权。

## 结果（2026-10-09）

- pass：T-1/T-2、AC-1/AC-2/AC-3。修正测试样例后，实施前先失败测试出现六处有序比较/请求哈希漂移失败，一项原本成功的边界通过（103 项未选中）。
- pass：`uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/cli/test_frontend_deploy_iam.py -q --tb=short` — 625 项通过，五条已有弃用警告。包含首次/待完成生命周期、补齐流程、原哈希/token 保留、真实变更及格式错误列表反例。
- pass：对 network.py、runtime.py、test_deployment_network.py、test_runtime_deployment_edges.py 执行 `uvx --from ruff==0.11.12 ruff check`、`uvx pyright --pythonpath .venv/bin/python`。初次 Pyright 问题已修复（列表类型收窄和条件测试变量），最终零错误。
- pass：直接实现审查确认请求哈希算法未变，不修改调用方/平台的子网选择，仅成员一致时优先采用注册顺序，不放宽资源归属或真实变更检查，异步生命周期/清理不变。
- blocked：本次真实 Runtime/注册记录只读核对返回 ApiError，未输出提供方请求内容或凭据。此前诊断快照及合成回归已确认顺序缺陷，但不声称修复后云查询或重试已成功。
- pass：范围内 pre-commit（Ruff、格式及硬编码密钥检测）、双语相对链接/标识和 diff 空白检查。格式检查首次修改两个测试文件，格式化后重跑检查。YAML 扫描 not_applicable，未修改 YAML。
- not_run：云端部署重试/完整实际发布，验证不执行云写操作。全 SDK 回归 not_run，受影响的托管/旧部署测试已覆盖本次集成修复。UI/构建/浏览器/生成资源及 Codex/harness 进程 smoke 为 not_applicable，未修改这些路径。完整提交同步/全文件门禁等待提交授权。T-3 完成，无延期实现范围。
