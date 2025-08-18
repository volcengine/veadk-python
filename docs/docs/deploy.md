# 部署上云

VeADK提供了一个云引擎，配合命令行脚手架，你可以方便地：

- 将你的本地Agent项目上传到云端（[火山引擎函数服务平台](https://www.volcengine.com/product/vefaas)）
- 启动一个新的样例模板项目进行开发

部署到云端时，你可以指定两种部署模式来对外提供服务：

- A2A与MCP Server（一体化启动）
  - A2A 提供标准的`message_send`等接口
  - MCP 提供`run_agent`工具方法
- VeADK Web（兼容Google ADK Web）

VeADK Web 将会为你提供一个Web界面，方便你在浏览器中进行体验。

## 脚手架

### 初始化

你可以运行`init`命令来初始化一个新的Agent项目：

```bash
$ veadk init
Directory name [veadk-cloud-proj]: 
Volcengine FaaS application name [veadk-cloud-agent]: 
Volcengine gateway instance name []: 
Volcengine gateway service name []: 
Volcengine gateway upstream name []: 
Choose a deploy mode:
  1. A2A/MCP Server
  2. VeADK Web / Google ADK Web
Enter your choice (1, 2): 1
Your project has beed created.
```

它会提示你输入如下几个参数：

- 本地项目名称（即项目的本地目录名称）
- VeFaaS应用名称
- 火山引擎网关实例名称
- 火山引擎网关服务名称
- 火山引擎网关Upstream名称
- 部署模式
  1. A2A / MCP Server
  2. VeADK Web / Google ADK Web

生成后的项目结构如下：

```bash
└── veadk-cloud-proj
    ├── config.yaml.example # 环境变量配置文件
    ├── deploy.py # 部署脚本
    ├── README.md
    └── src
        ├── agent.py # 定义 agent 导出
        ├── app.py  # 服务端启动脚本
        ├── run.sh  # 启动脚本
        └── weather_agent # Agent 实现
            ├── __init__.py
            ├── agent.py  # Agent 实例化
            └── requirements.txt  # 依赖
```

你所创建的`config.yaml`不会被上传到云端，其中的属性值将会以环境变量的形式上传至VeFaaS平台。

只有`src/`路径下的文件才会被上传到云端。

### 自定义项目

在使用脚手架生成模板项目后，你可以做如下操作：

1. 向`src`目录中直接导入一个能够被 ADK Web 识别的目录（例如`weather_agent`目录），主要包括：
   - 包含`root_agent`这个全局变量的`agent.py`文件
   - 包含`from . import agent`的`__init__.py`文件
2. 在`src/agent.py`中实例化`AgentRunConfig`类，主要属性包括：
   - `app_name`：部署在云上的 Agent 应用名称（与VeFaaS应用名称不一定对应，此处为服务级别）
   - `agent`：你提供服务的 Agent 实例
   - `short_term_memory`：短期记忆，为空则默认初始化in-memory短期记忆，重启后即消失
   - `requirement_file_path`：依赖文件路径，VeADK 能够自动将其移动到`src/requirements.txt`
3. 使用`python deploy.py`进行云端部署

如果你想在部署到云端前进行本地运行，测试代码问题，可以在`deploy.py`中的`engine.deploy`调用处，添加参数：`local_test=True`。添加后，在部署前将会启动相关服务，测试启动是否正常。

### 云端环境变量

| 环境变量名称 | 说明 | 值 | 备注 |
| - | - | - | - |
| VEADK_TRACER_APMPLUS | 是否使用火山 APMPlus Tracing | `true` \| `false` | |
| VEADK_TRACER_COZELOOP | 是否使用火山 CozeLoop Tracing | `true` \| `false` | |
| VEADK_TRACER_TLS | 是否使用 TLS Tracing | `true` \| `false` | |
| SHORT_TERM_MEMORY_BACKEND | 启动 ADK Web 时的短期记忆后端 | `local` \| `mysql` | 优先级低于在`agent.py`中定义的短期记忆 |
| LONG_TERM_MEMORY_BACKEND | 启动 ADK Web 时的长期记忆后端 | `opensearch` \| `viking` | 优先级低于在`agent.py`中定义的长期记忆 |

## Cloud Agent Engine

如果你已经有一个较为成熟的Agent项目，你可以通过VeADK中提供的云引擎来部署你的项目。VeFaaS平台所需的部署文件我们将会为你自动生成到你的项目路径中。

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
| use_studio | bool | 是否在云端使用VeADK Studio |
| use_adk_web | bool | 是否在云端使用VeADK Web / Google Web |

注意：`use_studio`与`use_adk_web`不可同时为`True`。

## Cloud App

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

## 更新云应用

### 通过 CloudAgentEngine 更新

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

## 删除云应用

### 通过 CloudAgentEngine 删除

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
