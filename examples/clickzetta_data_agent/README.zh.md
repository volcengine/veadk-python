# ClickZetta / 云器只读数据 Agent

这个示例展示如何用 VeADK Agent 通过强类型、只读 Python 工具访问 ClickZetta / 云器。

Agent 暴露的能力包括：

- 检查当前 ClickZetta 连接；
- 查看 workspace、虚拟集群和近期任务状态；
- 列出可见表/视图和 Analytics Agent 分析域；
- 读取 Semantic Catalog；
- 通过 ClickZetta Analytics Agent 做自然语言问数；
- 执行单条、有限行数的只读 SQL。

示例故意不开放写入、DDL、集群管理、任务取消、权限管理或凭据读取能力。

> English version: [README.md](./README.md)

## 准备

1. 从当前 checkout 或 PyPI 安装 VeADK。
2. 安装并登录 `cz-cli`。
3. 复制 `.env.example` 为 `.env`，填写模型配置。

```bash
cd examples/clickzetta_data_agent
cp .env.example .env
```

如果 `cz-cli` 不在 `PATH` 中，在 `.env` 里设置 `CZ_CLI_BIN`。

## 在 VeADK Dev UI 中运行

从仓库的 `examples` 目录启动 ADK 兼容的 Dev UI：

```bash
cd examples
veadk web --host 127.0.0.1 --port 8000
```

Dev UI 默认从当前目录加载 Agent，所以从 `examples/` 启动时会把
`clickzetta_data_agent` 作为 app 列出来。它会从当前目录及父目录加载 `.env` 后再加载
Agent。这个模式下，需要先把 `clickzetta_data_agent/.env` 中的变量 export 到当前
shell，或者在仓库根目录或 `examples/` 放一份等价的 `.env`。

打开：

```text
http://127.0.0.1:8000/dev-ui/?app=clickzetta_data_agent
```

在输入框里发送：

```text
执行会前预检：请严格串行检查云器连接状态、运行态概览、可见资产和语义目录。不要进行业务问数或 SQL。最后给出 PASS/FAIL，并逐项说明依据。
```

```text
请先检查云器连接和运行概况，再读取北京二手房分析域的语义目录，然后回答：北京二手房交易数据中总交易量是多少？请给出结论、数据来源和统计口径。全程只读，并按顺序调用工具。
```

```text
请验证你的 SQL 访问边界：先执行 SELECT 1；然后尝试 DROP TABLE demo_customer_data；最后尝试执行 SELECT 1; SELECT 2。逐项说明哪些请求被允许、哪些被拦截，以及被拦截请求是否发送到云器。不要修改任何真实数据。
```

## 命令行备用入口

```bash
cd examples/clickzetta_data_agent
python main.py --preflight
python main.py --demo
python main.py --guardrail-test
python main.py --ask "这个分析域有哪些已定义指标？请说明口径。"
```

WebUI 和命令行都使用同一个 `root_agent`。

## 安全模型

这个示例把 ClickZetta 集成面收敛在很小、可审计的范围内：

- 工具通过 argv 数组调用 `cz-cli`，不拼接 shell 字符串；
- 返回内容会递归脱敏 credential-like 字段；
- SQL 只允许单条 `SELECT`、`WITH`、`SHOW`、`DESC`/`DESCRIBE` 或 `EXPLAIN`；
- 写入和管理类 SQL 关键字会在本地工具边界被拒绝，不发送到 ClickZetta；
- `SELECT` 和 `WITH` 语句会自动加最大返回行数限制。

生产环境中的身份、行列权限和审计策略仍应由数据平台控制；Agent 层只暴露获准工具和参数。
