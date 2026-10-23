# Skill Shell 工具命名

[English](2026-10-20-skill-shell-tool-naming.md)

- 变更：skill-shell-tool-naming；日期：2026-10-20；状态：approved。
- 范围批准：用户在讨论规范命名、可选别名、Sandbox 有限纠错和错误详情保留后要求修复。用户已授权本地提交；不包含推送、SDK 发布或部署。

## 证据与目标

`SkillsToolset` 发布 `FunctionTool(bash_tool)`，声明名称为 `bash_tool`。`SkillsTool` 的工具说明和加载技能后的 footer 都写着 "use the bash tool"。一次远端运行先正确调用多次 `bash_tool`，随后调用不存在的 `bash` 并失败。说明文案的歧义已经确认，但不能证明它是模型误调用的唯一原因，也不能证明这是相对 SDK 1.0.10 的回归。

FR-1：SDK 生成的执行指引必须在工具说明与加载技能后的 footer 中使用真实可调用名称 `bash_tool`。原样保留技能作者的正文。
FR-2：保留工具名称、schema、执行、导入路径和函数签名的兼容性。不新增 `bash` 别名，不重命名现有工具。

## 设计与契约

从已有 Shell 函数取得规范名称，不再额外维护一个拼写。仅修改 SDK 自己生成的说明。SkillsToolset 的发现、注册表、安装、工作目录、环境、文件处理、授权与执行契约不变；本次只是让描述与既有接口一致，不需要修改组件契约。

最终范围：用户因发布成本明确排除 `actb-mono`，已撤回该库的 Sandbox 回调代码、测试及变更记录。仅保留 SDK 命名修复和 samples 桥接层有界、脱敏的错误详情。模型误用不存在的工具名仍可能失败，不提供自动纠错。SDK 源码变更不会自动更新已部署的 Sandbox 镜像。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| FR-1 | T-1：增加回归测试 | AC-1：说明中的工具名称等于实际 FunctionTool 声明 | `uv run --extra dev pytest tests/skills/test_skill_tool_names.py` | passed |
| FR-1 | T-2：修正文案 | AC-2：加载的 Skill 正文不变，footer 使用规范名称 | 同上测试 | passed |
| FR-2 | T-3：回归与评审 | AC-3：既有 Skill 安装与加载测试通过，工具声明不变 | 相关 skills 测试；Ruff；diff 空白检查 | passed |

## 评审、风险与交付

已直接完成设计评审：命名与证据符合当前代码；范围保留接口与权限；测试对照真实工具声明。当前没有 review-spec 技能，因此直接检查了可行性、兼容性、失败边界、可测试性与双语一致性。没有未解决的设计阻碍。用户批准记录见上文。

技能作者正文中的泛称 "bash" 不属于 SDK 生成文案。模型输出具有概率性，仍可能误用工具名；自动纠错不在最终批准范围内。镜像构建、发布属于独立部署动作。云端创建会话超时不在本次范围内。

## 验证结果

新增测试先失败后修复通过；工具命名、安装、回调及 ADK toolset 相关测试共 30 项通过。Ruff 的 E/F/I 检查和 diff 空白检查通过。未发布 SDK；已部署 Sandbox 需后续使用新版 SDK 构建镜像。
