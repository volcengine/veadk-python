# 评测

VeADK构建一套完整的自动化Evaluation流程，主要能力包括：

- 运行时数据采集：通过collect_runtime_data开启
- 测试集文件生成：开启后自动dump到本地
- 评测：通过不同的evaluator或adk eval命令进行测试
- 反馈优化：自动根据评测结果（score reason等属性）优化prompts

## 运行时数据采集

```python
from veadk.evaluation import EvalSetRecorder

# 在希望进行数据dump处初始化一个EvalSetRecorder
eval_set_recorder = EvalSetRecorder(session_service, eval_set_id)

# dump数据，为Json格式
dump_path = await eval_set_recorder.dump(app_name, user_id, session_id)
```

## 评测集文件

评测集文件格式兼容Google Evaluation，详见[评测集文件格式](https://google.github.io/adk-docs/evaluate/#how-evaluation-works-with-the-adk)。

评测集本地保存过程中，均考虑当前会话。下面是一些概念对齐：

- `test_case`：所有对话轮次
- `invocation`：一轮对话

## 评测器

当前VeADK支持Deepeval评测器，通过如下方式定义：

```python
from veadk.evaluation.deepeval_evaluator import DeepevalEvaluator

# 当然，你还可以传入`judge_model`等相关信息
evaluator = DeepevalEvaluator()
```

## 评测方法

启动标准的评测接口：

```python
await evaluator.eval(eval_set_file_path=dump_path, metrics=metrics)
```

其中，输入：

- `eval_set_file_path`：评测集文件路径
- `metrics`：评测指标

不同的评测指标在不同测试框架中可能不同。

## 数据上报

评测结果可以自动上报至火山引擎的VMP平台，只需要在定义评估器的时候传入Prometheus pushgateway的相关参数：

```python
from veadk.evaluation.utils.prometheus import PrometheusPushgatewayConfig

# 可以自动从环境变量中读取相关配置
prometheus_config = PrometheusPushgatewayConfig()

# 传入到评估器中
evaluator = DeepevalEvaluator(
    ...,
    prometheus_config=prometheus_config,
)
```