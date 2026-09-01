# 运维故障定位助手（`runtime="codex"`）

> English version: [README.md](./README.md)

**模型可以读取一整天的生产日志，却在物理上无法把它们传出去。** 它运行在操作系统级
沙箱里，`network_access=False`——没有任何 socket 可以把数据送出；它也只能写自己的
临时目录。通往外部世界的唯一通道是 `file_incident_ticket`，一个你自己写的 ADK
工具，它的参数你可以记录、校验、截断。

这就是对"我敢让大模型碰我的日志吗"这个问题的回答，也是本示例存在的理由。

它做什么：一个 on-call 智能体去调查一起它从未见过的故障。ADK 工具从内部系统拉取
原始日志、指标序列和发布记录，作为文件落进沙箱。随后 Codex 在沙箱里自己写 shell 和
Python 去 grep、聚合、做时间关联——写好几个程序，边看数据形态边改——最后开出一张
工单，给出根因和支撑它的具体数字。

```
                 ┌── ADK 工具（你的代码，你的进程）────────┐
   内部           │  fetch_application_logs                 │      workspace/
   系统    ───►   │  fetch_service_metrics    写文件 ───────┼───►  logs/*.log
                 │  fetch_deploy_history                   │      metrics/*.csv
                 └─────────────────────────────────────────┘      deploys/*.json
                                                                       │
                          ┌────────────────────────────────────────────┘
                          ▼
        Codex 在操作系统沙箱内：没有网络，也不能写工作区以外的任何位置。
        它写 analysis/*.py，运行它们，读输出，再写下一个。
                          │
                          ▼  file_incident_ticket(...)  ← 唯一的出口
                     outbox/INC-....json   （在工作区之外，沙箱够不到）
```

## 为什么这个任务适合 codex 而不是 adk

先说实话：对绝大多数智能体来说，`runtime="codex"` 严格劣于默认的 `runtime="adk"`。
它每一轮都要拉起一个子进程，把整段对话重新序列化进提示词，还拒绝一大批 ADK 能力。
只有当智能体真正的工作就是**运行它刚写出来的代码**时，这些代价才值得。临时性的日志
分析正是这种情况：

- **你没法为每个问题预先造一个工具。** "14:00 之后哪个错误签名的频率变了？""连接池
  是在延迟上升之前还是之后打满的？""这个模式一周前有没有出现？"——对一个日志文件
  有用的聚合方式是无穷的，每次新故障都会问出新的一个。按问题造工具是没有尽头的
  跑步机，解释器不是。
- **数据放不进上下文，而且模型不会数数。** 一天就是 7,494 行日志（1.4 MB）加 8,640
  行指标。就算你愿意付钱把它们贴进去，"951 次支付超时 vs 640 次连接池超时"也应该
  交给 `collections.Counter`，而不是靠模型阅读。执行代码给出的是精确数字，摘要式
  提示词给出的是听起来合理的数字。
- **做对需要好几轮。** 在我们的实测里，智能体先看了日志文件的头部，发现它并非全是
  JSON，然后写了一个按小时统计错误签名的直方图，接着是变化点定位脚本、指标聚合
  脚本、连接池饱和度校验脚本——每一个都基于上一个的结论。这个循环正是 Codex 的
  原生工作方式：一次模型轮次里跑很多条命令，程序输出留在它自己的循环里，而不是
  一个字节一个字节地穿过你的事件流。
- **沙箱才让这件事变得可以接受。** 让模型对着生产日志写并执行任意代码，只有在这些
  代码碰不到网络和磁盘其余部分时才是理智的。这是运行时的属性，不是一句 prompt 能
  承诺的东西。

最接近的替代方案是 `runtime="adk"` 配 ADK 的 `code_executor`。诚实地比较：
`UnsafeLocalCodeExecutor` 在你自己的进程里执行模型写的代码；`ContainerCodeExecutor`
需要你运维一个 Docker daemon；`VertexAiCodeExecutor` 是 Google 的托管服务。codex
运行时给你的是本机上的操作系统级沙箱（macOS seatbelt / Linux landlock+seccomp）、
一个贯穿整个会话的工作目录，以及一次模型轮次内跑很多条命令的智能体循环，而不是
一次 LLM 调用一个代码块。

### 什么时候**不要**用这个运行时

- **问题是固定的。** 如果 on-call 永远只问"昨天有多少 5xx"，那就写那个工具。更便宜、
  更快、确定性更好、也可测试。
- **你需要这个运行时替换掉的 ADK 能力。** `veadk/runtime/compat.py` 会直接拒绝
  `sub_agents`、`model=`（请用 `model_name=`）、`output_schema`、`planner`、
  `code_executor`、`include_contents="none"` 和 `enable_supervisor`，并会警告
  `knowledgebase`、`example_store`、模型 fallback 链、按 LLM 调用的 callback 和
  按调用的 tracing span 都会被丢弃。移植智能体之前请先读那个文件。
- **单轮延迟或成本是约束。** 每一轮都会拉起一个 Codex 子进程，而沙箱循环会在一轮内
  发起多次后端调用。
- **数据绝对不能落到这台机器上。** 工作区是运行智能体那台机器上的真实目录。

## 让 ADK 工具在这里正确工作的那条规则

**工作区是数据平面，工具的参数和返回值是控制平面。**

`runtime="codex"` 下的 ADK 工具并不在沙箱里执行。VeADK 的 shim 在你的进程里执行它，
并把它返回的任何东西作为函数调用结果粘进模型的上下文。所以一个返回 7,494 行日志的
工具并不是"把日志给了模型"——它会毁掉这一轮，而且模型之后还是得去 grep 那段文本。

因此这里每个 `fetch_*` 工具都往工作区写一个文件，然后返回一张**回执**：

```python
{"status": "ok",
 "path": "logs/checkout-api-prod_20260824T0000_20260825T0000.log",
 "lines": 7494, "bytes": 1396879,
 "note": "one event per line, chronological; content not returned"}
```

大约 40 个 token，而不是 40 万个。模型拿到指针，沙箱拿到字节。这是把 ADK 工具和这个
运行时结合时最重要的一件事，两个方向都成立：

- **工具通过写文件把数据交进去**，返回路径，外加足够的形态信息（行数、列名、单位）
  供模型规划。
- **模型通过工具参数把结论交出来**——参数很小、有结构，而且校验权在你手里：
  `file_incident_ticket` 会限制字段长度、检查 severity 枚举，并为每张工单打印一行
  审计日志。

## 安全配置，逐项拆解

```python
codex_runtime_config=CodexRuntimeConfig(
    sandbox="workspace_write",
    network_access=False,
    approval_mode="deny_all",
    workspace_root=str(WORKSPACE),
    reuse_workspace=True,
    max_tool_iterations=12,
    tool_timeout_seconds=60.0,
)
...
run_config=RunConfig(max_llm_calls=40)
```

| 配置项 | 它阻止了什么 |
| --- | --- |
| `sandbox="workspace_write"` | 模型写的代码**只能**在工作区（以及临时目录）里创建和覆盖文件。它碰不到你的源码树、你的 dotfiles，也碰不到 `outbox/`。Codex 会被明确告知它的可写根目录，而那恰好就是这三个。 |
| `network_access=False` | 没有 socket。模型读得到生产日志，却无处可送。只有 `workspace_write` 沙箱会遵守这个开关——`read_only` 和 `full_access` 会忽略它，而 `full_access` + `network_access=False` 现在会直接抛错，而不是假装做了隔离。 |
| `approval_mode="deny_all"` | 拒绝一切越出沙箱的提权请求。**永远不要在示例或生产里用 `"auto_review"`**：它不是审核步骤。Codex SDK 内置的处理器会接受每一个提权请求且无法替换，所以它等于全自动放行。 |
| `RunConfig(max_llm_calls=40)` | 给自驱循环设一个硬上限。在 `codex` 下，预算是在每次后端调用**之前**扣的，所以卡点是精确的，不会晚一次。 |
| `max_tool_iterations=12` | **整轮**允许的 ADK 工具往返次数（不是每次后端请求）。四次抓取加一次开单绰绰有余。 |
| `tool_timeout_seconds=60.0` | 卡住的 ADK 工具不会把整轮挂死。 |
| `outbox/` 在工作区之外 | 出口是一条你拥有的代码路径，而不是模型可以随手丢文件的地方。 |

这是可以验证的，不是口号。让智能体在它自己的沙箱里试一下：

```
touch ./inside-ok          -> exit 0
touch ../outbox/ESCAPED    -> touch: ../outbox/ESCAPED: Operation not permitted
touch ../ESCAPED2          -> touch: ../ESCAPED2: Operation not permitted
```

**有一件事 `workspace_write` 不做：它不限制*读取*。** 这个沙箱允许读取文件系统，
只约束写入。数据出不去——没有网络，唯一的出口是一个你能检查其载荷的工具——但如果
这台机器上有你根本不希望模型读到的密钥，请把智能体放进容器或专用机器里跑。

## 这起故障的标准答案，方便你核对

一切都由 `ops_backend.py` 用固定随机种子确定性生成，所以每台机器上出现的都是同一起
故障。**2026-08-24 UTC** 的标准答案：

- **根因。** `checkout-api 4.11.0` 于 **14:07:55Z** 发布，把 worker 并发从 8 提到
  32，而数据库连接池仍然是 20。一个新的错误签名
  `db.pool acquire timeout after 5000ms` 在**当天 14:11:02Z 之前始终为零**，之后
  一路涨到 640 条。`db.pool.in_use` 从约 6 爬升并恰好卡死在 `db.pool.size` = 20；
  p99 延迟从 180 ms 涨到 5,200 ms，5xx/分钟从 0.5 涨到 9.0，且都持续到窗口末尾。
- **诱饵一：最吵的错误。** `payments.gateway timeout` 是数量最多的 ERROR（951 条，
  比真正的签名 640 条还多），而它整天、以及整个上一周都稳定在 35–45 条/小时。按
  数量排序会选中它，而它只是长期噪声。
- **诱饵二：另一次发布。** `notify-worker 2.3.1` 在 13:52:40Z 上线，比真正的那次早
  十五分钟，并立刻带来 124 条 `notify.webhook retry exhausted` 错误。这波爆发六分钟
  后自己停了。"怪罪错误之前最近的那次发布"会选中它。
- **诱饵三：仪表盘上最大的那个数。** `notify.queue_depth` 在 13:52 到 14:25 之间从
  12 冲到 **900**，峰值出现在真正的起点*之前*，之后完全恢复。它的幅度碾压其他任何
  指标变化。
- **应当被排除的假设。** `checkout.rps` 两天完全一致，所以这不是流量驱动的故障。
- **一次 grep 一定不够**，这是设计出来的：答案需要按小时按签名计数、需要找变化点、
  需要对长格式 CSV 做透视、还需要和发布记录做关联——而发布记录的时间戳来自
  **UTC+08:00** 的 CI 系统，日志是 UTC，指标是 epoch 秒。此外日志流并不统一：约
  14% 的行是 sidecar 的纯文本输出，对每一行做 `json.loads` 会抛异常。

追问的第二轮问的是 **2026-08-17**，即一周前的同一个星期几。正确答案是*没有*：零条
连接池超时，指标平稳，只有同样的长期支付噪声。

## 我们实际跑出来的结果

Ark `deepseek-v4-pro-260425`，完整的两轮会话，跑了四次。

**第一轮四次都找到了预期的根因。** 4 次 ADK 工具调用、10–12 条沙箱命令、3.5–4 分钟。
每次的形态一致：先读 runbook skill，拉取三个数据源，`head` 日志和 CSV——正是这一步
让它发现日志流并非全是 JSON，并写出会跳过非 JSON 行的解析器——然后在 `analysis/` 下
写并运行一系列独立程序，每一个都在回答上一个提出的问题：按小时的签名直方图、变化点
定位、指标聚合、发布前后对比。

每张工单都点名了 `checkout-api 4.11.0`、并发 8→32 对上大小为 20 的连接池，都正确地
把 `22:07:55 +0800` 换算成了 `14:07:55Z`，并在证据里明确排除了两个诱饵发布和长期
存在的支付超时。原文摘录一条证据：

> `db.pool.in_use: before avg=6.0 (max=8.0), after avg=19.2 (max=20.0).`
> `Saturated (in_use >= pool size of 20) for 531/592 minutes (89.7%) after deploy.`

**出问题的是第二轮，两次，原因非常具体。** 四次里有两次干净地在 1–8 条沙箱命令内
答完，复用了第一轮的分析而不是重新推导。另外两次卡住了：第一轮写的脚本把 08-24 的
文件名写死了，模型没有把它参数化，而是开始重命名数据文件去迁就脚本——`mv`、运行、
`rm`、再 `mv` 回来——一直循环到 `RunConfig(max_llm_calls=40)` 把这一轮切断。这是
上限在正常工作而不是 bug；`main.py` 会捕获并打印
`[budget] the turn hit the 40-call ceiling`。但这也是一个公道的提醒：自驱循环需要
预算，光靠良好意愿不行。

这次失败也正是 skill 最后一段的由来。在 runbook 里加一行——*把输入路径作为
`sys.argv[1]` 接收，绝不写死*——就把第二轮变成了一次干净的调用：

```
[sandbox 1] python3 analysis/error_signatures.py logs/checkout-api-prod_20260817T0000_20260818T0000.log
```

关于"迭代"的诚实说明：**第一轮从未产生过失败的命令。** 它的迭代是"逐步细化"型的
（每个程序都是为了回答上一个程序带出的问题），而不是"崩溃后修复"型——模型在解析前
先看了文件，从而避开了混合格式的坑，这本来也正是你希望它做的。我们确实看到的失败
命令（三条 `exit 1`）来自第二轮的那个死胡同。请预期波动：能力更弱的模型会失败得更
多，你会在 `main.py` 打印的 `[sandbox N] -> exit ...` 行里看到。

## 关于 skill

`skills/incident-triage/SKILL.md` 就是你们团队的故障定位 runbook——先拉全部数据源、
刻画签名而不是给签名排名、定位变化点、和发布记录关联、在指标里验证、解释机理、只开
一张工单。驱动它的是 Codex 的**原生** skill 系统：VeADK 把 ADK 的 `SkillToolset`
物化到 `$CODEX_HOME/skills/`，Codex 自己发现并加载（我们那次运行的第一条沙箱命令就是
Codex 在读这个 SKILL.md）。

它刻意只编码**方法，不编码答案**——从不提及日志格式、时区陷阱，也不点名任何一个
诱饵。这才让它成为 runbook 而不是剧透，也正因如此智能体仍然得自己把活干完。

## 运行方式

```bash
pip install "veadk-python[codex]"       # openai-codex + 自带的 Codex CLI
cd examples/codex_ops_assistant
cp .env.example .env                    # 填入你的方舟 API Key
python main.py
```

仅支持 macOS 或 Linux：沙箱是 seatbelt / landlock+seccomp。请选一个工具调用和写代码
都过关的模型——这个智能体要给自己的脚本 debug——换模型之前请先读下面两个方舟坑。

跑完之后看看沙箱产出了什么：

```bash
ls workspace/analysis/     # 模型写的那些程序
cat outbox/INC-*.json      # 所有离开沙箱的内容
```

`main.py` 会在启动时删掉 `workspace/` 以保证每次运行可复现；去掉那一行就能看到工作区
跨多次运行地累积。

## 换模型前值得知道的两个方舟坑

**1. 提示词缓存搭不了 Codex 这班车。** VeADK 默认开启方舟提示词缓存
（`extra_body={"caching": {"type": "enabled"}}`），而 Codex 总是会发送顶层的
`instructions` 字段，方舟拒绝这个组合：

```
InvalidParameter: The parameter `instructions` specified in the request are not
valid: caching is not supported for instructions.
```

codex 的 shim 会替你把 `extra_body` 里的 `caching` 和 `expire_at` 剔掉，所以你不用
做什么——但 codex 运行时会原样转发 `model_extra_config` 的**其余部分**（与 `piagent`
不同，后者是整个丢弃），所以一个后端不认识的 body 字段会让每一轮都 400，智能体只
返回空字符串。如果你真的看到上面那个错误，请设 `MODEL_AGENT_CACHING=disabled`，或者
传 `model_extra_config={"extra_body": {"caching": {"type": "disabled"}}}`。

**2. 不是每个方舟模型都能接受 Codex 的对话结构。** Codex 会在请求的 `input` 里回放
`reasoning` 项。不支持它们的模型会在第一轮工具调用之后中途终止：

```
InvalidParameter: The parameter `input[3].reasoning` ... Item reasoning is not
supported for model: doubao-seed-1-6, version: 250615
```

我们在 `doubao-seed-1-6-250615` 上就遇到了：智能体抓取了两个文件、跑了一条 `grep`，
然后在调查中途挂掉。`deepseek-v4-pro-260425`（这里的默认值）能接受并跑完。换新模型
之前，先用一个短轮次试一下。

## 文件说明

| 文件 | 是什么 |
| --- | --- |
| `main.py` | 智能体、沙箱配置，以及一个会把每条沙箱命令都叙述出来的两轮会话。 |
| `ops_tools.py` | 四个 ADK 工具：三个往工作区写文件并返回回执，一个把工单写进 `outbox/`。 |
| `ops_backend.py` | 被模拟的内部可观测性系统。确定性生成；故障和诱饵都定义在这里。 |
| `skills/incident-triage/SKILL.md` | 故障定位 runbook，由 Codex 原生 skill 系统驱动。 |
