# 10 · 智能体路由（动态委派）

一个协调者智能体，在**运行时决定**把每个请求交给哪个专家。这与
[06](../06_multi_agent/) 的固定流水线相对：那里顺序写死，这里由大模型来路由。

> English version: [README.md](./README.md)

## 核心思想

```python
coordinator = Agent(
    instruction="你是一个路由器，把请求转交给合适的专家。",
    sub_agents=[finance_agent, translator_agent],
)
```

给普通 `Agent` 一个 `sub_agents` 列表，它就能把对话**转交（transfer）**给最合适的那个。
协调者依据每个子智能体的 **`description`** 来选择 —— 因此这些描述实际上就是路由表。
请为路由器而写好这些描述。

本示例中：

- “100 美元换多少人民币？” → 路由到 `finance_agent`（调用 `get_exchange_rate`）。
- “翻译……” → 路由到 `translator_agent`。

## 运行步骤

```bash
pip install veadk-python
cp .env.example .env   # 然后填入 MODEL_AGENT_API_KEY
python main.py
```

## SequentialAgent 与路由的区别

| | 顺序 | 由谁决定 |
| --- | --- | --- |
| [06 SequentialAgent](../06_multi_agent/) | 固定（A→B→C） | 你 |
| 10 路由（本例） | 动态 | 大模型协调者 |

## 下一步

- 增加第三个专家（如 `weather_agent`），观察协调者如何选择。
- 组合使用：被路由到的专家本身也可以是一个 `SequentialAgent`。
