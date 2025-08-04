# 部署上云

## Cloud Agent Engine

通过定义一个云引擎，能够将本地Agent工程直接部署至VeFaaS中，并自动启动一个A2A Server。

```python
engine = CloudAgentEngine()
cloud_app = engine.deploy(path=..., name=...)
```

## Cloud App

部署完成后，将返回一个`CloudApp`实例，代表云应用，主要功能包括：

- 发起一个远程会话创建请求
- 发起一个Agent执行任务/对话任务

```python
# 创建远程会话
cloud_app.create_session(user_id=..., session_id=...)

# 发起任务
cloud_app.invoke(user_id=..., session_id=..., message=...)
```
