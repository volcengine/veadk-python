# BytePlus Runtime 标签 Endpoint 修复

- Change ID：`studio-byteplus-tag-endpoint`
- 状态：`implemented`
- 创建日期：2026-10-15
- 修订日期：2026-10-15
- English：[2026-10-15-byteplus-tag-endpoint.md](2026-10-15-byteplus-tag-endpoint.md)
- 组件：[Studio MPA 控制面](../../../specs/studio-mpa-control-plane/README.zh.md)

## 背景与证据

通过源码部署到 BytePlus `ap-southeast-1` 的 Studio 在调用
`GET /web/runtimes` 时返回 HTTP 502。内层 Tag `GetResources` 响应为
HTTP 400 `InvalidEndpoint`。Runtime SDK 客户端已经选择 BytePlus host，
但生成的 Tag SDK 客户端将 `Configuration.host` 留空，导致 SDK 在该地域
回退到火山引擎 endpoint。

同一个只读 `GetResources` 请求显式发送到 `open.byteplusapi.com` 时成功，
证明请求结构、凭据和 IAM 权限均有效。

## 目标与非目标

### 目标

- 将 BytePlus Runtime 标签读取发送到 `open.byteplusapi.com`。
- 保持现有火山引擎 endpoint 行为。
- 增加回归测试，检查 Runtime 列表路由实际使用的生成 SDK 配置。
- 保持既有 Tag 错误失败关闭行为。

### 非目标

- 修改 Runtime 列表 schema、过滤、授权或分页。
- 增加由浏览器控制的 endpoint 输入。
- 修改或重建云端 Runtime 资源。
- 修改前端 UI 行为。

## 场景与需求

- `FR-1`：对于 BytePlus Studio 部署，当 `/web/runtimes` 执行标签过滤查询时，
  Tag SDK host 必须为 `https://open.byteplusapi.com`。
- `FR-2`：对于火山引擎 Studio 部署，既有生成 SDK endpoint 解析行为必须保持不变。
- `FR-3`：Tag 失败必须继续表现为明确错误，不能转换为空 Runtime 列表。

## 设计与契约影响

新增 provider 专属 Tag OpenAPI host helper。在构造 `TAGApi` 前，为每个 Runtime
标签读取客户端配置 BytePlus host；火山引擎配置继续保持 host 为空，沿用当前 SDK
解析行为。

公开 HTTP 契约不变。维护契约 `CON-15`/`CON-31` 增补 provider 正确的 Tag
endpoint 要求。不引入状态、持久化、并发、凭据、权限或前端类型变化。凭据继续仅在
服务端使用，浏览器不能选择 endpoint。

## 影响文件与任务

- `T-1`（`FR-1`、`FR-2`）：增加先失败的 BytePlus Runtime 列表 Tag host 测试。
- `T-2`（`FR-1`、`FR-2`）：增加 provider 专属 Tag host 选择并应用到 Runtime
  标签读取。
- `T-3`（`FR-3`）：更新双语组件契约。
- `T-4`：运行定向 Python 测试、Ruff、Pyright、前端测试/构建，并在重新部署后
  执行隔离的 BytePlus 真实读取。

## 验证与验收

| 需求 | 任务 | 验收标准 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`、`T-2` | `AC-1`：BytePlus Tag SDK 收到 `https://open.byteplusapi.com` | 定向 pytest | `pass`：BytePlus host 回归通过 |
| `FR-2` | `T-1`、`T-2` | `AC-2`：火山引擎行为不变 | 定向 pytest | `pass`：既有 Runtime Tag 测试通过 |
| `FR-3` | `T-3` | `AC-3`：既有失败关闭行为继续被覆盖 | 定向 pytest | `pass`：Runtime proxy 测试通过 |
| `FR-1` | `T-4` | `AC-4`：重新部署后的 BytePlus `/web/runtimes` 不再因 `InvalidEndpoint` 失败 | 真实浏览器/API 检查 | `blocked`：VeFaaS 新 revision Pod 就绪超时，流量切换前发布失败 |

要求执行：

```bash
uv run --extra dev pytest tests/cli/test_frontend_runtime_proxy.py
uv run --extra dev ruff check veadk/utils/cloud_provider.py veadk/cli/cli_frontend.py tests/cli/test_frontend_runtime_proxy.py
uv run --extra dev pyright veadk/utils/cloud_provider.py veadk/cli/cli_frontend.py
npm --prefix frontend test
npm --prefix frontend run build
git diff --check
```

## 风险与恢复

错误 host 会导致 Runtime 发现继续不可用。定向配置断言和真实读取覆盖该风险。回滚时
移除 BytePlus host 赋值即可，不需要数据迁移或云资源清理。

## 评审与交付记录

2026-10-15 评审确认故障来自 endpoint 选择，而非凭据、IAM、Runtime 状态或请求
结构。设计保持火山引擎行为和失败关闭错误。用户已在对话中批准实现。交付与验证证据
如下：

- `pass`：`tests/cli/test_frontend_runtime_proxy.py`，120 项。
- `pass`：三个已改 Python 文件的定向 Ruff。
- `pass`：`npm --prefix frontend test`，1389 项 Node 测试和 116 项 Vitest。
- `pass`：`npm --prefix frontend run build`。
- `pass`：双语文档配对和 `git diff --check`。
- `blocked`：Pyright 在 `cli_frontend.py` 中报告 37 个既有错误；没有错误指向新增
  Tag host 行。
- `blocked`：BytePlus 真实更新创建了 Application revision 2 和 Function
  revision 3，但 VeFaaS 以 `internal_system_error` /
  `check new revision's pod ready timeout` 终止发布。稳定流量仍停留在上一 revision，
  因此 `/web/runtimes` 验收未能覆盖本次修复。


### Rebase 后验证（2026-10-15）

范围：远端分支版本 `65cb4f50` 上的 Tag endpoint 改动。

- `pass`：无冲突 rebase 到 `origin/feat/mpa-lifecycle-upstream-20261013`。
- `pass`：`uv run --extra dev pre-commit run --all-files`，包括 Ruff、
  密钥扫描、依赖策略和 YAML 扫描。
- `fail`：`uv run --extra dev pytest -q tests/cli/test_frontend_runtime_proxy.py tests/integrations/mpa_managed -n 2`：
  1268 项通过，3 项失败。本次范围内回归使用两个 worker。
  三项均为既有 `test_creation_images.py` 中断言 `tosBucket` 不存在的测试；
  远端恢复逻辑现已保留该字段。在干净的 `65cb4f50` 上运行这三项可复现同样失败。
  本次 Tag 修复不修改这些创建契约或测试。
- `blocked`：三个改动 Python 文件的 Pyright 检查报告 57 条错误。
  `65cb4f50` 基线文件的诊断消息与数量完全相同，本次改动没有新增诊断。
- `not_run`：本次仅后端提交，没有重复前端构建、浏览器检查或云端部署；
  之前真实部署验证的限制仍然存在。
