# 部署上云

VeADK提供了一个云引擎，配合命令行脚手架，你可以方便地：

- 将你的本地Agent项目上传到云端
- 启动一个新的样例模板项目进行开发

你可以指定部署到云端的项目以三种模式进行对外服务：

- VeADK Studio
- VeADK Web（兼容Google ADK Web）
- A2A Server

前两种将会为你提供一个Web界面，方便你在浏览器中进行测试与可观测实践。

## 脚手架

你可以运行`init`命令来初始化一个新的Agent项目：

```bash
veadk init
```

它会提示你输入如下几个参数：

- 本地项目名称（即项目的本地目录名称）
- VeFaaS应用名称
- 火山引擎网关实例名称
- 火山引擎网关服务名称
- 火山引擎网关Upstream名称
- 部署模式
  1. A2A Server
  2. VeADK Studio
  3. VeADK Web / Google ADK Web

生成后的项目结构如下：

```bash
└── veadk-cloud-proj
    ├── __init__.py
    ├── config.yaml.example # 需要修改为config.yaml并设置
    ├── deploy.py # 部署脚本文件
    ├── README.md
    └── src
        ├── __init__.py
        ├── agent.py # 在其中定义你的Agent和短期记忆
        ├── app.py # FastAPI应用，用于处理HTTP请求
        ├── requirements.txt    # 依赖
        ├── run.sh # VeFaaS服务启动脚本
        └── studio_app.py # 用于VeADK Studio/Web的应用
```

别担心，你所创建的`config.yaml`不会被上传到云端，其中的属性值将会以环境变量的形式上传至VeFaaS平台。

只有`src/`路径下的文件才会被上传到云端。

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

- 更新自身代码
- 删除自身
