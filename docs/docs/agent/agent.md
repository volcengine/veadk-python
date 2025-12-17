# 构建您的第一个 Agent

本文档将阐述如何以最简方式构建并运行一个智能体（Agent）。内容涵盖两种主要定义方法：

- 代码定义
- 基于 Agent Builder 的 YAML 定义

本文档不依赖任何外部复杂组件，旨在帮助您建立最小可运行样例的整体认知。

## Agent 的定义方法

智能体的定义是其生命周期的起点。无论在何种规模的系统中，智能体都是任务拆解、规划的主体。

本节主要介绍两种定义方式：**代码方式**与 **YAML 配置方式**。

### 通过代码构建

在代码中直接定义智能体是最常见且最灵活的方式。此方法便于动态调整参数、集成外部模块并进行单元测试。您可以创建一个最简单的 Agent，无需额外设置。**Agent 缺省属性将来自环境变量或默认值。**如下代码实现了一个最简化的 Agent 定义与运行：

=== "Python"

    ```python title="agent.py" linenums="1" hl_lines="5"
    import asyncio

    from veadk import Agent, Runner

    agent = Agent()
    runner = Runner(agent=agent)

    response = asyncio.run(runner.run(messages="Hi!"))
    print(response)
    ```

=== "Golang"

    ```golang title="agent.go" linenums="1" hl_lines="18"
    package main

    import (
        "context"
        "fmt"
    
        "github.com/google/uuid"
        _ "github.com/volcengine/veadk-go/agent"
        veagent "github.com/volcengine/veadk-go/agent/llmagent"
        "google.golang.org/adk/agent"
        "google.golang.org/adk/runner"
        "google.golang.org/adk/session"
        "google.golang.org/genai"
    )
    
    func main() {
        ctx := context.Background()
        veAgent, err := veagent.New(&veagent.Config{})
        if err != nil {
            fmt.Printf("NewVeAgent failed: %v", err)
            return
        }
    
        appName := "veAgent_app"
        userID := "user-1234"
        sessionId := fmt.Sprintf("%s-%s", session.KeyPrefixTemp, uuid.NewString())
        sessionService := session.InMemoryService()
        agentRunner, err := runner.New(runner.Config{
            AppName:        appName,
            Agent:          veAgent,
            SessionService: sessionService,
        })
        if err != nil {
            fmt.Printf("New runner error:%v", err)
            return
        }
    
        _, err = sessionService.Create(ctx, &session.CreateRequest{
            AppName:   appName,
            UserID:    userID,
            SessionID: sessionId,
        })
        if err != nil {
            fmt.Printf("Create session error:%v", err)
            return
        }
    
        for event, err := range agentRunner.Run(ctx, userID, sessionId, genai.NewContentFromText("你好", genai.RoleUser), agent.RunConfig{StreamingMode: agent.StreamingModeNone}) {
            if err != nil {
                fmt.Printf("got unexpected error: %v", err)
            }
            fmt.Printf("got event: %s\n", event.Content.Parts[0].Text)
        }
    }
    ```


=== "所需环境变量"

    环境变量列表：

    - `MODEL_AGENT_API_KEY`: 用户 Agent 推理模型的 API Key
    - ...
    
    或在 `config.yaml` 中定义：

    ```yaml title="config.yaml"
    model:
      agent:
        api_key: ...
    ```

#### 设置 Agent 元信息

您也可以通过以下方式设置更多 Agent 元数据信息：

=== "Python"

    ```python title="agent.py" linenums="1" hl_lines="4-6"
    from veadk import Agent, Runner
    
    root_agent = Agent(
        name="life_assistant",
        description="生活助手",
        instruction="你是一个生活助手，你可以回答用户的问题。",
    )
    ```

=== "Golang"

    ```golang title="agent.go" linenums="1" hl_lines="2-4"
    cfg := &veagent.Config{}
	cfg.Name = "life_assistant"
	cfg.Description = "生活助手"
	cfg.Instruction = "你是一个生活助手，你可以回答用户的问题。"

	veAgent, err := veagent.New(cfg)
	if err != nil {
		fmt.Printf("NewVeAgent failed: %v", err)
		return
	}
    ```


其中，`name` 代表 Agent 的名称，`description` 是对 Agent 功能的简单描述（在Agent Tree中唯一标识某个Agent），`instruction` 是 Agent 的系统提示词，用于定义其行为和响应风格。

#### 使用不同模型

如果您想使用本地模型或其他提供商的模型，可以在初始化时指定模型相关配置：

=== "Python"

    ```python title="agent.py" linenums="1" hl_lines="4-7"
    from veadk import Agent
    
    agent = Agent(
        model_provider="...",
        model_name="...",
        model_api_key="...",
        model_api_base="..."
    )
    ```

=== "Golang"

    ```golang title="agent.go" linenums="1" hl_lines="2-4"
    cfg := &veagent.Config{
		ModelName: "...",
		ModelAPIBase: "...",
		ModelAPIKey: "...",
	}
    
    veAgent, err := veagent.New(cfg)
	if err != nil {
		fmt.Printf("NewVeAgent failed: %v", err)
		return
	}
    ```

由于 python VeADK 的 Agent 基于 [LiteLLM]() 实现，因此您可以使用 LiteLLM 支持的所有模型提供商。您可以查看 [LiteLLM 支持的模型提供商列表](https://docs.litellm.ai/docs/providers)来设置 `model_provider` 参数。

golang 暂不支持 LiteLLM，因此 VeADK 的 Agent 基于 OpenAI 实现，因此您可以使用所有支持OpenAI协议的模型。

#### 设置模型客户端

VeADK 支持您直接定义 LiteLLM 的客户端，来实现高度自定义的模型配置：

```python title="agent.py" linenums="1" hl_lines="5 8"
from google.adk.models.lite_llm import LiteLlm
from veadk import Agent

# 自定义您的模型客户端
llm = LiteLlm()

# 直接将模型客户端传递给 Agent
agent = Agent(model=llm)
```

#### 配置模型额外参数

此外，您还可以根据[火山引擎方舟大模型平台](https://www.volcengine.com/product/ark)的能力，指定一些[额外选项](https://www.volcengine.com/docs/82379/1494384?lang=zh)，例如您可以禁用豆包 1.6 系列模型的思考能力，以实现更加快速的响应：

=== "Python"

    ```python title="agent.py" linenums="1" hl_lines="7"
    import asyncio
    
    from veadk import Agent, Runner
    
    agent = Agent(
        model_name="doubao-seed-1.6-250615",
        model_extra_config={"extra_body": {"thinking": {"type": "disabled"}}},
    )
    runner = Runner(agent=agent)
    
    response = asyncio.run(runner.run(messages="hi!"))
    print(response)
    ```

=== "Golang"

    ```golang title="agent.go" linenums="1" hl_lines="6-14"
    import (
        _ "github.com/volcengine/veadk-go/agent"
        veagent "github.com/volcengine/veadk-go/agent/llmagent"
    )
    
    veAgent, err := veagent.New(&veagent.Config{
		ModelExtraConfig: map[string]any{
			"extra_body": map[string]any{
				"thinking": map[string]string{
					"type": "disabled",
				},
			},
		},
	})
	if err != nil {
		fmt.Printf("NewVeAgent failed: %v", err)
		return
	}
    ```


### 通过配置文件

在您构建 Agent 过程中，往往需要更加简洁的 Agent 定义方式与配置管理。为了方便这种场景，VeADK 提供了 YAML 文件定义方式。该方法以声明式语法描述智能体的全部元信息与行为结构。

**基本结构**：
本小节将给出一个简单的yaml文件weather_reporter_agent.yaml，用于演示如何定义一个查询天气信息的agent。

```yaml title="weather_reporter_agent.yaml"
root_agent:
  type: Agent # Agent | SequencialAgent | LoopAgent | ParallelAgent
  name: weather_reporter
  description: An intelligent_assistant which can provider weather information.
  instruction: Help user according to your tools.
  model_name: doubao-1-5-pro-32k-250115
  model_api_key: xxx # 您的模型API Key
  tools:
    - name: veadk.tools.demo_tools.get_city_weather # tool 所在的模块及函数名称
```

**结构说明**：

- `type`: 智能体类别
- `name`: 智能体名称
- `description`: 智能体的总体描述
- `instruction`：智能体的系统提示词（System prompt）
- `model_name`: 模型名称, 如doubao-1-5-pro-32k-250115, deepseek-r1-250528 等
- `tools`: 工具列表与调用规则

**使用方法**：下面将根据上面的weather_reporter_agent.yaml文件，演示如何使用该agent查询北京的天气。

```python title="agent.py" linenums="1"
import asyncio

from veadk import Runner
from veadk.agent_builder import AgentBuilder

agent_builder = AgentBuilder()

agent = agent_builder.build(path="weather_reporter_agent.yaml")

runner = Runner(agent)
response = asyncio.run(runner.run("今天北京天气如何？"))

print(response)
```

### 构建 Agent 的方法对比

**对比总结**：

| 特性   | 代码方式  | YAML 方式 |
| ---- | ----- | ------- |
| 灵活性  | 高     | 中       |
| 可读性  | 中     | 高       |
| 可维护性 | 中     | 高       |
| 动态生成 | 支持    | 一般      |
| 适用场景 | 开发、生产 | 实验、配置化、生产  |
