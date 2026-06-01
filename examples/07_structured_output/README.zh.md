# 07 · 结构化输出

让智能体返回符合你定义 schema 的 JSON，而不是自由文本。把一个 Pydantic 模型
传给 `output_schema` 即可。

> English version: [README.md](./README.md)

## 核心思想

```python
class Ticket(BaseModel):
    summary: str
    category: str
    priority: str
    sentiment: str

agent = Agent(output_schema=Ticket, instruction="抽取一张工单。")

raw = await runner.run(messages="你们的 App 一打开账单页就崩溃！", ...)
ticket = Ticket.model_validate_json(raw)   # 保证能解析
```

回复保证符合 `Ticket` 结构，因此可以直接 `model_validate_json`（或 `json.loads`）—
非常适合信息抽取、分类，以及把结果交给下游代码处理。

> ⚠️ 设置 `output_schema` 后，智能体**只会**返回结构化结果，无法调用工具或转交子智能体。

## 运行步骤

```bash
pip install veadk-python
cp .env.example .env   # 然后填入 MODEL_AGENT_API_KEY
python main.py
```

你会看到解析后的 `Ticket` 以美化 JSON 打印出来。

## 下一步

- 增加字段（如 `affected_feature: str`）后重新运行。
- 把结构化抽取与工作流（[06](../06_multi_agent/)）结合：一个智能体负责抽取，
  下一个智能体基于结构化结果继续处理。
