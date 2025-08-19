# 部署上云

## 命令行部署

VeADK提供了一个云引擎，配合命令行脚手架，你可以：

- **快速开始** 启动一个新的样例模板项目进行开发
- **从已有项目** 将你本地的 Agent 项目上传至[火山引擎函数服务平台](https://www.volcengine.com/product/vefaas)

部署时，你可以指定两种部署模式来对外提供服务：

- **A2A与MCP Server**
  - A2A Server 提供遵循 A2A 标准的 `message_send` 等接口
  - MCP Server 提供一个 `run_agent` 工具方法
- **VeADK Web**
  - 提供Web界面，方便你在浏览器中进行体验

### 快速开始

#### 初始化

你可以运行`veadk init`命令来初始化一个新的Agent项目：

```bash
$ veadk init
Welcome use VeADK to create your project. We will generate a `weather-reporter` application for you.
Local directory name [veadk-cloud-proj]: 
Volcengine FaaS application name [veadk-cloud-agent]: 
Volcengine API Gateway instance name []: 
Volcengine API Gateway service name []: 
Volcengine API Gateway upstream name []: 
Choose a deploy mode:
  1. A2A/MCP Server
  2. VeADK Web / Google ADK Web
Enter your choice (1, 2): 1
Template project has been generated at .../veadk-cloud-proj
Edit .../veadk-cloud-proj/src to define your agents
Edit .../veadk-cloud-proj/deploy.py to define your deployment attributes
Run python `deploy.py` for deployment on Volcengine FaaS platform.
```

它会提示你输入如下几个参数：

- 本地项目名称（即项目的本地目录名称）
- VeFaaS应用名称（不可带下划线）
- 火山引擎网关实例名称（可选）
- 火山引擎网关服务名称（可选）
- 火山引擎网关Upstream名称（可选）
- 部署模式
  1. A2A / MCP Server
  2. VeADK Web

生成后的项目结构如下：

```bash
└── veadk-cloud-proj
    ├── config.yaml.example # 定义环境变量
    ├── deploy.py # 部署脚本
    └── src
        ├── agent.py # agent 运行时数据导出
        ├── app.py # Server 定义
        ├── requirements.txt # 依赖
        ├── run.sh # 启动脚本
        └── weather_report # agent module
            ├── __init__.py # 必须包含`from . import agent`
            └── agent.py # agent 定义
```

你所创建的 `config.yaml` 不会被上传到云端，其中的属性值将会以环境变量的形式上传至VeFaaS平台。

只有 `src/` 路径下的文件才会被上传到云端。

#### 自定义项目

在使用脚手架生成模板项目后，你可以做如下操作：

1. 向 `src` 目录中直接导入一个能够被 ADK Web 识别的目录（例如 `weather_agent` 目录），主要包括：
   - 包含 `root_agent` 这个全局变量的 `agent.py` 文件
   - 包含 `from . import agent` 的 `__init__.py` 文件
2. 在 `src/agent.py` 中实例化 `AgentRunConfig` 类，主要属性包括：
   - `app_name`：部署在云上的 Agent 应用名称（与VeFaaS应用名称不一定对应，此处为服务级别）
   - `agent`：你提供服务的 Agent 实例
   - `short_term_memory`：短期记忆，为空则默认初始化in-memory短期记忆，重启后即消失
   - `requirement_file_path`：依赖文件路径，VeADK 能够自动将其移动到 `src/requirements.txt`
3. 使用`python deploy.py`进行云端部署

如果你想在部署到云端前进行本地运行来测试代码问题，可以在 `deploy.py` 中的 `engine.deploy` 调用处，添加参数：`local_test=True`。添加后，在部署前将会启动相关服务，测试启动是否正常。

#### 云端环境变量

| 环境变量名称 | 说明 | 值 | 备注 |
| - | - | - | - |
| VEADK_TRACER_APMPLUS | 是否使用火山 APMPlus Tracing | `true` \| `false` | 默认为 `false`|
| VEADK_TRACER_COZELOOP | 是否使用火山 CozeLoop Tracing | `true` \| `false` | 默认为 `false` |
| VEADK_TRACER_TLS | 是否使用 TLS Tracing | `true` \| `false` | 默认为 `false` |
| SHORT_TERM_MEMORY_BACKEND | 启动 ADK Web 时的短期记忆后端 | `local` \| `mysql` | 优先级低于在 `agent.py` 中定义的短期记忆 |
| LONG_TERM_MEMORY_BACKEND | 启动 ADK Web 时的长期记忆后端 | `opensearch` \| `viking` | 优先级低于在 `agent.py` 中定义的长期记忆 |

### 从已有项目

如果你已经在本地有一个 agent 项目，你可以使用`veadk deploy`命令将你当前的项目上传至云端。

使用命令前，请先确保你的本地 agent 项目中包括：

1. 一个含有全局变量 `root_agent` 的 `agent.py` 文件
2. 一个含有 `from . import agent` 语句的 `__init__.py` 文件

`veadk deploy`接收的参数如下：

| 名称 | 类型 | 释义 |
| - | - | - |
| `--access-key` | 字符串 | 火山引擎AK |
| `--secret-key` | 字符串 | 火山引擎SK |
| `--vefaas-app-name` | 字符串 | 火山引擎 VeFaaS 平台应用名称 |
| `--veapig-instance-name` | 字符串 | 火山引擎 APIG 实例名称 |
| `--veapig-service-name` | 字符串 | 火山引擎 APIG 服务名称 |
| `--veapig-upstream-name` | 字符串 | 火山引擎 APIG Upstream 名称 |
| `--short-term-memory-backend` | `local` \| `mysql` | 短期记忆后端 |
| `--use-adk-web` | FLAG | 设置后将会在云端启动 web，否则为 A2A / MCP 模式 |
| `--path` | 字符串 | 本地项目路径，默认为当前目录 |

## 代码部署

### Cloud Agent Engine

如果你已经有一个较为成熟的Agent项目，你可以通过VeADK中提供的云引擎来部署你的项目。项目结构的最佳实践可参考[这里](#项目结构)。

```python
from veadk.cloud.cloud_agent_engine import CloudAgentEngine

engine = CloudAgentEngine()

# Create application thru local folder and unique application name
cloud_app = engine.deploy(...)
```

类`CloudAgentEngine`初始化需要传入你的火山引擎AK/SK；如果你没有传入，那么VeADK将自动从你的环境变量中获取。

进行`deploy`函数调用时，关键参数如下：

| 参数名称 | 类型 | 说明 |
| --- | --- | --- |
| path | str | 本地Agent项目路径 |
| application_name | str | 云应用名称 |
| gateway_name | str | 火山引擎网关实例名称 |
| gateway_service_name | str | 火山引擎网关服务名称 |
| gateway_upstream_name | str | 火山引擎网关Upstream名称 |
| use_adk_web | bool | 是否在云端使用VeADK Web / Google Web |

### Cloud App

当你使用`CloudAgentEngine`部署完成后，将返回一个`CloudApp`实例，代表云应用，主要功能包括：

- 发起一个远程会话创建请求
- 发起一个Agent执行任务/对话任务

```python
from veadk.cloud.cloud_app import CloudApp

# 创建远程会话
cloud_app.create_session(user_id=..., session_id=...)

# 发起任务
cloud_app.invoke(user_id=..., session_id=..., message=...)
```

- 通过端点发起一个远程会话创建请求

```python
from veadk.cloud.cloud_app import CloudApp

# 创建远程A2A会话
APP_NAME = “veadk-agent”
SESSION_ID = "cloud_app_test_session"
USER_ID = "cloud_app_test_user"
ENDPOINT = "<URL of application deployed by>"

app = CloudApp(name="veadk-agent", endpoint=ENDPOINT)

# 发起任务
cloud_app.invoke(user_id=USER_ID, session_id=SESSION_ID, message=...)
```

### 更新云应用

#### 通过 CloudAgentEngine 更新

当您需要更新已部署的Agent代码时，可以使用`update_function_code`方法：

```python
from veadk.cloud.cloud_agent_engine import CloudAgentEngine

engine = CloudAgentEngine()

# 更新现有应用的代码，保持相同的访问端点
updated_cloud_app = engine.update_function_code(
    application_name="my-agent-app",  # 现有应用名称
    path="/my-agent-project"        # 本地项目路径
)

# 可以使用updated_cloud_app.vefaas_endpoint访问您的项目
```

**注意事项：**

- 更新操作会保持相同的访问端点URL
- 确保项目路径包含`agent.py`文件

### 删除云应用

#### 通过 CloudAgentEngine 删除

```python
from veadk.cloud.cloud_agent_engine import CloudAgentEngine

engine = CloudAgentEngine()

# 删除指定的云应用
engine.remove(app_name="my-agent-app")
```

执行时会提示确认：

```bash
Confirm delete cloud app my-agent-app? (y/N): y
```

输入`y`确认删除，输入其他任何字符或直接回车则取消删除。

## 项目结构

一个能在云上运行的 agent 项目结构主要包括如下几个文件：

- `run.sh` 启动脚本
- `requirements.txt` 依赖列表
- `app.py` 定义 FastAPI Server 的 python 文件
- `agent.py` 导出 agent 以及短期记忆、依赖路径等信息
- `agent_module` 自定义的 agent 模块
  - `__init__.py` 必须包含 `from . import agent` 语句
  - `agent.py` 定义 agent 实例，必须包含 `root_agent=...` 全局变量导出
