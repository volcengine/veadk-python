# 飞书渠道流式输出

[English](README.md)

组件：`feishu-channel`。修订：2026-10-10。状态：已实现，本地验证通过。
变更：[非 UI 迁移 PRD](../../prd-spec/features/managed-agents-upstream/2026-10-10-non-ui-migration.zh.md)，`FR-5` / `AC-3`。

## 范围
将非 UI 的飞书渠道增强移植到官方 VeADK，保留上游优雅关闭与应用事件循环任务追踪。
扩展负责呈现 Runner 事件与渠道生命周期；Runner 负责执行，Lark SDK 负责消息和卡片投递。范围不包含 Studio UI 或后台接线。

## 行为约定
- `CON-FEISHU-1`：默认仅输出回答；思考、工具输入、工具结果通过构造参数或环境变量显式启用。服务商返回的思考文本展示前规范化空白；无法获得模型未返回的内部推理。
- `CON-FEISHU-2`：可将思考与每次工具调用拆成独立卡片，回复到已有或主动创建的话题。调用 ID 关联乱序结果；找不到对应调用的结果使用独立卡片。缺失阶段不产生内容卡片。
- `CON-FEISHU-3`：服务商重复发送的完成事件不得重复显示思考或累计回答。工具记录按非空调用/结果 ID 去重；无 ID 事件不能提供相同的关联保证。
- `CON-FEISHU-4`：工具结构化字段按敏感字段名递归脱敏、限制长度并转义 Markdown 代码围栏。序列化回退必须使用已脱敏副本；任意字符串内嵌的秘密不在字段脱敏范围内。
- `CON-FEISHU-5`：成功与异常路径均回收流式任务。卡片错误向上传播，若 Runner 错误或取消正在传播则保留原始失败。保留上游先关闭套接字、再等待应用循环内已接收消息完成的行为；超时后取消未完成消息。

## 接口与配置

公开入口：`veadk.extensions.FeishuChannelExtension(runner=..., streaming=True, show_tool_calls=True)`。流式控制仅影响 `channel.stream`；普通处理函数及非流式 Runner 回复保留文本格式器。

| 构造参数 | 环境变量 | 默认值 |
| --- | --- | --- |
| `show_thinking` | `TOOL_FEISHU_CHANNEL_SHOW_THINKING` | `False` |
| `show_tool_calls` | `TOOL_FEISHU_CHANNEL_SHOW_TOOL_CALLS` | `False` |
| `show_tool_results` | `TOOL_FEISHU_CHANNEL_SHOW_TOOL_RESULTS` | `False` |
| `separate_tool_call_cards` | `TOOL_FEISHU_CHANNEL_SEPARATE_TOOL_CALL_CARDS` | `False` |
| `separate_thinking_card` | `TOOL_FEISHU_CHANNEL_SEPARATE_THINKING_CARD` | `False` |
| `create_topic` | `TOOL_FEISHU_CHANNEL_CREATE_TOPIC` | `False` |
| `tool_detail_max_length` | 无 | `4000`，最小 `100` |

布尔参数由构造参数 true 或环境值 `1`、`true`、`yes`、`on`（不区分大小写）启用；显式 false 不覆盖已启用的环境变量。创建话题要求 `reply_in_thread=True` 且有入站消息 ID，向 Lark 传递 `reply_to` 与 `reply_in_thread=True`。已有话题 ID 也启用话题内回复。格式器不持久化载荷或凭据。

## 兼容与失败

保留上游生命周期、身份映射、父消息/历史获取、重连行为与依赖回退。失败图标识别真值 `error`、`error`/`failed`/`failure` 状态与非零 `exit_code`，不改变执行状态。敏感标记为 `api_key`、`apikey`、`access_key`、`authorization`、`cookie`、`credential`、`password`、`secret`、`token`，字段名转小写并将连字符替换为下划线后匹配。本地测试不能保证真实卡片投递。关闭默认超时保留上游 `TOOL_FEISHU_CHANNEL_DRAIN_TIMEOUT` 的 300 秒。

## 验证
执行现有飞书扩展测试及源仓库回归测试，覆盖输出顺序、去重、独立卡片、失败工具结果、话题参数、脱敏与长度限制。真实飞书投递依赖凭据，不属于本地验证。

命令：`.venv/bin/python -m pytest tests/test_feishu_channel_extension.py -q`。
`CON-FEISHU-1..3` 对应详细流式、独立卡片、话题及缺失阶段测试；`CON-FEISHU-4` 对应截断与序列化回退测试；`CON-FEISHU-5` 对应优雅关闭、Runner 失败回收、卡片清理错误传播测试。

## 变更记录

2026-10-10：将源仓库渠道控制移植到官方 `171d8d86`，保留其生命周期变更；修复脱敏回退与后台卡片清理错误传播。上游基线 8 个测试通过。源仓库回归测试在新辅助函数安装前失败，迁移后通过。新增异常路径测试在修复前揭示格式器回退泄露与卡片错误吞没。父级迁移 PRD 记录本地验证结果；真实投递为 not_run。
