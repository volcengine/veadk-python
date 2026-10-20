# Studio Sandbox 镜像

在现有 AgentKit Code Sandbox 基础上预装开发环境，不更改 AIO 服务入口

## 镜像内容

- `/home/gem/Projects` 作为默认工作目录
- 独立 VeADK 环境 `/opt/studio-sandbox/venv`，包含 `veadk-python 1.1.9` 和官方 `agentkit-sdk-python 0.8.6` 提供的 `agentkit` 命令
- 固定版本 Python 依赖及 uv 离线缓存，新项目无需再次联网下载
- 默认 Dark Modern，代码和终端使用 Maple Mono v7.9，其他界面字体不变
- Python 语法高亮、BasedPyright 补全、Ruff 格式化和 `.venv` 解释器自动选择
- code-server 与 Jupyter 开启，原 sandbox 启动入口和鉴权方式保持不变

| 插件 | 固定版本 |
| --- | --- |
| Git History | 0.6.20 |
| gitignore | 0.10.0 |
| MDX | 1.8.18 |
| Modern MDX Preview | 1.7.0 |
| Python | 2026.4.0 |
| BasedPyright | 1.40.0 |
| Python Debugger | 2026.6.0，Linux x64 |
| Ruff | 2026.78.0，Linux x64 |
| Even Better TOML | 0.21.2 |

MDX Preview 采用 Open VSX 上的 `ggfincke.vsc-mdx-preview`，固定在兼容基础镜像 Node 22.18 / Code 1.104 的版本，不依赖微软 Marketplace 或 Pylance

构建先校验原始 VSIX，再从本地安装副本中移除可选 `extensionPack` 捆绑列表，避免 Python 插件自动下载 Pylance 或额外插件；插件代码、许可证和必要依赖保持不变

Maple Mono 通过同源 WOFF2 文件和 `@font-face` 提供给浏览器，不要求用户电脑安装字体，字体许可证随文件保留

## 准备构建上下文

在可访问 Open VSX 和 GitHub 的准备环境执行，不能在云流水线内临时下载这些资产

```sh
python3 prepare-context.py \
  --cache /tmp/studio-sandbox-assets \
  --output /tmp/studio-sandbox-context.tar.gz \
  --base-image '<当前区域可访问的 Code Sandbox 镜像引用>'
```

脚本按 `assets.lock.json` 校验 SHA256，仅将 Dockerfile、固定依赖、运行脚本和必要插件/字体打包，排除整个仓库、`.env`、Git 信息和本机虚拟环境

压缩包内 Dockerfile 位于根目录，适用于 CodePipeline 从私有 TOS 下载解压后直接构建

Dockerfile 通过构建参数适配火山引擎和 BytePlus，不写入账号、区域或凭据

- `BASE_IMAGE`：对应区域的基础镜像，准备上下文时注入默认值
- `APT_MIRROR_URL`：默认 `https://mirrors.aliyun.com/ubuntu`
- `PIP_INDEX_URL`：默认 `https://mirrors.aliyun.com/pypi/simple/`
- `NPM_REGISTRY_URL`：默认 `https://registry.npmmirror.com`

BytePlus 可换成部署区域内可访问的官方源或企业镜像源，镜像内不包含 AK/SK、Git 授权或模型密钥

## 新建项目

```sh
studio-project-create my-agent --json
```

生成 `Projects/my-agent/main.py`、独立 `.venv`、`.gitignore`、`README.md` 和 `AGENTS.md`，并执行 `git init --initial-branch=main`，不自动提交或设置远程仓库，依赖从镜像缓存离线安装，不复制其他路径的虚拟环境，不覆盖重名目录

项目名以英文字母开头，允许字母、数字、短横线、下划线，最多 64 个字符；Agent 的 Python 名称会把短横线转换为下划线

初始化失败保留目录供检查，避免误删任何工作内容

## 手动升级编辑器

```sh
studio-vscode-upgrade --check
studio-vscode-upgrade --version 4.136.2
```

检查默认使用 code-server 官方 Release API，有连接超时，不在 Session 启动时执行；可通过 `STUDIO_CODE_SERVER_RELEASE_API` 切换为兼容官方响应格式的企业镜像接口

国内环境建议先把官方安装包校验后放入账号对象存储，再指定下载地址和 SHA256

```sh
studio-vscode-upgrade --version '<版本号>' \
  --archive-url '<国内 HTTPS 下载地址>' \
  --sha256 '<官方 SHA256>'
```

命令要求先保存文件，只准备下一次启动使用的 code-server 版本，重新应用 Maple Mono 字体，不自动重启正在使用的编辑器，不修改项目、插件和用户设置

可用 `--rollback` 选择上一个版本，升级仅影响当前 Sandbox 文件系统，新 Session 的默认版本仍需更新镜像；不要为应用升级销毁正在使用的 Session

基础镜像每次启动覆盖用户设置的行为已改为仅首次初始化，后续重启保留用户设置

## 轻量检查

```sh
python3 -m unittest discover -s tests -v
```

镜像构建还会验证 Python/AgentKit 导入和离线项目创建，检查成功后移除仅供构建验证的临时项目

## 编辑器和终端默认行为

`VSCODE_LANG` 未设置或为 `zh-CN` 时使用简体中文，为 `en` 时使用英文，编辑器和欢迎页保持一致
火山引擎默认中文，BytePlus 启动时设置 `VSCODE_LANG=en`
中文界面使用官方 `MS-CEINTL.vscode-language-pack-zh-hans` 1.104.0

首次进入只显示 VS Code，欢迎页包含文档链接、VeADK 介绍和 AgentKit 介绍
每个工作区默认创建 Bash 和 Codex 两个集成终端，工作目录均为当前项目
刷新时复用已恢复的同名终端，Codex 使用 `--cd` 显式指定项目目录
配置 `MODEL_AGENT_API_KEY`、`MODEL_AGENT_NAME` 和 `MODEL_AGENT_BASE_URL` 后，基础镜像生成 Codex 模型配置，无需交互登录；凭据只在启动时传入，不写入镜像

Bash 使用上游 ble.sh v0.4.0-devel3 提供输入高亮，采用固定 SHA256 的官方发布包，不切换 Shell

本地 Apple Silicon 在 QEMU 中运行 x64 Codex 0.139.0 时，可能因不支持 TCGETS2 终端接口报 `os error 38`
本地预览容器可通过基础镜像已有的 `CODEX_REAL_BIN` 覆盖为相同版本 Linux ARM64 musl 程序
此替换仅用于本地兼容，不改变云端 x64 镜像的默认程序，也不放宽权限或沙箱限制

## Apple Silicon 本地预览

云端继续使用基础镜像的 `/opt/gem/run.sh` 和原始 x64 Codex
本地 ARM 预览显式选择 `/opt/studio-sandbox/runtime/local-arm64-entrypoint`，它设置已有的 `CODEX_REAL_BIN` 覆盖变量并统一 fnm 命令入口，再执行原始启动脚本
该入口随镜像提供，不是镜像默认入口

建议本地虚拟机至少提供 4 CPU / 12 GB 内存，构建时避免并行运行多个编辑器窗口
本地运行设置 `DISABLE_BROWSER=true`，避免 x64 浏览器在 QEMU 下反复崩溃
运行示例中的模型环境文件应设置为仅当前用户可读

```sh
docker run -d --name studio-sandbox-local --platform linux/amd64 \
  --entrypoint /opt/studio-sandbox/runtime/local-arm64-entrypoint \
  --ulimit core=0 --shm-size=512m \
  --env-file /path/to/model.env \
  -e AIO_USER=gem -e DISABLE_BROWSER=true \
  -e DISABLE_DEEPSEEK_HARNESS_WEBUI=true \
  -e DISABLE_CODEX_APP_SERVER=true -e DISABLE_CODEX_MCP_SERVER=true \
  -p 127.0.0.1:18080:8080 studio-sandbox:local
```

项目的 `.git` 在资源管理器中默认可见
`AGENTS.md` 仅包含 Python 开发规范、项目目录说明和 VeADK / AgentKit 文档链接
项目技能可放在 `.agents/skills/<name>/SKILL.md`，不默认复制个人技能

## 云端默认镜像与资源加载

镜像内置云端会话资源路由：主题、语法文件、语言包、工作台脚本、字体和欢迎页的
Service Worker 使用当前页面的 `Authorization`、`faasInstanceName`，不向外部域名转发
鉴权参数；本地地址不带这些参数时保持原有访问方式
无需在 Tool 的启动命令里再注入编辑器补丁，直接使用 `/opt/gem/run.sh`

终端仅在项目首次打开时自动初始化，后续刷新交给 VS Code 恢复，不因恢复较慢重复创建
手动关闭后不会在刷新时重新打开；需要时通过命令面板执行 `Studio: Open Bash and Codex / 打开终端`
现有用户自行创建的终端不会被删除

文件监听排除 `.venv`、Python 系统依赖、`__pycache__` 和 `node_modules`，减少云端
inotify 配额占用；目录仍可见，项目源码仍被监听，Python 补全仍可读取依赖类型信息

基于已经发布的 Studio 镜像更新编辑器时，可以使用 `Dockerfile.update`，`BASE_IMAGE`
应固定为已验证镜像的 SHA256 digest；全量构建继续使用 `Dockerfile`
更新过程只在构建镜像时执行，不覆盖挂载进来的用户设置和项目文件

```sh
docker build --platform linux/amd64 -f Dockerfile.update \
  --build-arg BASE_IMAGE='<Studio 镜像@sha256:digest>' \
  -t studio-sandbox:updated .
node --test tests/test_terminals.cjs
```

Tool 建议保持已验证的 4 CPU / 8 GB 内存、8080 端口和快照能力，模型环境变量在
创建 Tool 时传入；火山引擎默认中文，BytePlus 设置 `VSCODE_LANG=en`
