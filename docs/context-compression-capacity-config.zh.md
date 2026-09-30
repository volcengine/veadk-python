# 模型上下文容量配置说明

当前支持 `google-adk>=1.34.0,<2.3.0`，默认安装由依赖解析器选择兼容版本；CI 固定验证 1.34.0、2.1.0、2.2.0 的 Python 3.10 / 3.12 组合。**ADK 2.3 及以上（含 2.9.2）暂不支持**：它们要求 OpenTelemetry ≥1.39，而 AgentKit SDK 0.8.x 要求 ≤1.37。请勿使用 `--no-deps` 强行安装；开启、关闭上下文压缩均遵守此 SDK 依赖范围。


日期：2026-09-30。对应开发分支 `feat/default-context-compression`，尚未正式发布。

各模型的容量已从 Python 代码迁移到 **`veadk/context/model_capacities.json`**。维护模型窗口时修改配置文件即可；`model_capacity.py` 只保留数据结构、加载、校验和查询逻辑。

配置文件路径（相对 SDK 仓库根目录）：

```text
veadk/context/model_capacities.json
```

## 配置格式

顶层为 `schema_version` 和 `models`。每个模型条目完整填写字段，不通过模型家族自动继承容量或协议参数。以下是配置中的一个现有条目示例；整个文件还包含其他模型，修改时保留它们。

```json
{
  "schema_version": 1,
  "models": [
    {
      "provider": "volcengine",
      "model_id": "deepseek-v4-1-flash-260910",
      "context_window": 1024000,
      "max_input_tokens": 1024000,
      "max_output_tokens": 384000,
      "source": "https://www.volcengine.com/docs/ark/model-list?lang=zh",
      "verified_on": "2026-09-28",
      "default_output_reserve": 16384,
      "aliases": [],
      "default_answer_tokens": null,
      "reasoning_token_reserve": 0,
      "answer_only_max_tokens": false,
      "ark_thinking_controls": false
    }
  ]
}
```

| 字段 | 含义 |
| --- | --- |
| `provider`、`model_id` | 服务商和精确模型版本；不做家族前缀匹配 |
| `context_window` | 共享上下文总上限，单位 token |
| `max_input_tokens`、`max_output_tokens` | 单独的最大输入、最大输出限制 |
| `default_output_reserve` | 规划输入时预留的输出空间，不是 API 生成参数 |
| `aliases` | 经确认指向该版本的别名；不能重复或与其他模型冲突 |
| `default_answer_tokens`、`reasoning_token_reserve` | 回答和推理的规划预算，按该版本的接口语义填写 |
| `answer_only_max_tokens` | 该接口的 `max_tokens` 是否只计算回答；不是所有模型都相同 |
| `ark_thinking_controls` | 是否启用当前 SDK 已适配的方舟 thinking 参数处理；不等于模型是否支持推理 |
| `source`、`verified_on` | 官方依据与实际核实日期；本次文件迁移不会修改原核实日期 |

单独公布输入和输出上限，不代表二者相加就是共享窗口。容量配置也不会替用户开启或关闭 thinking；实际生成参数仍由模型配置决定。

## 如何维护和生效

1. 根据该模型版本的官方说明，核实容量和输出参数语义，修改或新增 `models` 条目。
2. 更新对应来源和核实日期；容量必须填写整数，不能使用 `"128K"` 或布尔值。
3. 运行仓库强制门禁 `python tests/run_context_compression_gate.py -q`，构建 SDK 并确认 wheel/sdist 都包含 JSON。
4. 安装新构建并重启应用。配置随 SDK 包交付，进程启动时加载一次；当前不提供热更新，也不自动读取工作目录同名文件。

普通开发者创建 Agent 的方式不变：

```python
from veadk import Agent

agent = Agent(name="assistant")
```

单个私有部署也可以按实际限制使用 `context_compression` 的 `context_window`、`output_reserve` 参数，无需为每个业务实例修改 SDK 配置文件。

## 错误处理与验证

配置缺失或不可读取时抛出 `model_capacity_config_unavailable`；格式、字段、容量关系或名称冲突错误时抛出 `invalid_model_capacity_config`。错误不会静默降级为空表后猜测容量。未覆盖模型仍保持原来的 `model_capacity_required` 行为与显式容量配置指引。

迁移范围为原有 25 个条目，包括容量、别名、来源、核实日期以及回答/推理规划；已与迁移前实际加载的数据逐字段核对，全部一致。

| 验证项 | 结果 |
| --- | --- |
| 配置与预算定向回归 | 153 项通过 |
| 完整强制门禁 | 1,293 passed、5 skipped、0 failures/errors；Python 3.12 / google-adk 2.2.0 |
| 新增配置回归 | 覆盖类型/范围/重复名称、缺失与损坏文件、工作目录独立及错误信息；已纳入 `tests/context/` 强制入口 |
| 实际包构建 | wheel 和 sdist 都包含与源码字节一致的 JSON |
| 安装后验证 | 从实际安装的 wheel 读取全部 25 条配置，与迁移前一致；不受工作目录同名文件影响，普通 Agent 创建通过 |

执行全部在隔离 Devbox 目录，真实 LLM 调用 0、客户 Runtime 操作 0、新增依赖 0。Python 3.10 / 3.12 的发布与依赖回归各 10 项通过，新虚拟环境安装及依赖一致性检查通过。远端 CI 以 [PR #1152](https://github.com/volcengine/veadk-python/pull/1152) 当前提交为准；尚未正式发布。

开发者接入示例见[上下文压缩开发者入门与使用示例](context-compression-developer-guide.zh.md)。
