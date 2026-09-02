# codex_data_analysis

一个把原始销售流水变成正式报告的 Agent——**它自己写分析脚本、运行、读报错、改脚本、再运行**，
全过程都在操作系统级沙箱里，且网络已关闭。

> English version: [README.md](./README.md)

这是 `runtime="codex"` 的旗舰示例。如果你要找的是 skill / MCP 工具在该 runtime 下的接线参考，
请看 [`codex_with_skill_and_mcp/`](../codex_with_skill_and_mcp/)。

```
codex_data_analysis/
├── main.py                 # Agent、沙箱配置，以及一次两轮对话
├── analytics_tools.py      # 夹在沙箱两端的两个 ADK 工具
├── data/
│   └── sales_2025q3.csv    # “内部系统”：2400 条原始订单，脏数据俱全
├── skills/
│   └── sales-report/
│       └── SKILL.md        # 报告的固定格式（house format）
└── outbox/                 # 运行时创建——只有 publish_report 放行的文件
```

## 这个任务做什么

1. `fetch_sales_extract`（ADK 工具）把某个季度的订单从内部数仓导出**到 Codex 的工作区**，
   只返回一张回执：`{"path": "data/sales_2025q3.csv", "rows": 2400, ...}`。
2. **Codex** 写一个分析脚本、运行、撞上真实的 `ValueError`、修好、再运行，
   最终产出 `report.md` 和一张手写的 `chart.svg`。
3. `publish_report`（ADK 工具）校验路径，把两个文件复制进 `outbox/`——这是任何文件离开沙箱的唯一出口。

随后的第二轮——*“把趋势图换成按地区的收入排行”*——复用同一个工作区：数据、脚本、报告都还在，
所以 Agent 是去改，而不是从头再来。

## 为什么这个任务适合 codex，而不适合 adk

真正该比的不是“模型能不能跑代码”——`runtime="adk"` 也有 code executor。
该比的是 **你拿到的是什么形状的循环，以及安全地跑起来要付出什么代价。**

**这个 runtime 在这里给你的东西：**

- **一个工作目录加一个 shell，而不是一个表达式求值器。** 调试就是 `ls`、`cat`、写文件、
  `python3 x.py`、读 traceback、打补丁、再跑一遍这样一个循环。ADK 的 code executor 是把
  *模型吐出的代码块*执行掉再把输出还回去；它不是一个能让模型把脚本、数据文件、图表、报告
  堆在一起反复迭代的地方。
- **一个不需要额外基础设施的操作系统沙箱。** macOS seatbelt / Linux landlock+seccomp，由
  Codex CLI 自己建立。ADK 自带的是 `UnsafeLocalCodeExecutor`——直接在*你的*进程里执行，
  没有任何隔离，甚至不支持有状态——以及 `BuiltInCodeExecutor`，后者转交给模型厂商的服务端工具，
  只支持 Gemini，在 Ark 聊天后端上根本用不了。更安全的方案都得你自己搭。
  而这里 `sandbox="workspace_write"` + `network_access=False` 就是四行配置。
- **能跨轮次存活的文件。** 工作区按会话隔离，所以第二轮是在第一轮的产物上继续改。
  code executor 的代码块每次都从零开始，除非你自己把状态重建出来。
- **一套不用靠提示词拼出来的调试机制。** 读 traceback、改文件重跑，本来就是 Codex 自身循环在做的事。

**你要为此付出的代价：**

- 每一轮都要拉起一个 Codex 子进程，而且每个原生工具回合都要发一次后端请求，
  每次都把整轮上下文重新序列化一遍。这个示例要跑几分钟、几十次模型调用，
  而一次性回答只要一次。
- `Agent` 的相当一部分配置面会被直接拒绝（见 [约束](#约束)），
  并且 per-LLM-call 回调完全不会执行。
- 回合数不确定。用 `RunConfig(max_llm_calls=...)` 给它兜底。

**什么时候*不该*用它：**

- 一次工具调用加一句格式化回答。`runtime="adk"` 更快更便宜——为此拉起 Codex 子进程毫无收益。
- 你需要 `output_schema`、`sub_agents`、`planner` 或 per-call 模型回调。这些在该 runtime 下都被拒绝。
- 计算逻辑事先就已知。如果你早就知道分析就是“按地区分组求和”，那就直接用 Python 写好、
  包成一个 ADK 工具。这个 runtime 值回票价的场景是 **代码事先无法确定**：一次性分析、
  不熟悉的文件格式、只有真的跑一遍才会暴露的数据缺陷。
- 对延迟敏感的交互式对话。

## 唯一必须做对的事：传路径，不传数据

> **工作区是数据面，工具的入参和返回值是控制面。**

在该 runtime 下，ADK 工具由 runtime 的 Responses shim 执行，它的 JSON 返回值会
**以文本形式回到模型上下文里**，而不会落到文件上。所以：

```python
# 错 —— 2400 行数据会进入本次请求，并且此后每次请求都跟着走
def fetch_sales_extract(quarter: str) -> dict:
    return {"rows": [...]}          # 约 125 KB 的 CSV，每一回合都重发一遍

# 对 —— 数据落盘，回执给模型
def fetch_sales_extract(quarter: str) -> dict:
    workspace = Path(current_workspace())        # 本轮沙箱的工作目录
    shutil.copyfile(source, workspace / "data" / source.name)
    return {"status": "ok", "path": "data/sales_2025q3.csv", "rows": 2400,
            "columns": [...], "bytes": 127983}
```

模型随后用自己的沙箱代码去读这个文件，那里的数据量是免费的。
`publish_report` 是同一条规则的反方向：入参是*路径*，返回的是“复制出去了什么”的回执。

这份数据的**体量本身就是设计的一部分**。只有 40 行时，模型直接 `cat` 一下就看全了所有脏数据，
第一版脚本就写对——调试循环根本不会发生，示例也就什么都证明不了。到了 2400 行，
`cat` 没有用（Codex 会截断命令输出），要弄清文件里到底有什么，唯一的办法就是写代码跑一遍看哪里炸。
这正是这个 runtime 存在的意义，也正是真实数据导出的样子。

有两点值得记住：

- **工具的 docstring 要把这件事说清楚。** `fetch_sales_extract` 的 docstring 明确告诉模型
  “返回的是回执不是数据——请到返回的路径去读 CSV”。不写这句，模型会试图把回执当数据用。
- **模型给的路径是不可信输入。** `publish_report` 会把每个路径解析回工作区，
  并拒绝任何越界的路径（`..`、绝对路径、指向外部的符号链接）。见 `_resolve_in_workspace`。

### 工具是怎么知道工作区在哪的

ADK 工具跑在*你的*进程里，而不是沙箱里，所以必须有人告诉它们 Codex 在哪工作。
它们每次被调用时自己问一遍：

```python
from veadk.runtime.codex import current_workspace

def fetch_sales_extract(quarter: str) -> dict:
    workspace = current_workspace()      # 本轮的工作目录，或者 None
    if workspace is None:                # 不在 codex 轮次里——直说，别猜
        return {"status": "error", "message": "no sandbox working directory"}
    ...
```

这个值由 runtime 在每次工具调用前后绑定，所以即使一个进程里同时跑着多个会话，
拿到的也一定是*本轮*的工作区。正因如此，这个示例把 `workspace_root` 和 `reuse_workspace`
都留空：每个 `(app, user, session, agent)` 各得一个目录，并且照样能跨该会话的多轮存活——
第二轮依赖的正是这个特性。

当调用栈上没有 codex 轮次时（换了 runtime、被 `AgentTool` 调用、单元测试），
`current_workspace()` 返回 `None` 而不是抛异常。这里的工具因此把它转成一条普通的
`{"status": "error", ...}` 结果交给模型，而不是抛异常，也不是悄悄退回到自己的某个本地目录。

**钉死目录如今是单租户下的便利，而不是多租户的答案。**
`workspace_root=..., reuse_workspace=True` 让目录变成一个常量，进程退出很久之后你依然能
`ls` 它——在自己机器上开发单个 Agent 时很好用，放到服务端就是错的：它会把所有会话压到同一个目录。
不钉死时，工作区位于 runtime 自己的临时根目录下，进程退出即被清理，
所以 `main.py` 会在结束前先把目录树打印出来。

## 安全配置本身就是这个示例的内容

```python
CodexRuntimeConfig(
    sandbox="workspace_write",   # 只能写自己的工作区
    network_access=False,        # 只有 workspace_write 会读它：沙箱内没有任何 socket
    approval_mode="deny_all",    # 拒绝 Codex 提出的一切提权
    max_tool_iterations=8,       # 整轮允许的 ADK 工具往返次数
)
...
run_config = RunConfig(max_llm_calls=60)   # 硬性成本上限
```

这四行讲的是一个完整的故事：

- 模型可以对数据做**任何**计算——这正是我们要的——但网络关掉之后，它没有任何 socket 把结果送出去。
  `outbox/` 刻意放在工作区**之外**，所以沙箱也写不到那里。
- 于是两个受审计的 ADK 工具成了**唯一**的出口。每一个离开沙箱的文件都经过 `publish_report`：
  有日志、有大小上限、有摘要，并且拒绝任何非工作区内的、非 `.md`/`.svg` 的文件。
  这是一条你可以指给审计人员看的边界。
- `approval_mode="deny_all"` 维持这条边界。**永远不要用 `"auto_review"`**：
  名字有迷惑性，它其实是*全自动批准*——Codex SDK 内置的审批处理器会接受一切提权请求，且无法替换。
- `max_tool_iterations` 约束的是**整轮**的 ADK 工具往返次数（默认 32），它不是成本上限；
  成本上限是 `RunConfig(max_llm_calls=...)`。codex 是唯一能精确执行这个预算的外部 runtime——
  shim 会在每次后端调用**之前**扣减它。

## 为什么数据是脏的

`data/sales_2025q3.csv` 是一份真实感的数仓导出，也就是说它以四种最常见的方式一团糟：

| 缺陷 | 行数 | 天真的脚本会怎样 |
| --- | --- | --- |
| 数值列里带千分位（`"4,208.40"`） | 22 | `ValueError: could not convert string to float: '4,208.40'` |
| 一个空的金额单元格 | 4 | `ValueError: could not convert string to float: ''` |
| 第二种日期格式（`07/23/2025`） | 31 | `ValueError: time data '07/23/2025' does not match format '%Y-%m-%d'` |
| 同一个地区的三种写法（`north`、`NORTH`、`_South`） | 14 | 不报错——悄悄把一个地区拆成三个 |

**第一处缺陷出现在第 212 行**，所以 `head` 看上去一切正常，
第一版脚本是对着一个「看起来没问题」的文件写出来的。

**提示词里对此只字未提。** 这是刻意的：如果 instruction 把缺陷都描述清楚，
模型第一版就会写出防御性的解析器，那这个示例也就演示不出任何 `runtime="adk"` 做不到的东西了。
第一版脚本必须真的崩，这个循环才是真的。

最后一行最有意思——它不会崩，所以只有*会去看自己输出*的 Agent 才抓得到。
报告里的 `Data notes` 小节就是为此存在的。

## 关于那个 skill

`skills/sales-report/SKILL.md` 承载报告的固定格式（章节、列顺序、金额格式、手写 SVG 的规则）。
它以 ADK 原生方式加载，并被 materialize 进 Codex 自己的 skill 目录，
由 Codex 原生的 skill 系统发现和渐进加载。它在这里值得存在有两个理由：
格式不必占用提示词；而它的 `Data notes` 小节让 Agent 的迭代过程在最终产物里显形。

## 运行

```bash
pip install "veadk-python[codex]"   # openai-codex + 自带的 Codex CLI 二进制

export MODEL_AGENT_API_KEY=...
export MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
export MODEL_AGENT_NAME=deepseek-v4-flash-260425   # 见「已知的粗糙之处」：选哪个模型很关键

# 已知问题：VeADK 默认开启的 prompt caching 与 Codex 必带的 `instructions` 字段冲突，
# Ark 会返回 400（"caching is not supported for instructions"）。暂时关掉：
export MODEL_AGENT_CACHING=disabled

python examples/codex_data_analysis/main.py
```

仅支持 macOS 与 Linux——沙箱依赖 seatbelt / landlock+seccomp。

### 该看什么

`main.py` 会把每一条沙箱内执行的命令打印出来，因为 runtime 把 Codex 自己的
`commandExecution` 条目转成了普通的 ADK function-call 事件：

```
  → fetch_sales_extract({'quarter': '2025Q3'})
  ← fetch_sales_extract: {'status': 'ok', 'path': 'data/sales_2025q3.csv', 'rows': 2400, ...}
  $ cat .../skills/sales-report/SKILL.md
  $ head -20 data/sales_2025q3.csv                    # 看上去一切正常
  $ cat > analyze.py << 'PY' ... PY; python3 analyze.py
    exit=1
    | ValueError: could not convert string to float: ''
  $ cat > analyze.py << 'PY' ... PY                   # 重写
  $ python3 -c "... 把出问题的行找出来 ..."
  $ cat > build_report.py << 'PY' ... PY; python3 build_report.py
  $ cat report.md
  → publish_report({'report_path': 'report.md', 'chart_path': 'chart.svg'})
  ← publish_report: {'status': 'ok', 'published': [...]}
```

这是一段真实记录（略作删节）：12 条沙箱命令，其中 2 条失败；`head -20` 什么问题都看不出来，
因为第一处缺陷在再往下 190 行的位置。第二轮接着读了它自己留下的 report 和 chart，
只替换了图和 Trend 段落，并从一次 `zsh` 引号错误里恢复过来，然后重新发布。
请把它当作一种「形状」而不是固定命令——回合数每次都不一样。

这次运行结束前会把 Codex 留在工作区里的东西（它的脚本、它的草稿）打印出来——
那个目录属于本会话，进程退出时会被 runtime 清理。留在磁盘上的是 outbox：

```bash
cat examples/codex_data_analysis/outbox/*/report.md
```

报告里的 `Data notes` 小节会列出它绕过的缺陷——和上面那张表对照一下，看它抓到了多少。
在上面那次运行里，它报出了四类缺陷中的三类并给出了准确行数（4 行空金额、31 行日期格式不一致、
14 行地区写法不一致），第四类则是默默处理掉了；所有发布出来的数字都和真实值分毫不差。

## 已知的粗糙之处（截至撰写时）

以下都是 runtime / 后端的问题，不是这个示例的 bug。它们直接影响了上面的代码写法，
在你基于它开发之前值得先知道。

- **在该 runtime 下 Ark 会拒绝 VeADK 默认开启的 prompt caching。** Codex 总会带上
  Responses 的 `instructions` 字段，而 Ark 返回
  `400 InvalidParameter: caching is not supported for instructions`。
  在你设置 `MODEL_AGENT_CACHING=disabled` 之前，任何跑在 Ark 上的 codex-runtime Agent
  都会在第一次后端调用时失败。
- **不是每个 Ark 模型都能当后端，而且失败是静默的。** 第一个工具回合之后，
  Codex 会把自己的 `reasoning` 条目重放进对话，shim 原样转发给后端。
  `doubao-seed-1-6-250615` 会返回
  `400 InvalidParameter: input[N].reasoning ... Item reasoning is not supported for model`。
  但你看到的**不是**报错：第一次后端调用成功，Agent 只跑了一条命令，
  这一轮就以 `status=completed` 结束，留下一个半成品工作区和一段像模像样的总结。
  那个 400 只会以 `codex_backend_api_error` 警告的形式出现在日志里，**不会**抛给调用方。
  请使用 `deepseek-v4-flash-260425`（已端到端验证）；当一个 codex 轮次结束得可疑地早时，
  先在日志里 grep 一下 `codex_backend_api_error`，再决定要不要相信那个回答。
- **被桥接进 Codex 协议的聊天模型会“讲解”而不是“动手”。** Codex 收到 assistant 消息就结束这一轮，
  所以模型如果回一句*“我现在来写分析脚本”*，这一轮就会什么都没做地结束。
  这正是 instruction 开头就写 *“Act, do not narrate”* 的原因。
  在任何聊天后端上，都要预留一部分提示词预算来处理这件事。
- **`apply_patch` 根本到不了后端，`request_user_input` 也没人能回答。** shim 只转发
  `function` 类型的工具，而 Codex 的文件编辑工具不是——后端实际看到的列表是 `exec_command`、
  `write_stdin`、`update_plan`、`request_user_input`、`view_image`，外加你自己的 ADK 工具。
  但 Codex 自己的系统提示词仍然告诉模型去用 `apply_patch`；`request_user_input` 也照样被通告出去，
  尽管一次 ADK 调用根本没有可以回答它的交互通道。
  **runtime 现在会在每轮的 developer instructions 后面追加一段工具可用性说明**，
  把这两件事以及替代做法（用 `exec_command` 的 heredoc 写文件；自己拿主意而不是提问）讲清楚。
  这个示例的 instruction 从前要手写这两句，现在不需要了。

一般性的教训是：在聊天后端上，这个 runtime 实际可用的工具面比 Codex 文档给人的印象要窄。
这两个缺口 runtime 已经替你补上了，其余的仍然要靠你的 instruction。

## 约束

`runtime="codex"` 会直接拒绝 `Agent` 的一大片配置面，而不是默默忽略。与本例相关的有：

- 被拒绝：`sub_agents`、`model=`（请用 `model_name=`）、`output_schema`、`planner`、
  `code_executor`、`include_contents="none"`、`enable_supervisor`，
  以及 `generate_content_config` 里除 `system_instruction` 之外的任何字段；
- 同样被拒绝：`CodexRuntimeConfig(sandbox="full_access", network_access=False)`
  ——这个组合读起来像“没有网络”，实际却是全权限；
- 带告警丢弃：`knowledgebase`、`example_store`、`skills_mode` 等。

详见[支持矩阵](../../docs/content/docs/framework/agent/runtime.mdx#支持矩阵)。
