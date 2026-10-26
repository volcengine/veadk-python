# Studio 直接填写协作 Agent 密钥

[English](2026-10-20-direct-credentials.md)

变更：collaborator-direct-credentials | 2026-10-20 | 本地已实现并验证，尚未发布。
替代原协作 Agent 方案中“仅环境变量引用”的决策，其他边界保持。

## 需求与设计
- FR-1：名称、URL、密钥框使用用途说明的边框颜色，仅作用于此表单。复用 InputWithTailIcon、Textarea、Select、Checkbox、Button，不修改全局主题。
- FR-2：直接输入 Bearer/API Key。默认隐藏，可主动显示/隐藏新输入值；保存成功、取消、刷新、切换鉴权或目标时清空。编辑时留空，仅当鉴权方式、请求头、目标 origin 不变时保留已有密钥。更换 origin 必须重新填写，防止旧密钥发送到不同服务。无鉴权清除凭据。
- FR-3：新增只写 `secret`（SecretStr，最多8192字符，无控制字符）；响应仅新增 `credential_configured`。兼容旧 `secret_env` 记录与调用，新表单不要求配置环境变量。明文、密文均不回显，校验错误不能携带原始输入。
- FR-4：Fernet 加密密钥值及其 MPA/注册记录归属，存入现有配置 JSON。在现有 `mpa_deployment_settings` 事务锁下自动生成持久 `collaborator_credential_key`。不新增依赖、迁移或环境变量。有密文但密钥丢失时失败，不自动轮换。包装密钥与数据同库，数据库管理员及备份仍属于可信边界；两个表应共同备份。
- FR-5：启用表示允许派发；停用保留配置。连接验证独立，实际任务派发不在本次范围。

## 任务与验收
T-1/AC-1：直接创建/验证/解析、重启持久化、编辑保留/替换/清除、旧记录兼容、版本及 MPA 隔离、密钥丢失/损坏、响应及校验脱敏回归。
T-2/AC-2：前端隐藏/切换/重置、写入请求、留空编辑测试；浏览器检查明暗主题、窄布局与输入框边框。
T-3/AC-3：MPA make lint/test、Studio 前端 npm test/build、代理测试及资源检查，如实记录，不代表云端验收。

## 评审与交付
用户明确要求直接输入和统一输入框外观。手工评审：仓库及技能目录中没有 review-spec/前端设计技能文件，依照 SPEC 与已有组件实现。已考虑 origin 变更凭据转发、明文泄漏、并发与密钥丢失恢复，不扩展派发或云资源操作。验证结果见下文。

## 验证记录（2026-10-20）

| 需求 | 证据 | 结果 |
| --- | --- | --- |
| FR-1/FR-2 | 浏览器浅色/深色、360px 表单、隐藏/显示、创建、验证、重开、留空保存和再次验证；真实本地 Runtime 数据库/API，远端 Card 为模拟 | pass |
| FR-2/FR-3 | 前端 1,389 项 Node + 129 项 React 测试，TypeScript、翻译和生产构建资源检查 | pass |
| FR-3/FR-4 | Runtime 凭据/注册测试含隔离 PostgreSQL 16：45 passed；可执行行399/415（96.14%），含分支95% | pass |
| FR-3/FR-5 | Studio 代理/鉴权回归127 passed，代理及 Runtime 新模块 Ruff/Pyright | pass |

Runtime make lint 已通过；Python 3.12.13 / Codex 0.155.1 全量 make test：9,343 passed / 251 skipped / 0 failed，645.31秒。跳过项不视为通过，凭据专项另在 PostgreSQL 验证。已清理浏览器夹具与临时 PostgreSQL。未执行真实外部 Agent 验证、云端部署、正式 CI 或本次镜像发布。Studio 默认 Python 缺少 Ruff/Pyright，使用 MPA 已安装工具并指定 Studio Python 完成导入解析。
