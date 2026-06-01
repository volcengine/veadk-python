# 02 · 自定义工具

让智能体调用你自己的 Python 函数。工具本质上就是一个带**类型注解**和**文档字符串（docstring）**
的函数 —— 通过 `tools=[...]` 传入，模型会自行决定何时调用。

> English version: [README.md](./README.md)

## 核心思想

```python
def get_city_weather(city: str) -> dict[str, str]:
    """获取某个城市的当前天气。

    Args:
        city: 城市的英文名称，例如 "Beijing"。
    """
    ...

agent = Agent(tools=[get_city_weather, recommend_clothing])
```

docstring 就是工具的“接口说明”，模型会据此理解工具用途。请清晰描述每个参数，
模型会用这些信息判断*何时*以及*如何*调用工具。

本示例串联了两个工具：智能体先查询天气，读取温度，再调用穿衣建议工具 —— 在一轮对话内完成。

## 运行步骤

```bash
pip install veadk-python
cp .env.example .env   # 然后填入 MODEL_AGENT_API_KEY
python main.py
```

## 下一步

- 新增一个 `get_air_quality(city)` 工具，并更新 instruction 来使用它。
- 继续阅读 [03 · 短期记忆](../03_short_term_memory/)，实现多轮对话。
