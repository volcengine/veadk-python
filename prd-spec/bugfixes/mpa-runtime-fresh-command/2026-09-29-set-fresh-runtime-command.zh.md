# 设置全新托管 Runtime 启动命令

[English](2026-09-29-set-fresh-runtime-command.md)

- **变更 ID：** `mpa-runtime-fresh-command`
- **日期：** 2026-09-29
- **状态：** implemented
- **契约：** [MPA Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)
- **前序设计：** [保留参考 Runtime 启动命令](../../mpa-runtime-reference-command/2026-09-29-preserve-runtime-command.zh.md)

## 背景与证据

修复 Workload Identity 创建后，使用内置 profile 的真实 Studio 创建已经带上指定 MPA
镜像、Worker Tool 和 TOS 环境并进入 Runtime 创建，但 Runtime 在版本 0 进入 `Error`，
其 `Command` 为空。此前修复只保留参考 Runtime 的命令，而内置 Studio profile 使用
`fresh_template()`，没有参考 Runtime。当前 MPA Runtime 镜像通过 `bash run.sh` 启动。

## 目标与非目标

- 为全新托管 MPA Runtime 模板设置 `Command="bash run.sh"`。
- 保持显式 JSON 模板和参考 Runtime 的命令行为。
- 不开放命令配置，也不从任意镜像推断命令。

## 需求与设计

- **FR-1：** `fresh_template()` 必须输出标准 MPA 命令 `bash run.sh`。
- **FR-2：** `managed.from-runtime` 必须继续保留参考命令。
- **FR-3：** 显式 JSON 模板保持权威，除现有 Runtime settings 外不做修改。

仅在现有 MPA 专用 fresh template 中增加一个固定字段。不修改 API、schema、权限、
持久化或依赖。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1–FR-3 | T-1 增加先失败的 flat-source 断言并设置 fresh-template 字段 | AC-1 所有 managed 来源回归通过 | `uv run --extra dev pytest tests/integrations/mpa_managed/test_service.py tests/integrations/mpa_managed/test_agent_deployment.py` |
| FR-1 | T-2 重试真实 Studio 创建 | AC-2 新 Runtime 携带命令并越过版本 0 Error | 本地 Studio 创建与 Runtime 检查 |

## 风险、审查与交付

改动只影响 MPA 专用 fresh template，命令与已知可用参考 Runtime 相同；回退时删除该字段。
已直接审查范围、兼容性、安全与可测试性；用户要求修复创建阻塞并重建 Runtime。针对性
60 条测试及 5259 条全量回归通过。真实 Studio 创建得到 Ready 的 Runtime
`r-yew4qlw5c017agjttpcw`，版本为 2，且 `Command="bash run.sh"`。
