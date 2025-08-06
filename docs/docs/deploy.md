# 部署上云

## Cloud Agent Engine

通过定义一个云引擎，能够将本地Agent工程直接部署至VeFaaS中，并自动启动一个A2A Server。

```python
from veadk.cloud.cloud_agent_engine import CloudAgentEngine

engine = CloudAgentEngine()

# Create application thru local folder and unique application name
cloud_app = engine.deploy(path=<absolute path of your agent application, e.g. /Users/my_agent_name>, name=<unique name of your agent. e.g. veadk-agent>)

# Delete applicaton by name
async def delete_app(app_name: str):
    engine = CloudAgentEngine()
    engine.remove(app_name)

if __name__ == "__main__":
    asyncio.run(delete_app("veadk-agent"))
```

## Cloud App

部署完成后，将返回一个`CloudApp`实例，代表云应用，主要功能包括：

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
