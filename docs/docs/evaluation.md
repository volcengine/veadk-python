# 评测

VeADK 构建一套完整的自动化评测（Evaluation）流程，其主要功能包括：

- 运行时数据采集：自动捕获 Agent 的运行时数据
- 测试集文件生成：Agent 运行后自动将运行时数据作为测试数据集（Eval Set）导出到本地
- 评测：通过多种评测器（Evaluator）进行评测
- 反馈优化：根据评测结果（如评测得分，原因分析等）自动优化 prompts

## 运行时数据采集

VeADK 可以通过两种方式采集 Agent 的运行时数据。

对于 `agent.run()` 方法，在调用时设置 `collect_runtime_data=True` 即可开启数据采集。运行结束后，运行时数据构成的评测集文件将保存在 `agent._dump_path` 指定的路径。

```python
await agent.run(
    prompt,
    collect_runtime_data=True,
    eval_set_id=f"eval_demo_set_{get_current_time()}",
)
# get expect output
dump_path = agent._dump_path
assert dump_path != "", "Dump eval set file failed! Please check runtime logs."
```

对于 `Runner` 执行器，在 Agent 运行结束后，通过调用 `runner.save_eval_set()` 将运行时数据构成的评测集文件保存在默认路径。

```python
runner = Runner(
    agent=agent,
    short_term_memory=ShortTermMemory(),
)

await runner.run(messages=prompts, session_id=session_id)

dump_path = await runner.save_eval_set(session_id=session_id)
assert dump_path != "", "Dump eval set file failed! Please check runtime logs."
```

## 评测集文件

评测集文件格式兼容 Google Evaluation 标准，详见[评测集文件格式](https://google.github.io/adk-docs/evaluate/#how-evaluation-works-with-the-adk)。评测集本地保存过程中，会考虑所有会话。

文件结构说明：

- `eval_cases`：所有对话轮次
- `conversation`：一轮对话
  - `user_content`：用户的输入
  - `final_response`：Agent 的最后输出
  - `intermediate_data`：中间数据
    - `tool_uses`：Agent 使用的工具
    - `intermediate_responses`：Agent 的中间会话

## 评测

VeADK 目前支持 [DeepEval](https://deepeval.com/) 评测器和 [ADKEval](https://google.github.io/adk-docs/evaluate/)，通过如下方式定义评测器：

```python
from veadk.evaluation.deepeval_evaluator import DeepevalEvaluator
from veadk.evaluation.adk_evaluator.adk_evaluator import ADKEvaluator

# 当然，你还可以传入`judge_model`等相关信息
evaluator = DeepevalEvaluator()

# Alternatively:
# evaluator = ADKEvaluator()
```

启动标准的评测接口：

```python
await evaluator.eval(eval_set_file_path=dump_path, metrics=metrics)
```

参数说明：

- `eval_set_file_path`：评测集文件路径
- `metrics`：评测指标，不同的评测指标在不同测试框架中可能不同。

## 数据上报

评测结果可以自动上报至火山引擎的 [VMP](https://console.volcengine.com/prometheus) 平台，只需要在定义评估器的时候传入 Prometheus pushgateway 等相关参数即可，可在 `config.yaml` 中进行配置并从环境变量中自动读取：

```python
from veadk.evaluation.utils.prometheus import PrometheusPushgatewayConfig

# Load Prometheus configuration (can be read from environment variables)
prometheus_config = PrometheusPushgatewayConfig()

# Pass config into evaluator
evaluator = DeepevalEvaluator(
    ...,
    prometheus_config=prometheus_config,
)
```

## 完整示例

以下是使用 DeepEval 评测器的完整例子。其中定义了 [GEval](https://deepeval.com/docs/metrics-llm-evals) 指标和 [ToolCorrectnessMetric](https://deepeval.com/docs/metrics-tool-correctness) 指标，分别用于整体输出质量评估和工具调用正确率评估，并将评测结果上报至火山引擎的 VMP 平台：

```python
import asyncio
import os
from builtin_tools.agent import agent

from deepeval.metrics import GEval, ToolCorrectnessMetric
from deepeval.test_case import LLMTestCaseParams
from veadk.config import getenv
from veadk.evaluation.deepeval_evaluator import DeepevalEvaluator
from veadk.evaluation.utils.prometheus import PrometheusPushgatewayConfig
from veadk.prompts.prompt_evaluator import eval_principle_prompt

prometheus_config = PrometheusPushgatewayConfig()

# 1. Rollout, and generate eval set file
# await agent.run(
#     prompt,
#     collect_runtime_data=True,
#     eval_set_id=f"eval_demo_set_{get_current_time()}",
# )
# # get expect output
# dump_path = agent._dump_path
# assert dump_path != "", "Dump eval set file failed! Please check runtime logs."

# 2. Evaluate in terms of eval set file
evaluator = DeepevalEvaluator(
    agent=agent,
    judge_model_name=getenv("MODEL_JUDGE_NAME"),
    judge_model_api_base=getenv("MODEL_JUDGE_API_BASE"),
    judge_model_api_key=getenv("MODEL_JUDGE_API_KEY"),
    prometheus_config=prometheus_config,
)

# 3. Define evaluation metrics
metrics = [
    GEval(
        threshold=0.8,
        name="Base Evaluation",
        criteria=eval_principle_prompt,
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
    ),
    ToolCorrectnessMetric(
        threshold=0.5
    ), 
]

# 4. Run evaluation
eval_set_file_path = os.path.join(
    os.path.dirname(__file__), "builtin_tools", "evalsetf0aef1.evalset.json"
)
await evaluator.eval(eval_set_file_path=eval_set_file_path, metrics=metrics)
```