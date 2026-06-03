# basic-app · 向火山引擎 AgentKit 部署一个带前后端的 Agent

一个最小的**完整应用**：单个容器同时提供 Agent API 与 Web 前端，使用
`veadk agentkit` 命令部署到[火山引擎 AgentKit](https://www.volcengine.com/)。

> English version: [README.md](./README.md)

## 目录结构

```text
basic-app/
├── app.py                       # 前后端一体服务（部署入口）
├── agents/
│   └── basic_app_agent/         # 后端 Agent（已开启 A2UI），暴露 root_agent
├── agentkit.yaml                # AgentKit 部署配置（已接入 build_script）
├── scripts/install_veadk.sh     # 构建时从 feat/a2ui 安装 veadk[a2ui,pdf]
├── requirements.txt             # 留空（veadk 由构建脚本安装）
├── .dockerignore
└── .env.example
```

- **后端** —— `agents/basic_app_agent` 是一个普通的 VeADK `Agent`，开启了
  `enable_a2ui=True`，因此可以用富文本、声明式 UI 作答。
- **前端** —— 构建好的 Web UI **随 veadk 包一起发布**（位于 `veadk/webui`）。
  `app.py` 会挂载它，所以只要装好 veadk[a2ui]，容器就具备了全部内容，
  无需额外打包前端。
- **单进程** —— `app.py` 构建 Google ADK 的 FastAPI 应用
  （`/list-apps`、`/run_sse`、会话等），并把 UI 挂载到 `/`，监听 8000 端口。
  AgentKit 用 `python -m app` 运行它。

> 前端（`veadk/webui`）与 A2UI 的 Python 支持尚未发布到 PyPI/`main`，它们在
> **`feat/a2ui`** 分支上。因此镜像通过 `scripts/install_veadk.sh` 从该分支安装
> veadk —— 用**浅克隆 + sparse**、走 HTTP/1.1，只拉取 `veadk/` 包。理论上
> `pip install git+...@feat/a2ui` 也可以，但仓库庞大的 docs 历史会让整仓克隆在
> 构建网络里很慢且不稳定，所以改用这种定向克隆。

## 1. 配置

```bash
cd examples/basic-app
cp .env.example .env
# 编辑 .env：MODEL_AGENT_API_KEY + VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
```

`veadk agentkit` 会使用火山引擎 AK/SK 进行构建与部署。

## 2. 本地运行（可选）

```bash
pip install "veadk-python[a2ui,pdf]"
python app.py            # 或：python -m app
# 打开 http://127.0.0.1:8000
```

你应当能看到 Web UI；试着问“给我一张航班状态卡片”，Agent 会用富 A2UI 作答。
`/list-apps` 返回 `["basic_app_agent"]`，`/ping` 返回 `{"status": "ok"}`。

### 附件（图片 / PDF）

输入框的 **+** 按钮可上传**图片**与 **PDF**。图片会直接发送给（具备视觉能力的）
模型；PDF 则由 `before_model_callback`（`veadk.utils.pdf_to_images`）渲染为逐页
图片后交给模型识别——这需要 `pdf` 额外依赖（已包含在上面的 `[a2ui,pdf]` 中），
并使用具备视觉能力的模型（默认的 `doubao-seed-1.6` 即可）。

## 3. 部署到 AgentKit

```bash
# 交互式填写 agentkit.yaml 中与账号相关的字段
veadk agentkit config

# 一步完成镜像构建与部署
veadk agentkit launch

# 上线后查看状态 / 发送测试请求
veadk agentkit status
veadk agentkit invoke "你好，做一张今天的天气卡片"
```

`veadk agentkit launch` = `build` + `deploy`。使用 `veadk agentkit destroy`
可销毁运行时。

## 前端是如何进入容器的

AgentKit 构建的 Docker 镜像，其构建上下文就是**当前目录**（`COPY . .`），
并以 `python -m app` 运行。Web UI 并不是从这里拷贝的 —— 当构建脚本从
`feat/a2ui` 分支安装 `veadk[a2ui]` 时，它**随 veadk 包**（`veadk/webui`）一起
进入容器。`scripts/install_veadk.sh` 通过 `agentkit.yaml` 里的
`docker_build.build_script` 接入，在镜像构建期间执行。

为什么用构建脚本而不是一行 `pip install git+...`：整仓克隆 veadk（庞大的
docs/图片历史）在构建网络里多次中途失败（`curl 92 HTTP/2 stream not closed
cleanly`）。脚本让抓取又小又稳 —— `--depth 1 --filter=blob:none --sparse`
只拉取 `veadk/` 包，走 HTTP/1.1，并带重试（约 4 MB，而非整个仓库）。
