# 06 · 多智能体工作流

把一个任务拆分给多个各司其职的智能体，并按固定顺序执行。`SequentialAgent` 会
自上而下依次运行子智能体，通过共享的会话状态在它们之间传递数据。

> English version: [README.md](./README.md)

## 核心思想

```text
拟提纲 -> 撰写 -> 润色
```

```python
outliner = Agent(name="outliner", instruction="...", output_key="outline")
writer = Agent(name="writer", instruction="...扩写：\n{outline}", output_key="draft")
editor = Agent(name="editor", instruction="...润色：\n{draft}", output_key="final")

pipeline = SequentialAgent(
    name="content_pipeline", sub_agents=[outliner, writer, editor]
)
runner = Runner(agent=pipeline, app_name="multi_agent_demo")
```

让它跑通的两个机制：

- **`output_key`** —— 智能体把自己的回复写入会话状态的该键下。
- **`{key}` 模板注入** —— 下一个智能体在 instruction 中引用该键即可取回其值。

于是 `outliner` 写入 `outline`，`writer` 读取 `{outline}` 并写入 `draft`，
`editor` 读取 `{draft}` 并产出最终文本 `final`，由 runner 返回。

## 运行步骤

```bash
pip install veadk-python
cp .env.example .env   # 然后填入 MODEL_AGENT_API_KEY
python main.py
```

你会得到一段经过三个阶段处理、润色后的文字。

## 下一步

- VeADK 还提供 `ParallelAgent`（并发运行子智能体）与 `LoopAgent`（循环直到满足条件），
  用法都是同样的 `sub_agents=[...]`。
- 若需要*动态*委派（由一个协调者智能体自行决定调用哪个专家），
  可直接给普通 `Agent` 传入 `sub_agents=[...]`，让大模型来路由。
