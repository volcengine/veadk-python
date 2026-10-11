# 规范化托管 MPA 注册库 TLS 连接地址

[English](2026-09-23-mpa-registry-tls-url.md)

日期：2026-09-23。状态：已在工作区实现。组件：[Studio MPA 创建](../../specs/studio-mpa-creation/README.zh.md)。

## 证据、范围和需求

新 Runtime 的 V2 已达到平台 Ready，但 `/readiness` 返回 503，MPA 元数据引导报 TypeError。使用下发的注册库地址复现镜像中的 SQLAlchemy asyncpg 连接构造，得到 `connect() got an unexpected keyword argument 'sslmode'`。VeADK 自身的数据库适配器会转换此参数，独立版本的 MPA 镜像没有转换。

FR-1：下发 `SHARED_APIG_DATABASE_URL` 时将 `sslmode` 转为 `ssl`，保留参数值、凭据、主机、数据库和其他参数。已兼容的 URL 保持字节级不变。拒绝冲突或重复 TLS 参数，错误不得暴露 URL。
FR-2：初次创建和最终配置均收到兼容地址。进行中任务若记录的哈希仅因本次规范化而不同，可以恢复。丢失创建响应时必须使用原客户端令牌重放原始请求。其他配置变化仍被拒绝。
FR-3：仅修改已授权当前 Runtime 的这一环境变量，然后验证平台就绪、应用就绪和 Studio 任务完成。恢复不分配新的 PG、APIG、Worker 或 Runtime。

## 设计、任务与验收

T-1 / AC-1：添加离线测试，覆盖驱动连接参数、TLS 模式、参数冲突、初次/最终请求及重试；先验证测试失败。
T-2 / AC-2：在 managed `runtime.py` 添加纯 URL 规范化函数，并用于下发环境变量。将进行中哈希兼容检查扩展到这一特定旧表示；Runtime ID 未知时保留精确重放。
T-3 / AC-3：执行托管部署回归、变更文件 Ruff/Pyright、空白检查和密钥扫描。对当前 Runtime 修正单个变量，并观察已有创建任务。

仅影响托管 MPA 部署；通用 Studio 对话、UI、镜像、数据库归属和 APIG 创建不在范围内。同步更新所属组件的双语契约。原部署配置继续供控制面使用；凭据不得进入报告或测试。URL 转换保留所要求的 TLS 模式；数据库代理的内部连接加密不属于此适配器的控制范围。

## 审查、授权与验证

直接设计审查（review-spec 不可用）：已审查兼容性、幂等性、秘密处理和失败边界。用户以“帮忙解决下”授权修复并恢复本次失败创建，无额外设计阻塞。真实恢复可能增加一个 Runtime 发布版本。保留现有注册记录和云资源。

验证记录（2026-09-23，`feat/from-main-20260922`，本次未提交修复）：

- **pass：**新增 12 个回归用例在实现前失败、实现后通过；受影响部署用例共 52 项通过。扩大后的托管创建和部署环境回归共 359 项通过，CLI 用例共 19 项通过。最初 6 项服务测试使用了非 URL 占位值，现已将测试夹具改为有效的虚构 PostgreSQL URL。
- **pass：**`UV_CACHE_DIR=/private/tmp/veadk-uv-cache uv run --extra dev pytest -q tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py`，以及单独的 `tests/cli/test_cli_mpa.py`。CLI 测试允许绑定本地模拟服务端口。
- **pass：**对 `runtime.py`、`test_registry_url.py` 和 `test_service.py` 执行 Ruff 0.11.12 和 Pyright；对相关文件执行 Gitleaks；`git diff --check`；核对双语文档链接及标识符。默认缓存路径不可用后，检查工具使用临时缓存。
- **pass（真实环境）：**仅修正已有 Runtime 的注册库环境变量值。V3 达到 Ready，应用就绪探针成功，已有 Studio 任务变为 `succeeded`，部署注册记录为 `ready` 且 `pending=false`。未分配额外 PG、APIG、Worker 或 Runtime，验证记录未包含秘密值。
- **not_applicable：**前端构建/浏览器视觉检查及 harness 冒烟，因为没有修改前端、对话或 harness 代码。**not_run：**全仓库回归及全文件 pre-commit，本次交付为限定范围的未提交修复；已执行受影响回归及密钥/静态检查。通过生产方规范化兼容旧 Runtime 镜像，无需重建镜像。

T-1–T-3 和 AC-1–AC-3 均已满足。没有提交或推送。
