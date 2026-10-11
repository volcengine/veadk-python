# 将 Studio 多 Bot 支持迁入上游基础分支

[English](2026-10-10-port-multi-bot.md)

- 变更 ID：mpa-multi-bot-port；创建/修订：2026-10-10；状态：implemented。
- 来源：`feat/from-main-20261009` 的 `49dd4696`；目标基线：`feat/mpa-account-fixes-upstream-clean-20261010` 的 `f7576c40`。
- 设计：[原功能](2026-10-09-studio-multi-bot.zh.md)。契约：[渠道](../../../specs/mpa-channels/README.zh.md)、[任务](../../../specs/studio-mpa-cron-tasks/README.zh.md)。

## 背景、目标和范围

来源实现了按能力开启的飞书账号管理和定时任务投递，目标缺少新容器及能力字段。补丁预检查允许源码/测试/规格改动，frontend README 须结合上下文合并。用户要求迁入该功能。保留当前账号 Key 功能与无关 package-lock 修改。不合并无关分支历史，不改 Runtime 镜像、后端存储/鉴权，不操作真实 Bot。原分支验证不是当前分支证据。

## 需求和设计

- FR-1：迁入原 FR-1–FR-6 语义及回归用例：按能力显示多个账号、诊断/群权限携带选定 appId、追加绑定、独立启停/解绑、明确任务投递账号、取消及迟到响应处理。
- FR-2：保留旧单 Bot Runtime、企微/钉钉和通用智能体聊天。缺少 multiBotChannels 沿用旧 UI；任务能力接口不支持（404）时保留旧任务行为。鉴权/网络失败仍显示错误，不通过空/异常响应推断兼容能力。
- FR-3：仅应用该功能源码/测试/契约/文档。基于目标源码重建打包产物，不复制旧压缩包。原有本地修改逐字节保留。无需依赖/锁文件改动；除原有能力控制的扩展外，不新增公开 Python 或服务端 API 契约。

复用既有 RuntimeChannels 布局、渠道 Tab、Select、Radio、Button、任务 DialogShell 和 text-shimmer。不新增产品图标或组件设计，使用公开组件属性。frontend-design/ui-ux-pro-max 技能文件缺失，直接执行 foundation/S1–S8 与 UI 审查，保持既有组件行为。Bot 存储/路由仍由 MPA 负责，Studio 负责账号选择与代理请求。

## 任务和验收

| 需求 | 任务 | 验收 |
| --- | --- | --- |
| FR-1 | T-1 | AC-1：先迁测试并记录失败，再迁源码，验证渠道/任务用例 |
| FR-2 | T-2 | AC-2：执行旧流程回归与浏览器夹具，覆盖正常/加载/空/错误/重试/取消/键盘/窄窗口 |
| FR-3 | T-3 | AC-3：重建产物，验证引用/国际化/类型/安全，同步双语 README/规格/设计并比较原有文件哈希 |

命令：定向 Vitest（jsdom）；npm --prefix frontend test；npm --prefix frontend run test:mpa-cron-coverage；npm --prefix frontend run build；npm --prefix frontend run check:i18n；npm --prefix frontend run test:webui-assets；本地 tsc --noEmit；uv run --extra dev pytest tests/test_mpa_channel_proxy_policy.py tests/frontend/server/test_mpa_cron.py。本次迁入无 Python 生产改动，无新增 Ruff/Pyright 检查对象；先前 Key 功能的检查保持独立。

## 风险和审查

多 Bot 需要另行部署兼容 Runtime。非管理员可能无法列出投递 Bot，须显示权限错误。模拟浏览器夹具不能证明真实飞书/Gateway 投递。原生确认/IME 限制须记录。不执行资源清理/迁移。

review-spec 不可用，直接审查源码/目标边界、原有修改保留、能力、鉴权/错误、取消、测试及双语等价，无阻塞。用户在限定迁入计划后批准：“把那个修改挪过来吧”。未授权提交/推送/部署。已读设计/规格规则及前端 foundation/SPEC；引用的 UI 技能在仓库和已安装路径不存在，沿用既有组件行为。

## 验证记录

范围：相对 `f7576c4080da6230e263eac20ab5d32644405ed5` 的源码/测试/文档及重建 WebUI 差异；执行日期：2026-10-10。T-1–T-3、AC-1–AC-3 已完成，真实验证限制如下。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 定向 Vitest，测试先行 | fail，预期失败 | 迁源码前 27 个新增用例失败，账号辅助模块缺失；123 个既有用例通过 |
| 定向 Vitest（jsdom） | pass | 6 个文件、162 个测试：渠道、账号响应校验、任务机器人、管理、定时任务及渠道 API |
| `npm --prefix frontend test` | pass | 1,377 个 Node 测试及 65 个智能体信息/创建/详情 Vitest 测试 |
| `npm --prefix frontend run test:mpa-cron-coverage` | pass | 87 个测试；语句 99.31%、分支 97.44%、函数 99.18%、行 99.74%，满足配置门槛 |
| `frontend/node_modules/.bin/tsc --noEmit`（frontend 工作目录） | pass | 当前 TypeScript 源码编译通过 |
| `npm --prefix frontend run check:i18n` | pass | 两种语言、21 个命名空间一致 |
| `npm --prefix frontend run build` | pass | 基于目标源码重建 Studio 及网站集成，保留既有大包警告 |
| `npm --prefix frontend run test:webui-assets` | pass | 113 个打包文件、350 个内部引用 |
| 上述定向 Python 命令 | pass | 18 个代理策略/定时任务测试 |
| 隔离真实浏览器检查 | pass | 模拟 API、真实组件：账号选择、独立启停 B、按账号诊断/群权限请求、手动追加 C 且保留 A/B、任务 B 的投递/线程元数据保留、Web 清除 appId、旧单 Bot 页面、钉钉原界面、空/错误/重试/加载、重挂载取消请求、取消添加和键盘选择；390px 窗口及任务编辑均无横向溢出 |
| 原生解绑确认 / 真实 IME | blocked | 应用内浏览器确认框阻塞 CDP 输入，已关闭受影响测试标签；解绑/取消/迟到请求及输入法保护由组件回归覆盖，未声称实际 IME 验证 |
| Gitleaks 限定目录扫描（`--redact=100`） | pass | 24 个迁入源码/测试/文档文件，无发现 |
| 原有修改保留和文档审查 | pass | 原有 20 个未提交文件 SHA-256 完全一致，含账号 Key 功能及 package-lock；已检查双语文档、相对链接和空白 |
| Ruff/Pyright 及 harness-sidecar 覆盖率 | not_applicable | 未改 Python 生产代码或 sidecar 契约 |
| 真实 Runtime/飞书/Gateway 写入 | not_run | 兼容 Runtime 部署和真实投递不在本次 Studio 迁入范围 |
| 提交前 fetch/rebase 及全量 pre-commit | not_run | 未要求提交 |

实现审查：按能力控制的职责和旧版本兼容符合契约；机器人诊断/群权限/解绑及任务投递保持账号范围；读取失败不会变成成功空列表或任意机器人选择，取消及防重复请求处理保留。未改通用聊天、MPA 创建、默认镜像、IAM 或模型 Key 发现生产代码。已删除临时夹具、停止服务并清除浏览器窗口尺寸覆盖；来源设计的历史证据单独保留。

文档检查说明：完整 frontend README 链接检查发现 HEAD 已有的 `.agents` 本地示例链接不可用；迁入链接全部通过，未改这个无关链接。

## 提交准备（2026-10-10）

用户授权：“把当前的修改都提交吧”。仅提交，不推送或部署。已 fetch origin/upstream，再执行 `git rebase --autostash upstream/main`：上游基础分支已同步，自动暂存成功恢复。172 个修改/删除/未跟踪文件状态与同步前哈希一致，检查期间未改生产或测试文件。按用户授权包含已有 package-lock 改动；`npm ci --prefix frontend --dry-run --ignore-scripts --offline` 通过，未修改锁文件。

- pass — `uv run --extra dev pre-commit run --all-files`：Ruff 检查/格式化、硬编码凭据扫描及 YAML 密钥扫描。
- pass — 已改 Python 生产/测试文件执行 `uv tool run --from pyright pyright --pythonpath .venv/bin/python`：零错误/警告。
- pass — 同步后重跑前端完整测试：1,377 个 Node 测试及 65 个 Vitest 测试；重跑多 Bot/渠道/任务回归：162 个通过。同步及检查未改变源码/产物，此前构建、国际化、覆盖率、产物及隔离浏览器证据仍有效。
- fail，基线已有问题 — `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`：6,933 个通过、53 个跳过、四个 xfailed、一个失败、55 个警告，耗时 412.63 秒。唯一失败为 `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`：期望 `text/markdown`，实际 `application/octet-stream`。写入实现及测试与 HEAD 逐字节一致，使用仓库 Python 环境运行隔离 `git archive HEAD` 基线可复现；本机 `mimetypes.guess_type("summary.md")` 返回 `(None, None)`。当前 writer 单独测试也复现，另 48 个用例通过。本提交未加入无关 MIME 实现/测试变更，不将全仓检查表述为通过；该结果未发现提交功能范围的回归。
- pass — 暂存差异空白检查及密钥钩子；本地 `.env` 保持忽略，未包含到提交。真实方舟/飞书/云验证及浏览器原生确认/IME 限制保持前述记录，跳过的测试不证明真实行为。
