# 08 · 模型配置：降级回退与额外选项

直接在 `Agent` 上配置模型 —— 为每个智能体单独选模型、添加回退（fallback）以提升健壮性、
并传入额外的请求选项。

> English version: [README.md](./README.md)

## 核心思想

```python
agent = Agent(
    model_name=["doubao-seed-1-6-250615", "deepseek-v3-2-251201"],  # 主模型 + 回退
    model_extra_config={"extra_body": {"thinking": {"type": "disabled"}}},
)
```

- **`model_name` 传列表** —— 第一个为主模型，请求失败时按顺序尝试后续模型。
  传单个字符串则固定使用一个模型。
- **`model_provider` / `model_api_base` / `model_api_key`** —— 为*当前*智能体单独覆盖模型
  （例如给某个子智能体用更便宜的模型），无需改动全局环境配置。
- **`model_extra_config`** —— 合并进每次请求。`thinking: disabled` 关闭模型的思维链输出，
  让回复更快、更省。

## 运行步骤

```bash
pip install veadk-python
cp .env.example .env   # 然后填入 MODEL_AGENT_API_KEY
python main.py
```

你会发现回复很快返回 —— 因为我们关闭了 thinking，没有冗长的思考输出。

## 下一步

- 在 [06](../06_multi_agent/) 中给不同子智能体配置不同的 `model_name`：
  用强模型负责写作，用便宜模型负责排版。
