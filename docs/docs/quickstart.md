---
title: 快速开始
---

## 安装

您可以从 PyPI 中安装最新版的 VeADK：

```bash
pip install veadk-python
```

您可以通过运行如下命令来检测您的 VeADK 是否安装成功：

```bash
veadk --version
```

??? note "了解如何安装 Python"
    请查看[Python 安装指南](https://www.python.org/downloads/)了解如何安装 Python。

??? note "了解如何从源码构建 VeADK"
    请查看[安装](https://volcengine.github.io/veadk-python/introduction/installation)章节中“从源码构建”部分，了解如何从源码构建 VeADK。

??? note "了解如何为 VeADK 贡献代码"
    请查看[贡献指南](contributing.md)了解如何为 VeADK 项目贡献代码。

## 生成并运行

您可以执行如下命令，来生成一个我们为您预制好的 Agent 项目模板：

```bash
veadk create
```

您将被提示输入如下信息：

- 项目名称（这也将会成为您的本地目录名称）
- 方舟平台 API Key（您也可以稍后手动填写到配置文件中）

输入完毕后，您本地的项目结构如下：

```title="your_project/"
your_project
├── __init__.py # 模块导出文件
├── .env        # 环境变量文件，您需要在此处提供您的模型 API Key
└── agent.py    # Agent 定义文件
```

您需要在 `.env` 中填入您的模型 API Key：

<a class="openai-button" href="https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey?apikey=%7B%7D">获取方舟 API Key</a>

```txt title=".env"
MODEL_AGENT_API_KEY = ...
```

我们为您生成的 Agent 项目中，`agent.py` 提供了一个可以查询模拟天气数据的智能体，结构如下：

```python title="agent.py"
from veadk import Agent # 导入 Agent 模块

root_agent = Agent(
    name="root_agent",  # Agent 名称 
    description="A helpful assistant for user questions.",  # Agent 描述
    instruction="Answer user questions to the best of your knowledge",  # Agent 系统提示词
    model_name="doubao-seed-1-6-251015",    # 模型名称
)
```

之后，您可以通过如下命令来启动一个浏览器页面，与您的 Agent 进行交互：

??? tip "常用配置"
    - 改变服务地址：`veadk web --host 0.0.0.0`
    - 改变服务端口：`veadk web --port 8000`
    - 改变日志输出级别：`veadk web --log_level DEBUG` (1)
      { .annotate }
    
        1. VeADK 重载默认等级为 `ERROR`

```bash
veadk web
```

交互界面如图：

![veadk交互界面](../assets/images/overview/veadk-web.png)