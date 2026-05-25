# 飞书 Channel 扩展

`veadk.extensions.FeishuChannelExtension` 用于把飞书机器人的入站消息桥接到 VeADK `Runner`。

它默认基于 `lark_oapi.channel.FeishuChannel` 的 `message` 事件工作，并按下面的规则映射会话身份：

- `sender.union_id -> Runner.user_id`
- `conversation.thread_id -> Runner.session_id`
- 如果线程 ID 不存在，则回退到 `chat_id -> Runner.session_id`

这样做的好处是，VeADK 现有的短期记忆、长期记忆、Tracing 和多租户隔离能力可以直接复用。

## 安装

```bash
pip install veadk-python[extensions]
```

如果你只想安装这个能力，也可以单独安装：

```bash
pip install lark-oapi
```

## 配置

环境变量：

- `TOOL_FEISHU_CHANNEL_APP_ID`
- `TOOL_FEISHU_CHANNEL_APP_SECRET`
- `TOOL_FEISHU_CHANNEL_TRANSPORT`，默认 `ws`
- `TOOL_FEISHU_CHANNEL_STREAMING`，是否开启流式输出，默认 `false`
- `TOOL_FEISHU_CHANNEL_REACTIONS`，是否在收到消息时回复“收到”表情，默认 `false`

或在 `config.yaml` 中配置：

```yaml title="config.yaml"
tool:
  feishu_channel:
    app_id: cli_xxx
    app_secret: xxx
    transport: ws
    streaming: true
    reactions: true
```

## 最小示例

```python
--8<-- "examples/channel/feishu_bot.py"
```

## 说明

- 默认使用飞书 `Channel` 的 WebSocket 模式，因此只要机器人已订阅消息事件，就可以直接启动连接。
- 默认回复会使用 `reply_to=原消息 message_id`，让 VeADK 输出继续挂在当前飞书消息线程下。
- 你可以通过 `session_id_factory` 和 `user_id_factory` 覆盖默认映射逻辑。
