# 命令行工具VeADK

## 提示词优化

用来优化 Agent 的系统提示词（System prompt）。

```bash
veadk prompt
```

选项包括：

- `--path`：指定要优化的 Agent 文件路径，默认值为当前目录下的 `agent.py` 文件。注意，必须将你定义的智能体作为全局变量导出
- `--feedback`：指定优化后的提示词反馈，用于优化模型
- `--api-key`：指定 AgentPilot 平台的 API Key，用于调用优化模型
- `--model-name`：指定优化模型的名称，默认值为 `doubao-1.5-pro-32k-250115`

## 一键上云部署

可直接将本地项目部署到火山引擎 FaaS 平台上：

```bash
veadk deploy
```

选项包括：

- `--access-key`：指定火山引擎的 Access Key，用于调用 FaaS 平台的 API
- `--secret-key`：指定火山引擎的 Secret Key，用于调用 FaaS 平台的 API
- `--name`：指定部署的应用名称，用于在 FaaS 平台上标识该部署
- `--path`：指定项目路径，默认值为当前目录

## 本地调试

可以通过`adk web`或`veadk studio`来启动Web页面，运行智能体：

```bash
# basic usage:
adk web

# if you need to use long-term memory, you should use `veadk web`.
# if the `session_service_uri` is not set, it will use `opensearch` as your long-term memory backend
veadk web --session_service_uri="mysql+pymysql://{user}:{password}@{host}/{database}"

# or, use our own web:
veadk studio
```

它们能够自动读取执行命令目录中的`agent.py`文件，并加载`root_agent`全局变量。
