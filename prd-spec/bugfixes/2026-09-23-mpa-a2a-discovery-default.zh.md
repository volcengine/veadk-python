# MPA A2A 发现默认配置修复

[English](2026-09-23-mpa-a2a-discovery-default.md)

- 变更：mpa-a2a-discovery-default；日期：2026-09-23；状态：implemented。
- 契约：[MPA 部署](../../specs/mpa-runtime-provisioning/README.zh.md)。

## 证据与范围

只读线上对比确认：旧 Runtime 未设置 DISABLE_JWT_AUTH，list-apps 返回 404，A2A agent card 返回 200，Studio 使用 a2a-default。新 Runtime 由 build_runtime_env 注入 DISABLE_JWT_AUTH=true，list-apps 返回 default，进入 REST profile-status 后因无 JWT 公钥返回 500。两者 A2A 发现均正常。镜像不同但本次不切换镜像。

## 需求、设计与验收

- FR-1 / T-1 / AC-1：创建默认值改为 DISABLE_JWT_AUTH=false、ENABLE_A2A=true，保留 A2A_TIP_VERIFY_ENABLED=false 和外层 Runtime key-auth。测试先复现，再验证 CLI 环境与 managed flat 创建 payload。
- FR-2 / T-2 / AC-2：保留显式 extra_env 和 managed.runtime.env 覆盖优先级；引用 Runtime / 模板的环境沿用原有逻辑。通用智能体逻辑不改动；Studio MPA 代理的路径兼容按下方追加设计实施。非目标：启用 MPA_AGENTKIT_MODE、补 JWT、公钥/身份架构迁移、修改数据库。
- FR-3 / T-3 / AC-3：对本次失败的新 Runtime 单独更新上述发现配置；同一个 Runtime 发布新版本，等待 Ready 和应用 readiness，再验证 list-apps 404、agent card 200、Studio a2a-default 与隔离测试会话聊天。不得输出密钥。失败如实报告，不自动回退其他资源。

## 文件、风险与恢复

涉及 mpa_provision.py、test_mpa_provision_env.py、mpa_managed/test_service.py、双语部署规范和模块 README。用户已明确授权沿用旧 A2A 链路并修正模板。现有 Runtime 不会被代码自动迁移；本次仅修复已定位的新 Runtime。发布可能短暂中断该 Runtime；保留其他环境和镜像。未完成创建任务的 payload hash 仍保持严格校验，不绕过配置漂移保护；旧任务若报漂移需用原配置完成或重新创建。显式禁用 JWT 的自定义配置仍由操作者负责。

## 设计审查

review-spec 不可用，已直接审查需求、接口、安全、兼容性、错误处理、测试性和双语一致性。没有阻塞项；用户本轮指令批准上述方案。不改变会话状态、流式事件或取消逻辑，仅选择现有 A2A 协议。外层 key-auth 不变，REST JWT 校验保持有效。

## 验证记录

2026-09-23，当前未提交差异。详细结果见下方实施记录。前端构建：not_applicable（无前端变更）。全仓测试及 pre-commit：not_run（本轮不提交，先执行受影响回归）。

## 追加设计审查：共享公网路径

线上 V4 会话发送暴露第二个原因：共享公网 endpoint 带 /runtime/<ID> 前缀，但 agent card 的 /a2a/jsonrpc 丢失该前缀。FR-4 / T-4 / AC-4：Studio 后端仅对已验证类型为 MPA 的 Runtime，在 agent card 与控制面 endpoint 同源且卡片路径恰为 /a2a/jsonrpc 时，补齐符合 /runtime/[a-z0-9-]+ 的前缀。已带前缀、跨源、非默认 RPC 路径、含查询/片段/用户信息的 URL 不做改写；通用智能体不改。适用于发送、流式回退和历史读取。新增 frontend/server/mpa_a2a.py、修改 cli_frontend.py 并增加单测和现有代理集成矩阵。保留失败及取消行为，无额外重试。直接复审已通过，属于用户批准恢复 A2A 聊天的必要兼容修复。需要重启本地 Studio 加载后端代码；无需前端构建。

## 实施与最终验证记录

2026-09-23，当前分支未提交差异：FR-1 至 FR-4、T-1 至 T-4、AC-1 至 AC-4 已完成。

- `pass`：测试先行，原默认值导致 5 个回归失败；路径修复前新集成矩阵 6 例失败、12 例通过，均为预期复现。
- `pass`：`UV_CACHE_DIR=/private/tmp/veadk-uv-cache uv run --extra dev pytest -q tests/integrations/test_mpa_provision_env.py tests/integrations/mpa_managed tests/integrations/test_mpa_runtime.py`，366 例通过。测试辅助函数类型修正后，环境及 service 两个目标文件重跑 37 例通过。
- `pass`：`uv run --extra dev pytest -q tests/cli/test_cli_mpa.py tests/cli/test_frontend_runtime_proxy.py -k 'a2a or mpa'`，32 例通过；追加路径修复后 `uv run --extra dev pytest -q tests/cli/test_mpa_a2a_url.py tests/cli/test_frontend_runtime_proxy.py --tb=short`，106 例通过，覆盖通用智能体地址不变、流式/非流式/回退和历史恢复。
- `pass`：Ruff check/format 对本次 7 个 Python 文件通过；gitleaks 扫描通过；diff whitespace 通过。
- `pass`：模板、环境测试、service 测试及新增 URL helper/test 的 Pyright 无错误。`fail`：cli_frontend.py 和旧代理测试文件全文件 Pyright 有 56 个存量错误；与 HEAD 副本逐条比较诊断文本及文件后完全相同，没有新增诊断。未为本修复修改无关类型错误。
- `pass`：线上新 Runtime 仅更新 2 个发现变量，发布 V4，平台 Ready、应用 readiness 成功；旧 Runtime 仍 V7 且配置不变。新 Runtime 的 list-apps 返回 404、agent card 返回 200。
- `pass`：重启本地 Studio 后，真实浏览器选中新 Runtime 显示 a2a-default；独立测试会话发送简单算术，收到最终答案 2，推理和底部操作栏正常，无 JWT/404 错误。保留该测试会话；没有创建额外云资源。REST profile-status 仍要求 JWT，不作为 A2A 的验收条件。
- `not_run`：全仓回归、全文件 pre-commit（范围大且包含无关未提交修改，本轮未要求提交）；前端构建/布局场景 `not_applicable`（无 TS/CSS/生成资源变更）。未真实运行沙箱技能、取消及跨进程历史恢复；本次不改变这些协议。
- 工具网络受限导致在线 uvx 拉取 pre-commit 失败，使用既有离线缓存运行相同 gitleaks hook 并通过，未修改全局配置或绕过检查。没有提交或推送。

最终审查补充空用户信息 URL 边界回归：修正保护条件前失败，修正后 15 个 URL 单测全部通过。
