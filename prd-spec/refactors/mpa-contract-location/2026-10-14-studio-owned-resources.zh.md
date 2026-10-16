# 将 MPA 兼容性资源迁入 Studio 目录

[English](2026-10-14-studio-owned-resources.md)

- Change ID：`mpa-contract-location`；日期：2026-10-14；状态：implemented。
- 契约：[Studio MPA 控制面](../../../specs/studio-mpa-control-plane/README.zh.md)。

## 证据、需求与非目标

根目录 `contracts/mpa-p0` 仅有 `compatibility-matrix.json` 和 `benchmark-report.schema.json`。Studio 与 CLI 共用 `veadk.cli.mpa_p0_contract` 评估器；默认加载器优先读取根目录文件，不存在时使用完全一致的内置规则。集成测试和文档 `--matrix` 示例直接引用根文件。未发现性能报告 schema 的运行时调用方。Studio 发布暂存会复制 frontend Python 树，但 setuptools 目前未声明新路径 JSON 的 package-data。已有无关 `frontend/package-lock.json` 改动须保持字节一致。

FR-1：将两个 JSON 原样移至 `frontend/server/mpa/contracts/mpa-p0/`，移除空根目录。不改变规则/schema 内容、检查结果、MPA/通用智能体或 OpenViking 行为。
FR-2：更新 `default_matrix_path()`、集成测试及文档命令。保留公开函数签名、必填自定义 `--matrix` 参数和内置备用规则。包内文件缺失时仍使用内置规则，存在但格式错误时仍明确失败。明确指定旧根路径的调用方需改用新路径。
FR-3：Python wheel 及 Studio 源码暂存必须包含两个 JSON；通过相邻文件系统路径读取，不导入较重的 frontend 组合包。验证源码环境与隔离解包 wheel 读取相同规则。

非目标：迁移评估器职责、更改 SDK/版本规则、移除兼容性检查、删除 OpenSpec/PRD/spec 目录、更改 UI 或云资源。未请求提交、推送或部署。

## 设计、文件与任务

保留 `mpa-p0` 层级。从已安装评估器源码根定位 frontend/server/mpa；在 pyproject.toml 的 `frontend.server` package-data 中加入精确资源 glob。Studio copytree 暂存已覆盖该目录，无需改生产实现。同步双语当前设计/验证示例，在维护中的控制面契约追加迁移说明。

T-1 / AC-1：先写默认路径/源码加载失败回归，覆盖正常兼容、无效 manifest 和写入前拒绝。逐字节移动资源并更新路径。
T-2 / AC-2：验证缺文件备用规则及存在但格式错误时失败；更新 CLI 示例/测试，不改显式自定义文件语义。
T-3 / AC-3：增加两个资源真实源码暂存断言；构建本地 wheel，检查/解包验证 JSON 和默认加载路径，不发布。
T-4 / AC-4：定向兼容性/CLI/发布检查、改动 Python Ruff/Pyright、双语文档/链接、空白及密钥检查。记录实际证据，保留无关本地改动。

## 审查、风险与授权

review-spec 不可用，直接审查确认需求、职责、调用方路径、文件系统/wheel、错误语义、不新增 import 边界和双语一致。用户于 2026-10-14 对完整目录迁移明确回复“按此方案迁移（推荐）”。文件位置变化属于预期，自定义 CLI 参数语义不变。不改变运行时并发、权限、凭据或云接口。两种语言及维护契约同步更新。主要风险为漏打包，以 wheel 解包验收。已授权实现/测试，设计批准不包含提交/推送/部署。

## 验证记录

执行范围从 `2ffe6e14` 加本次差异开始，结果记录如下。真实云/浏览器/sidecar smoke 为 not_applicable，仅改变内部静态资源位置。不计划 TypeScript/界面变更，前端重建及浏览器交互不适用。

### 已完成验证 — 2026-10-14

范围：`2ffe6e14` 加本地迁移。T-1–T-4 / AC-1–AC-4 完成。移动文件/改加载器前先写回归得到 6 failed / 4 passed。实现后：

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| 定向兼容性测试 | pass | 10 项，含新位置、两个源码暂存 JSON、缺文件备用及格式错误明确失败。 |
| 相关兼容性、Studio RBAC/GitHub、发布及启动回归 | pass | 两个 worker 共 376 项；云/平台调用使用模拟。仍覆盖写入前兼容性拒绝及通用智能体路径。 |
| 改动 Python Ruff/格式/Pyright | pass | 仓库 Ruff 0.11.12；Pyright 使用仓库 Python，0 错误/警告。临时 uvx 工具，未改全局配置。 |
| 普通 wheel 与实际 Studio 暂存 wheel | pass | 均本地构建。隔离解包找到新路径下两个 JSON，与 HEAD 原文件逐字节相同；默认加载器读取包内矩阵，原基线返回兼容。真实 stage_studio_wheel_source 排除 node_modules/src 并包含资源。未上传或全局安装。 |
| 审查 / 文档 / 密钥 / 空白 | pass | 审查双语标识符/命令/相对链接；按仓库 Gitleaks 规则扫描本次变更范围；git diff 空白。未增加凭据。 |
| 已有本地修改 | pass | 无关 frontend/package-lock.json SHA-256 未变。 |
| 全仓回归 / 前端浏览器 / 真实云 / sidecar smoke | not_run / not_applicable | 定向回归覆盖所有已知路径调用方；未改其他共享逻辑、TypeScript、UI、云或 harness 协议，未执行真实云操作。 |
| 提交 / 推送 / 部署 | not_run | 本次迁移未请求或授权。 |

最终审查没有发现额外行为、import、职责或打包变化。明确指定旧根 CLI 路径须按批准方案改用新路径；自定义矩阵参数与内置备用保持兼容。实际命令（MPA_STAGE_ROOT 为真实 Studio 暂存返回的临时源码目录）：

```bash
uv run --extra dev pytest tests/integrations/test_mpa_compatibility_manifest.py -q
uv run --extra dev pytest -n 2 -q tests/integrations/test_mpa_compatibility_manifest.py tests/cli/test_studio_rbac.py tests/cli/test_github_cicd.py tests/cli/test_studio_release.py tests/test_studio_release_server.py tests/cli/test_studio_startup_imports.py
uvx --from ruff==0.11.12 ruff check veadk/cli/mpa_p0_contract.py tests/integrations/test_mpa_compatibility_manifest.py
uvx --from ruff==0.11.12 ruff format --check veadk/cli/mpa_p0_contract.py tests/integrations/test_mpa_compatibility_manifest.py
uvx pyright --pythonpath .venv/bin/python veadk/cli/mpa_p0_contract.py tests/integrations/test_mpa_compatibility_manifest.py
uv build --wheel --out-dir /tmp/veadk-mpa-contract-wheel-20261014
uv build "$MPA_STAGE_ROOT" --wheel --out-dir /tmp/veadk-mpa-contract-release-wheel-20261014
git diff --check
```
