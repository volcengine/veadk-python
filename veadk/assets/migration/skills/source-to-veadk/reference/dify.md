# Dify 迁移规则

## 识别条件

输入目录指 `AGENTKIT_MIGRATE_INPUT_DIR`。输入目录包含 `workflow.yml` 或 `workflow.yaml`。`node_config.yml` 是可选的节点补充配置。

## 迁移重点

把 Dify graph workflow 转成可调用的 Python workflow，并用 VeADK `root_agent` 包装。

必须解析并保留：

- app 信息
- workflow nodes
- workflow edges
- 变量定义
- 节点 id、title、type 和关键配置
- `node_config.yml` 中的节点级覆盖配置

## 额外产物

Dify 迁移必须额外生成：

```text
assistant/workflow.py
```

`assistant/workflow.py` 暴露：

```python
def build_workflow():
    ...
```

返回对象支持：

```python
workflow.invoke({"query": "demo 1"})
```

## 实现策略

- `start`、`end`、`answer`、变量整理等本地逻辑直接实现。
- `llm`、`agent`、`question-classifier` 等 LLM 类节点必须生成真实模型调用路径。
- HTTP、知识库、RAG、插件、数据库等外部依赖没有真实配置时，生成 transparent no-op adapter：保留 trace 和 metadata，默认不改变 state，不向用户可见 answer 写 placeholder。
- 只有后续节点强依赖某个未配置输出且无法安全留空时，才记录为 unresolved dependency。
- 输出结果建议包含 `status`、`answer`、`trace`、`unconfigured_nodes`、`placeholders` 和 graph 摘要。

## 模型配置

模型配置必须使用环境变量引用：

- model name 优先读取 `AGENTKIT_TARGET_MODEL_ID`、`MODEL_NAME`、`codex_model`。
- model api key 只读取 `AGENTKIT_TARGET_MODEL_API_KEY_ENV` 指向的 env，默认 `MODEL_AGENT_API_KEY`。
- `.agentkit/agentkit.yaml` 不写真实 key，只写 `${MODEL_AGENT_API_KEY:?set MODEL_AGENT_API_KEY before deploy}` 这类引用。
- `assistant/agent.py` 必须读取同一个 model api key env；如果用户指定 `ARK_API_KEY`，不要生成空的 `MODEL_AGENT_API_KEY` 别名。
- `APP_HOST: "0.0.0.0"`，`APP_PORT: "8000"`。

缺少模型环境变量时，返回可调试的配置缺失错误，不伪造 LLM 成功。

## Dify 验证

只执行通用确定性验证，不额外测试 workflow demo、源项目文件、外部依赖或真实模型调用。缺少模型环境变量时，允许返回模型配置缺失错误；不能把 LLM 节点降级成假结果。

## 行为契约

必须从 Dify workflow、变量、节点、分支、提示词和外部依赖中动态生成 `source_behavior_contract.json`。优先写入 `schema_version: 1`，但不要为了形式字段牺牲源行为证据。这个文件先给 Codex 使用：实现 VeADK Agent、工具、降级边界和 eval cases 都必须从 contract 映射；同时也给用户验收迁移后的保留能力和降级能力。不要保留 bootstrap 占位内容。

## 部署后评测

必须生成：

```text
source_behavior_contract.json
eval/cases.json
eval/rubric.md
```

`eval/cases.json` 至少 3 条用例，字段只包含 `input`、`reference_output`，可直接导入 AgentKit eval dataset。用例需要覆盖：

- 主要 workflow 正常用户输入
- 分支/分类/变量映射等 Dify 图结构关键行为
- 未配置 HTTP、知识库、数据库、插件等外部节点时的透明降级或明确错误

`eval/rubric.md` 评测重点：

- 是否保留原 Dify app 的意图、回答格式和关键分支
- 是否诚实报告未配置外部依赖
- 是否没有伪造 LLM、HTTP、RAG、数据库或插件执行结果
- 必须引用 `{{input}}`、`{{output}}`、`{{reference_output}}`，并要求只返回数值评分 `1`、`0.5` 或 `0` 加一句简短理由。不要只返回 PASS/PARTIAL/FAIL。

这些文件用于部署后执行 `agentkit eval dataset add --file eval/cases.json` 与 `agentkit eval evaluator create --prompt-file eval/rubric.md`，不是默认 post-step 的 mock 测试。
