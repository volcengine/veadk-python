# 通用项目迁移规则

## 背景

一般而言，一个agent通常由下面这些部件组成：

- 主入口或 Agent 配置：定义身份、业务场景、模型和回答方式
- Skill：描述业务流程、规则、知识资料和可用能力
- 工具 / 脚本 / MCP：执行具体动作，比如查日志、查数据库、调用 APM、跑诊断
- 配置文件：保存模型、云服务、数据库、日志系统等连接方式

迁移到 VeADK 时，要把这些内容重新组织成一个 VeADK Agent 工程：

- `assistant/agent.py` 放主 Agent，并暴露 `root_agent`
- `skills/<skill-name>/` 放 Skill 和相关资料
- `tools/` 放少量安全、可控的工具，或者先放工具能力说明
- `main.py`、`Dockerfile`、`.agentkit/agentkit.yaml` 是 VeADK 部署到 AgentKit 的适配层外壳。`Dockerfile` 由 `scripts/bootstrap_runtime.sh` 或 CLI-managed `agentkit init` 产出/归一化；不要手写固定 registry 或固定 `FROM`。

AgentKit 不是新的业务框架。它只负责把 VeADK Agent 打包成云端 runtime。真正决定 Agent 行为的是 `root_agent` 的 instruction、Skill 内容、工具能力说明和环境配置。

第一阶段迁移先保证四件事：Agent 知道自己服务什么场景，能找到 Skill，知道有哪些工具可以尝试，遇到未配置的外部系统能说清楚原因。数据库、APM、日志系统等真实连接能力可以后续补。

## 识别条件

无法确定项目框架，但是能找到用户的agent和skills以及配置文件时，使用此通用迁移规则

## 目标

迁移后必须做到：

- `from assistant.agent import root_agent` 可以成功执行
- `main.py` 可以加载 `root_agent` 并暴露服务应用
- Agent 保留原项目的身份、业务场景、回答语言和安全边界
- Agent 能发现并理解迁移后的 Skill
- Agent 知道原项目有哪些工具、脚本和诊断能力
- 工程能通过 VeADK/AgentKit Runtime 的确定性导入验证，并在配置模型凭证后可部署、可调用

可以暂时不做到：

- 原始脚本真实执行
- 云服务真实调用
- 数据库真实连接
- APM、日志系统真实查询
- 默认 post-step 中的真实模型调用

这些真实执行能力可以后续补。当前阶段不能伪造成功，必须在报告中说明需要的环境变量、网络和权限。

## 用户 Agent 架构含义

### 主 Agent

主 Agent 是迁移后的业务入口。用户的问题先进入主 Agent，由它判断要不要使用 Skill、要不要调用工具、最后如何回答。

在 VeADK 工程里，主 Agent 一般写在 `assistant/agent.py`，并暴露：

```python
root_agent = Agent(...)
```

主 Agent 必须做到：

- 保留原 Agent 的身份、业务场景、回答语言和安全边界
- 能判断用户问题是否需要使用 Skill
- 知道有哪些工具、脚本或诊断能力可以尝试
- 工具不可用时，能说明原因

如果原项目有多个 Agent，优先把直接面向用户的 Agent 作为 `root_agent`。其他 Agent 只有在原项目确实依赖时才迁移，不要凭空生成。

### Skill

Skill 不是主 Agent，也不是工具。Skill 是业务说明书和知识包。它告诉 Agent：这个场景是什么、处理流程是什么、有哪些资料、有哪些能力、哪些事情不能做。

迁移时保留这些内容：

```text
SKILL.md
references/
assets/
scripts/ 的源码、名称、用途、能力说明
config/ 里的环境变量名和配置项
```

如果源项目有标准或类标准 skill 目录，迁移结果必须把它转成 ADK-compatible skill package：

- 目录放在 `skills/<skill-name>/`
- `SKILL.md` 必须有 `name:` / `description:` frontmatter
- 目录名必须和 `name:` 一致，确保 `load_skill_from_dir()` 可加载
- `references/`、`assets/`、`scripts/`、`config/` 作为 skill resources 保留
- `assistant/agent.py` 通过 `load_skill_from_dir()` + `SkillToolset` 挂载，而不是把 skill 全文粘进 instruction

具体转换模板、脚本安全边界和验证方式见 `source-to-veadk/reference/adk-skill.md`。`.codex/skills/*` 是执行器侧 skill 目录，不视为原项目业务 skill。

如果 `scripts/` 暂时不能执行，也要保留源码或至少保留名称、用途和需要的配置。默认不要开放 `run_skill_script`；只有补齐安全 executor、凭证隔离、白名单和网络边界后，才允许脚本执行。

### 工具 / 脚本 / MCP

工具 / 脚本 / MCP 是执行层。它们负责真正动手。

迁移早期优先生成少量简单工具，只做这些事：

- 列出业务场景
- 列出原项目里真实存在的工具、脚本、诊断能力
- 生成诊断或执行计划
- 说明某个能力需要哪些环境变量和外部配置

真实执行云服务、数据库或 shell 脚本之前，必须先补齐配置、白名单和安全校验。

### AgentKit 适配层

AgentKit 适配层是允许用户将VeADK Agent未来部署到AgentKit外壳。它把 VeADK Agent 变成云端可运行服务。
你无需实际Agentkit Deploy，将VeADK部署上去，但是生成的产物必须是Deploy Ready的形态，加上下列的适配层外壳。

它包括：

```text
main.py
Dockerfile
.agentkit/agentkit.yaml
requirements.txt
```

要求：

- `main.py` 加载 `root_agent`
- 使用 `AgentkitAgentServerApp`
- 服务监听 `0.0.0.0:8000`
- `Dockerfile` 使用 AgentKit provider-aware 模板：如果目标是 BytePlus，必须匹配 BytePlus registry；如果目标是 Volcengine，必须匹配 Volcengine registry。不要把 `cn-beijing` 镜像写死到 BytePlus 迁移产物。
- `.agentkit/agentkit.yaml` 声明 runtime 配置；顶层 `apmplus: true`，`ENABLE_APMPLUS` 默认 `true`；应用运行时环境变量必须放在 `envs:` 下

## 迁移顺序

按这个顺序迁移：

1. **先找业务入口**
   找原项目里直接服务用户的 Agent、prompt、README、模型配置和 Skill 目录。先确认这个 Agent 是做什么的。

1. **同时识别观测和护栏信号**
   运行 `scripts/detect_source_capabilities.py`，并结合源码分析判断是否存在 OpenTelemetry/APM、guardrails、moderation、LLM Shield、prompt injection 或敏感信息防护等信号。APMPlus 是迁移后的 AgentKit 平台能力，默认开启，不依赖源项目是否已有观测；检测结果用于报告证据。安全护栏是否默认开启仍取决于凭证是否完整，但必须保留环境变量手动关闭。

2. **动态生成行为契约**
   基于源项目证据生成 `source_behavior_contract.json`，不要使用 bootstrap 占位内容。Codex 必须读回这个 contract，再写 Agent、工具、评测集和报告。这个文件既约束 Codex 迁移，也给用户验收迁移保留和降级的能力。

2. **再搬 Skill**
   迁移 `SKILL.md`、`references/`、`assets/`、`scripts/`、`config/` 到 `skills/<skill-name>/`，并在 `assistant/agent.py` 里以 ADK `SkillToolset` 挂载。脚本暂时不能执行也没关系，但要保留脚本名称、用途和需要的配置。
   如果 detector 报告 `skills.detected=true`，必须阅读 `reference/adk-skill.md` 并按该模板落地。

3. **再写 `root_agent`**
   在 `assistant/agent.py` 里创建 VeADK Agent。instruction 里写清楚身份、场景、处理流程、Skill 使用方式、工具不可用时的回答方式。

4. **最后接 AgentKit 适配层外壳**
   用 `main.py`、`Dockerfile`、`.agentkit/agentkit.yaml` 把组织好的 VeADK Agent 形成一个可进行 AgentKit Deploy 的形式。这里不新增业务逻辑；`Dockerfile` 保持 bootstrap 选择的 provider-aware base，不要用固定样例覆盖。

5. **运行确定性验证**
   执行 `bash "$AGENTKIT_MIGRATE_ASSET_DIR/scripts/validate_runtime.sh"`。失败后根据日志修复并重跑，直到通过或写出明确失败报告。

6. **生成行为评测集**
   根据 `source_behavior_contract.json` 生成 `eval/cases.json` 和 `eval/rubric.md`。评测集用于部署后通过 `agentkit eval` 检查迁移后行为是否贴近原项目，而不是迁移阶段的 mock 测试。

## 推荐产物

建议生成：

```text
assistant/agent.py
assistant/__init__.py
tools/
skills/<skill-name>/
main.py
requirements.txt
Dockerfile
.dockerignore
.agentkit/agentkit.yaml
.env.example
source_behavior_contract.json
migration_metadata.json
convert_report.md
eval/cases.json
eval/rubric.md
```


## 迁移原则

1. **先恢复业务理解，再补真实执行**
   先让 Agent 知道自己是谁、服务什么场景、有哪些 Skill 和能力。工具真实执行可以后补。

2. **保留用户业务资产**
   保留原项目里的 `SKILL.md`、`references/`、`assets/`、脚本源码/名称、配置项和模型配置参考。业务 skill 应是一等 ADK skill 资源，不是 prompt 的附录。

3. **代码保持简单**
   迁移结果应该容易读、容易调试、容易部署。不要发明新框架、调度器、脚本系统或模拟服务。

4. **对于涉及到外部服务的mcp工具或者http,不做要求**

5. **模型配置使用环境变量引用**
   `.agentkit/agentkit.yaml` 的 `envs:` 只写环境变量引用，不写真实 key。模型名优先使用 `AGENTKIT_TARGET_MODEL_ID` / `MODEL_NAME`，模型 key env 优先使用 `AGENTKIT_TARGET_MODEL_API_KEY_ENV`，默认 `MODEL_AGENT_API_KEY`。`assistant/agent.py` 也必须读取同一个 key env；如果用户指定 `ARK_API_KEY`，不要再生成空的 `MODEL_AGENT_API_KEY` 别名。

6. **观测默认开启，护栏凭证驱动**
   迁移产物的 `envs.ENABLE_APMPLUS`、顶层 `apmplus` 和 `.env.example` 默认 `true`；不要生成 `OTEL_SERVICE_NAME`、`OTEL_RESOURCE_ATTRIBUTES`。源项目有安全围栏/内容审核信号时，先记录能力；只有 `TOOL_LLM_SHIELD_APP_ID` 和 `TOOL_LLM_SHIELD_API_KEY` 已配置时，`ENABLE_LLM_SHIELD` 才可以默认 `true`。缺少凭证时默认 `false`，且不要写空的 Shield 凭证 env。用户部署时仍可显式设置 `true` 或 `false` 覆盖默认值。

## 禁止事项

- 不复制 证书、缓存、日志、`__pycache__`、`*.pyc`
- 不生成复杂脚本框架
- 不自动执行危险命令
- 不默认执行写 SQL
- 不读取敏感文件
- 不伪造云服务、数据库、APM、日志系统调用成功
- 不为了显得完整生成大量不可维护代码

## 验证

只执行通用确定性验证，不额外测试源项目脚本、外部文件、外部系统或真实模型调用。

```bash
PYTHON=/home/gem/venv_veadk/bin/python
[ -x "$PYTHON" ] || PYTHON=python
"$PYTHON" -m compileall -q .
"$PYTHON" -c "from assistant.agent import root_agent; print(root_agent.name)"
"$PYTHON" -c "from main import app; print(type(app).__name__)"
```

推荐直接运行统一脚本：

```bash
bash "$AGENTKIT_MIGRATE_ASSET_DIR/scripts/validate_runtime.sh"
```

## 部署后评测

迁移产物必须给出可执行评测材料：

- `source_behavior_contract.json`：动态生成的源行为契约，包含入口、可见行为、典型输入、输出契约、工具/集成、状态/记忆、外部依赖、安全边界、降级能力、迁移映射和 eval 覆盖
- `eval/cases.json`：至少 3 条源项目相关用例，字段只包含 `input`、`reference_output`，可直接执行 `agentkit eval dataset add --file eval/cases.json`
- `eval/rubric.md`：评测迁移后行为是否保留源项目身份、核心能力、安全边界和诚实降级
- `eval/rubric.md` 必须可直接作为 AgentKit evaluator prompt 使用：引用 `{{input}}`、`{{output}}`、`{{reference_output}}`，并要求评测器返回 `score: 1|0.5|0` 和一句简短理由。不要只写 PASS/PARTIAL/FAIL，否则平台实验会运行但评分不可解析或全部失败。

部署成功后可按以下流程执行真实评测：

```bash
DATASET_ID=$(agentkit eval dataset create --name <dataset-name> --schema input,reference_output --json | jq -r '.id // .datasetId')
agentkit eval dataset add "$DATASET_ID" --file eval/cases.json
EVALUATOR_ID=$(agentkit eval evaluator create --name <evaluator-name> --from-template <template-with-input-output-reference_output> --prompt-file eval/rubric.md --model <judge-model> --json | jq -r '.id // .evaluatorId')
agentkit eval run --dataset "$DATASET_ID" --evaluator "$EVALUATOR_ID" --target <runtime-name>
```

如果评测结果暴露行为偏差，应优先修 `assistant/agent.py` 的身份/流程/工具边界，或补充安全只读工具，而不是伪造外部系统结果。
