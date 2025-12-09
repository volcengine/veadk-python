# 执行引擎

`Runner` 是 ADK Runtime 中的一个核心组件，负责协调你定义的 Agents、Tools、Callbacks，使它们共同响应用户输入，同时管理信息流、状态变化，以及与外部服务（例如 LLM、Tools）或存储的交互。

VeADK 的执行引擎完全兼容 Google ADK Runner，更多`Runner`工作机制说明您可参考 [Google ADK Agent 运行时](https://google.github.io/adk-docs/runtime/)。

---

## 多租设计

在程序中，若需满足企业级多租户设计需求，可通过 `app_name`、`user_id` 以及 `session_id` 三个核心维度实现数据隔离，各维度对应的隔离范围如下：

| 数据 | 隔离维度 |
| :- | :- |
| 短期记忆 | `app_name` `user_id` `session_id` |
| 长期记忆 | `app_name` `user_id` |
| 知识库 | `app_name` |

## 最简运行

VeADK 中为您提供了一个简单的运行接口 `Runner.run`，用于直接运行一个 Agent 实例，处理用户输入并返回响应。

!!! warning "使用限制"
    本运行接口封装度较高，如您需要在生产级别进行更加灵活的控制，建议使用 `Runner.run_async` 接口，通过异步生成器处理 Agent 每个执行步骤所产生的 Event 事件。

下面是一个最简运行示例：

```python linenums="1" hl_lines="7 9"
import asyncio

from veadk import Agent, Runner

agent = Agent()

runner = Runner(agent=agent)

response = asyncio.run(runner.run(messages="北京的天气怎么样？"))

print(response)
```

## 生产级运行

我们以图片理解为例，演示如何使用 `runner.run_async` 来进行 Event 事件处理：

```python
from google.genai.types import Blob, Content, Part

from veadk import Agent, Runner

APP_NAME = "app"
USER_ID = "user"
SESSION_ID = "session"

agent = Agent()
runner = Runner(agent=agent, app_name=APP_NAME)

user_message = Content(
  role="user",
  parts=[
    Part(
      text="请详细描述这张图片的所有内容，包括物体、颜色、布局和文字信息（如有）。"
    ),
    Part(
      inline_data=Blob(
        display_name=os.path.basename(image_path),
        data=read_png_to_bytes(image_path),
        mime_type="image/png",
      )
    ),
  ],
)

async for event in runner.run_async(
  user_id=runner.user_id,
  session_id=session_id,
  new_message=user_message,
  run_config=RunConfig(max_llm_calls=1),
):
  # 在这里处理您的 Event 事件
```
