# Harness 子模块示例：ContextEngine + ResultVerifier

这个示例演示如何为 veADK Agent 组合两个 Harness 子模块，用于上下文工程、
证据追踪和最终答案验证。

- `ContextEngine`：固定原始任务、过滤噪声历史、组装证据优先上下文，并记录
  轻量预算报告。
- `ResultVerifier`：记录工具收据、收集证据引用、检查最终答案里的伪造 URL 和
  无证据外部事实，并写入本地验证报告。

所有代码都自包含在 `examples/harness/`，开发者可以在一个目录内阅读、运行、
测试并按自己的业务场景改造。

## 目录

```text
examples/harness/
├── main.py
├── harness_agent.py
├── harness_modules/
│   ├── core.py
│   ├── context_engine.py
│   ├── result_verifier.py
│   ├── tool_wrappers.py
│   └── stores.py
├── tests/
└── golden/
    ├── production_scenarios.jsonl
    ├── context_engine_cases.jsonl
    └── verifier_cases.jsonl
```

## 运行

先配置常规 veADK 模型环境变量，然后执行：

```bash
python examples/harness/main.py
```

运行审计数据会写到 `.harness_runs/`：

- `events.jsonl`
- `messages.jsonl`
- `receipts.jsonl`
- `evidence/*.txt`
- `reports/<session_id>-<run_id>.json`

## 核心用法

```python
from harness_agent import build_harness_agent

bundle = build_harness_agent()
answer = await bundle.run(
    "请查一下 veADK Harness 示例的核心能力，给出来源，并用 3 条要点回答。",
    session_id="harness-demo",
)
report = bundle.latest_report(session_id="harness-demo")
```

`bundle.agent` 和 `bundle.runner` 是常规 veADK `Agent` / `Runner` 实例。
`bundle.run(...)` 是很薄的一层，用于协调 `user_id`、`session_id` 和
`original_prompt`，让 Harness processor 生成本地收据、证据、上下文事件和验证报告。

## 测试

测试使用 fake tool 和 fake runner event，不需要模型 key：

```bash
pytest examples/harness/tests
```

验证点：

- follow-up 轮次保留原始任务锚点；
- progress 和控制消息不会进入模型上下文；
- 可确定性拦截伪造 URL；
- 当前/外部事实任务无证据时验证失败；
- 工具异常时保留 failed receipt；
- 大工具结果外置为 evidence 文件。

场景级 golden 集合是
`examples/harness/golden/production_scenarios.jsonl`。它按通用生产场景和模块组织，
开发者可以在不绑定特定产品问题或项目特定数据集的情况下新增回归 case。
`verifier_cases.jsonl` 和 `context_engine_cases.jsonl` 保留模块级 golden 检查。

## 评测 Harness 增益

运行离线 A/B 评测：

```bash
python examples/harness/evaluation/run_eval.py
```

评测隔离的是 Harness 子模块的确定性效果，而不是模型能力。Baseline 使用原始历史，
并信任所有非空答案；Harness Treatment 使用 `ContextEngine` 和 `ResultVerifier`。
Case 集合覆盖常见生产开发场景：RAG 旧缓存、失败工具收据、权限误拦截、
运行时参数偏移，以及多轮上下文锚定。

当前结果：

| 指标 | Baseline | Harness | 增益 |
| --- | ---: | ---: | ---: |
| 结果验证准确率 | 20.0% | 100.0% | +80.0 pp |
| 不安全答案误放行率 | 100.0% | 0.0% | -100.0 pp |
| 不安全答案召回率 | 0.0% | 100.0% | +100.0 pp |
| 上下文质量分 | 0.0% | 100.0% | +100.0 pp |

离线报告按场景的摘要：

| 场景 | Baseline 表现 | Harness 增益 | 模块 |
| --- | --- | --- | --- |
| RAG 记忆新鲜度 | 无当前证据时仍信任旧缓存答案。 | 缺少当前知识库证据时阻断答案。 | `ResultVerifier` |
| 工具失败却声称成功 | 只要最终 JSON 写了 passed 就信任。 | 检测 failed receipt，阻断虚假的完成声明。 | `ResultVerifier` |
| 权限策略误拦截合法工具 | 合法工具被拦截后仍可能信任成功结果。 | 将 failed receipt 与 `operation_completed=true` 判为冲突。 | `ResultVerifier` |
| 运行时参数偏移 | 信任没有证据支撑的 token/runtime 数值。 | 阻断证据中不存在的关键数字事实。 | `ResultVerifier` |
| 多轮上下文锚定 | 原始历史包含 progress 噪声，且容易丢失任务锚点。 | 固定原始任务，并过滤控制消息污染。 | `ContextEngine` |
| 当前证据优先于旧记忆 | 最近历史中的旧缓存答案可能先于证据进入上下文。 | 将当前证据放在历史前，并保留原始任务锚点。 | `ContextEngine` |

报告输出到：
`examples/harness/evaluation/results/harness_eval_report.json` 和
`examples/harness/evaluation/results/harness_eval_report.md`。

## 带模型的评测

模型评测会发起实际 veADK 模型调用。可以先在 shell 中导出标准模型环境变量，也可以传入
任意包含 `MODEL_AGENT_API_KEY`、`MODEL_AGENT_NAME`、`MODEL_AGENT_API_BASE` 的
dotenv 文件：

```bash
python examples/harness/evaluation/run_model_eval.py \
  --env-file /path/to/model.env
```

如果这些变量已经在当前 shell 中导出，可以省略 `--env-file`。

报告不会写入任何密钥值。评测对比的是：普通 veADK Agent 对所有非空答案直接信任；
Harness Agent 只有在 `VerificationReport.done=True` 时才把答案视为可信。

报告输出到：
`examples/harness/evaluation/results/harness_model_eval_report.json` 和
`examples/harness/evaluation/results/harness_model_eval_report.md`。

当前示例模型评测结果：

| 指标 | Baseline | Harness | 增益 |
| --- | ---: | ---: | ---: |
| 信任决策准确率 | 66.7% | 100.0% | +33.3 pp |
| 无证据任务错误放行率 | 100.0% | 0.0% | -100.0 pp |
| 可回答任务验证放行率 | - | 100.0% | +100.0 pp |
| 可回答任务 receipt 覆盖率 | - | 100.0% | +100.0 pp |
| 无证据任务阻断率 | - | 100.0% | +100.0 pp |

模型报告还包含按场景组织的矩阵，第一列就是场景，覆盖 RAG 新鲜度、
工具证据收据、无证据幻觉抑制。

模型报告按场景的摘要：

| 场景 | Baseline 运行时 | Harness 运行时 | 结果说明 |
| --- | --- | --- | --- |
| RAG 新鲜度与来源支撑 | 信任非空模型答案。 | 只有存在工具收据和来源证据时才信任。 | 有来源要求的请求在证据充分时正常放行。 |
| 工具证据与 receipt 覆盖 | 不强制运行时 receipt 校验。 | 答案放行，同时记录工具 receipt。 | Harness 增加审计能力，不误伤有效答案。 |
| 无证据幻觉抑制 | 信任非空但无证据的答案。 | 因缺少工具证据或 source receipt 而阻断。 | 信任门能防止无证据来源声明返回给调用方。 |

## 设计说明

这个示例聚焦开发者最常用的核心链路：

- 在模型运行前构造任务感知的上下文 header；
- 包装工具调用，让每次能力调用都留下可审计收据；
- 将工具输出绑定到 evidence reference；
- 在信任最终答案前执行结果验证；
- 通过测试、离线评测和带模型评测度量效果增益。

模块实现保持紧凑、直接，适合作为业务侧扩展 Harness 能力的起点。
