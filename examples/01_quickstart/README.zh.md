# 01 · 快速开始

最小可运行的 VeADK 程序。`Agent` 承载模型与指令，`Runner` 负责驱动一次对话并返回最终回答。

> English version: [README.md](./README.md)

## 核心思想

```python
agent = Agent(name="quickstart_agent", instruction="你是一个乐于助人的助手。")
runner = Runner(agent=agent, app_name="quickstart")
answer = await runner.run(messages="你好！", session_id="demo-session")
```

- `Agent(...)` 会自动从环境变量（`MODEL_AGENT_*`）读取模型配置。
- `runner.run(...)` 是**异步**方法，返回最终回答文本（字符串）。

## 运行步骤

1. 安装 VeADK：

   ```bash
   pip install veadk-python
   ```

2. 配置密钥：

   ```bash
   cp .env.example .env
   # 然后编辑 .env，填入 MODEL_AGENT_API_KEY
   ```

3. 运行：

   ```bash
   python main.py
   ```

终端会打印出一句话的回答。

## 下一步

- 修改 `instruction`，给智能体一个不同的人设。
- 继续阅读 [02 · 自定义工具](../02_custom_tools/)，让智能体调用你自己的 Python 函数。
