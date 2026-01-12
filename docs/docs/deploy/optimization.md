---
title: 持续优化
---

## Prompt 优解

Prompt（提示词）作为大模型的核心输入指令，直接影响模型的理解准确性和输出质量。优质的 Prompt 能显著提升大语言模型处理复杂任务的能力。

[PromptPilot](https://www.volcengine.com/docs/82379/1399495?lang=zh) 提供全流程智能优化，涵盖生成、调优、评估和管理全阶段。

### 调用方法

```shell
veadk prompt
```

选项包括：

```shell
--path：指定要优化的 Agent 文件路径，默认值为当前目录下 agent.py。注意，必须将定义的智能体作为全局变量导出
--feedback：指定优化后的提示词反馈，用于优化模型
--api-key：指定 AgentPilot 平台的 API Key，用于调用优化模型
--model-name：指定优化模型的名称
```

## 强化学习

在对效果与泛化能力要求高的复杂业务场景中，强化学习（RL）相比 PE、SFT、DPO 等方式上限更高，更贴合业务核心诉求：

- 基于反馈迭代的训练模式，更好激发模型推理与泛化能力；
- 无需大量标注数据，成本更低、实现更简单；
- 支持按业务指标反馈打分优化，可直接驱动指标提升。

针对上述问题与需求，VeADK 提供了内置的强化学习解决方案，包括：

- 基于 [方舟平台强化学习](https://www.volcengine.com/docs/82379/1099460) 的解决方案
- 基于 [Agent Lightning](https://github.com/microsoft/agent-lightning) 的解决方案

### 基于方舟平台强化学习

方舟 RL 将强化学习过程进行了一定程度的封装，降低了复杂度。用户主要关注 rollout 中的 agent 逻辑、奖励函数的构建、训练样本的选择即可。

VeADK 与方舟平台 Agent RL 集成，用户使用 VeADK 提供的脚手架，可以开发 VeADK Agent，然后提交任务到方舟平台进行强化学习优化。

#### 准备工作

在你的终端中运行以下命令，初始化一个强化学习项目：

```bash
veadk rl init --platform ark --workspace veadk_rl_ark_project
```

该命令会在当前目录下创建一个名为 `veadk_rl_ark_project` 的文件夹，其中包含了一个基本的强化学习项目结构。
然后在终端中运行以下命令，提交任务到方舟平台：

```bash
cd veadk_rl_ark_project
veadk rl submit --platform ark
```

#### 原理说明

生成后的项目结构如下，其中核心文件包括：

- 数据集: `data/*.jsonl`
- `/plugins`文件夹下的rollout和reward:
  - rollout ：用以规定agent的工作流，`raw_async_veadk_rollout.py`提供了使用在方舟rl中使用veadk agent的示例，
  - reward：给出强化学习所需的奖励值，在`random_reward.py`给出了示例
- `job.py`或`job.yaml`：用以配置训练参数，并指定需要使用的rollout和reward

```shell
veadk_rl_ark_project
├── data
    ├── *.jsonl # 训练数据
└── plugins
    ├── async_weather_rollout.py # 
    ├── config.yaml.example # VeADK agent 配置信息示例
    ├── random_reward.py # reward规则设定
    ├── raw_async_veadk_rollout.py # rollout工作流设定
    ├── raw_rollout.py # 
    └── test_utils.py #
    └── weather_rollout.py # 
├── job.py # 任务提交代码
├── job.yaml # 任务配置
├── test_agent.py # VeFaaS 测试脚本
```

#### 最佳实践案例

1. 脚手架中，基于 VeADK 的天气查询 Agent 进行强化学习优化
2. 提交任务 (veadk rl submit --platform ark)

![提交任务](../assets/images/optimization/submit_task.png)

![训练中](../assets/images/optimization/training.png)
3. 查看训练日志和时间线

![查看训练日志](../assets/images/optimization/logs.png)

![查看训练时间线](../assets/images/optimization/timeline.png)

### Agent Lightning

Agent Lightning 提供了灵活且可扩展的框架，实现了智能体（client）和训练（server）的完全解耦。
VeADK 与 Agent Lightning 集成，用户使用 VeADK 提供的脚手架，可以开发 VeADK Agent，然后运行 client 与 server 进行强化学习优化。

#### 准备工作

在你的终端中运行以下命令，初始化一个 Agent Lightning 项目：

```bash
veadk rl init --platform lightning --workspace veadk_rl_lightning_project
```

该命令会在当前目录下创建一个名为 `veadk_rl_lightning_project` 的文件夹，其中包含了一个基本的基于 VeADK 和 Agent Lightning 的强化学习项目结构。
然后在终端1中运行以下命令，启动 client：

```bash
cd veadk_rl_lightning_project
python veadk_agent.py
```

然后在终端2中运行以下命令

- 首先重启 ray 集群：

```bash
cd veadk_rl_lightning_project
bash restart_ray.sh
```  

- 启动 server：

```bash
cd veadk_rl_lightning_project
bash train.sh
```

#### 原理说明

生成后的项目结构如下，其中核心文件包括：

- agent_client: `*_agent.py` 中定义了agent的rollout逻辑和reward规则
- training_server: `train.sh` 定义了训练相关参数,用于启动训练服务器

```shell
veadk_rl_lightning_project
├── data 
    ├── demo_train.parquet # 训练数据,必须为 parquet 格式
    ├── demo_test.parquet # 测试数据,必须为 parquet 格式
└── demo_calculate_agent.py # agent的rollout逻辑和reward设定
└── train.sh # 训练服务器启动脚本,设定训练相关参数 
└── restart_ray.sh # 重启 ray 集群脚本
```

#### 最佳实践案例

1. 脚手架中，基于 VeADK 的算术 Agent 进行强化学习优化
2. 启动 client (python demo_calculate_agent.py), 重启ray集群(bash restart_ray.sh), 最后启动训练服务器server (bash train.sh)，分别在终端1与终端2中运行以上命令

![启动client](../assets/images/optimization/lightning_client.png)

![启动server](../assets/images/optimization/lightning_training_server.png)

## Agent 自我反思

VeADK 中支持基于 Tracing 文件数据，通过第三方 Agent 推理来进行自我反思，生成优化后的系统提示词。

### 使用方法

您可以在适宜的时机将 Agent 推理得到的 Tracing 文件数据，提交到 `reflector` 进行自我反思，如下代码：

```python
import asyncio

from veadk import Agent, Runner
from veadk.reflector.local_reflector import LocalReflector
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

agent = Agent(tracers=[OpentelemetryTracer()])
reflector = LocalReflector(agent=agent)

app_name = "app"
user_id = "user"
session_id = "session"


async def main():
    runner = Runner(agent=agent, app_name=app_name)

    await runner.run(
        messages="你好，我觉得你的回答不够礼貌",
        user_id=user_id,
        session_id=session_id,
    )

    trace_file = runner.save_tracing_file(session_id=session_id)

    response = await reflector.reflect(
        trace_file=trace_file
    )
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
```

### 结果说明

原始提示词：

```text
You an AI agent created by the VeADK team.

You excel at the following tasks:
1. Data science
- Information gathering and fact-checking
- Data processing and analysis
2. Documentation
- Writing multi-chapter articles and in-depth research reports
3. Coding & Programming
- Creating websites, applications, and tools
- Solve problems and bugs in code (e.g., Python, JavaScript, SQL, ...)
- If necessary, using programming to solve various problems beyond development
4. If user gives you tools, finish various tasks that can be accomplished using tools and available resources
```

优化后，您将看到类似如下的输出：

```text
optimized_prompt='You are an AI agent created by the VeADK team. Your core mission is to assist users with expertise in data science, documentation, and coding, while maintaining a warm, respectful, and engaging communication style.\n\nYou excel at the following tasks:\n1. Data science\n- Information gathering and fact-checking\n- Data processing and analysis\n2. Documentation\n- Writing multi-chapter articles and in-depth research reports\n3. Coding & Programming\n- Creating websites, applications, and tools\n- Solving problems and bugs in code (e.g., Python, JavaScript, SQL, ...)\n- Using programming to solve various problems beyond development\n4. Tool usage\n- Effectively using provided tools and available resources to accomplish tasks\n\nCommunication Guidelines:\n- Always use polite and warm language (e.g., appropriate honorifics, friendly tone)\n- Show appreciation for user feedback and suggestions\n- Proactively confirm user needs and preferences\n- Maintain a helpful and encouraging attitude throughout interactions\n\nYour responses should be both technically accurate and conversationally pleasant, ensuring users feel valued and supported.' 

reason="The trace shows a user complaint about the agent's lack of politeness in responses. The agent's current system prompt focuses exclusively on technical capabilities without addressing communication style. The optimized prompt adds explicit communication guidelines to ensure the agent maintains a warm, respectful tone while preserving all technical capabilities. This addresses the user's feedback directly while maintaining the agent's core functionality."
```

输出分为两部分：

- `optimized_prompt`: 优化后的系统提示词
- `reason`: 优化原因
