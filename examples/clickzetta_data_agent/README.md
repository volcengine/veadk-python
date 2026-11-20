# ClickZetta Read-Only Data Agent

This example shows how to expose ClickZetta / Yunqi data capabilities to a
VeADK agent through typed, read-only Python tools.

The agent can:

- inspect the active ClickZetta connection;
- summarize workspace and recent job status;
- list visible tables/views and Analytics Agent domains;
- read a semantic catalog;
- ask ClickZetta Analytics Agent a natural-language data question;
- run a single bounded read-only SQL statement.

The example intentionally does not expose write, DDL, cluster-management, job
cancel, permission-management, or credential-reading operations.

> 中文版见 [README.zh.md](./README.zh.md)

## Prerequisites

1. Install VeADK from this checkout or from PyPI.
2. Install and authenticate `cz-cli`.
3. Copy `.env.example` to `.env` and fill in the model settings.

```bash
cd examples/clickzetta_data_agent
cp .env.example .env
```

If `cz-cli` is not on `PATH`, set `CZ_CLI_BIN` in `.env`.

## Run in the VeADK Dev UI

From the repository's `examples` directory, start the ADK-compatible Dev UI:

```bash
cd examples
veadk web --host 127.0.0.1 --port 8000
```

The Dev UI loads agents from the current directory by default, so starting from
`examples/` makes `clickzetta_data_agent` appear as an app. It also loads `.env`
from the current working directory or parents before loading the agent. For this
mode, export the values from `clickzetta_data_agent/.env` into the shell first,
or place a matching `.env` in the repository root or `examples/`.

Open:

```text
http://127.0.0.1:8000/dev-ui/?app=clickzetta_data_agent
```

Try these prompts in the input box:

```text
执行会前预检：请严格串行检查云器连接状态、运行态概览、可见资产和语义目录。不要进行业务问数或 SQL。最后给出 PASS/FAIL，并逐项说明依据。
```

```text
请先检查云器连接和运行概况，再读取北京二手房分析域的语义目录，然后回答：北京二手房交易数据中总交易量是多少？请给出结论、数据来源和统计口径。全程只读，并按顺序调用工具。
```

```text
请验证你的 SQL 访问边界：先执行 SELECT 1；然后尝试 DROP TABLE demo_customer_data；最后尝试执行 SELECT 1; SELECT 2。逐项说明哪些请求被允许、哪些被拦截，以及被拦截请求是否发送到云器。不要修改任何真实数据。
```

## Run from the command line

```bash
cd examples/clickzetta_data_agent
python main.py --preflight
python main.py --demo
python main.py --guardrail-test
python main.py --ask "这个分析域有哪些已定义指标？请说明口径。"
```

Both entry points use the same `root_agent`.

## Safety model

The ClickZetta integration is deliberately small and auditable:

- tools call `cz-cli` with argv arrays, never shell string interpolation;
- returned data is recursively redacted for credential-like fields;
- SQL is limited to one `SELECT`, `WITH`, `SHOW`, `DESC`/`DESCRIBE`, or
  `EXPLAIN` statement;
- mutating or administrative SQL keywords are rejected before reaching
  ClickZetta;
- `SELECT` and `WITH` statements get a maximum row limit.

Keep production identity, row/column permissions, and audit policy in the data
platform. The agent layer should expose only the approved tools and arguments.
