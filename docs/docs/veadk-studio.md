# VeADK Studio

VeADK Studio是我们提供的一站式Agent开发平台，提供本地Agent优化、观测等功能。

![VeADK Studio主页](/images/veadk-studio.png)

## 前置准备

你需要在你的Agent项目中准备一个`agent.py`文件，导出`agent`和`short_term_memory`两个全局变量：

```python
agent = ...

short_term_memory = ...
```

## 启动

在你准备好的Agent项目目录下执行以下命令：

```bash
veadk-studio
```

Studio将会自动加载你的`agent.py`文件，启动一个本地服务器。注意，服务地址与端口必须固定为`127.0.0.1:8000`。

访问`http://127.0.0.1:8000`即可打开Studio：

![VeADK Studio主页](/images/veadk-studio.png)

## 功能介绍

VeADK Studio的主页包括两个入口：

- **Local agent**：你的本地Agent项目
- **Remote agent**：连接一个已经部署到VeFaaS的Agent（即将上线）

点击Local agent后，即可体验本地优化观测等各项功能：

![VeADK Studio智能体页面](/images/veadk-chat.png)

### 交互

Studio中采用流式（SSE通信）与你定义的Agent进行交互，期间会自动加载短期与长期记忆。

只要服务端保持连接，历史会话便不会消失。

### 工具调用

当发生工具调用时，可显示工具的状态和输入输出。

![VeADK Studio智能体页面](/images/veadk-tool.png)

### Prompt优化

VeADK通过AgentPilot提供Prompt优化功能，你可以在Studio中对Prompt进行优化与替换。

![VeADK Studio智能体页面](/images/veadk-refine-prompt.png)

### 调用追踪

本地可查看调用链与具体的事件信息、Tracing Span的属性信息等。

![VeADK Studio智能体页面](/images/veadk-tracing.png)

### 效果评估

VeADK通过DeepEval提供效果评估功能，你可以在Studio中对Agent的效果进行评估（例如输入输出情况）。

![VeADK Studio智能体页面](/images/veadk-evaluation.png)

在生成评估结果后，评估器输出的评估Reason可作为进一步Prompt优化的Feedback反馈：

![VeADK Studio智能体页面](/images/veadk-eval-to-refine.png)

### 云端部署

该功能即将上线。


