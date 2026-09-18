# 默认关闭数据库自动埋点

用户已授权：从上游 feat/mpa-agent-oneclick-provision 新建分支，在创建 MPA Runtime 时注入数据库埋点配置。不改原生 MPA 代码和已有部署。

共享 build_runtime_env 增加 OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=sqlalchemy,asyncpg,psycopg,psycopg2,dbapi。保留 extra_env 最后覆盖语义，包括空字符串。预览和部署使用同一构建函数，第二阶段环境更新保留该值。不增加依赖，不修改鉴权，业务 tracing 保持启用。

已自审：新增默认值，保留显式覆盖，不包含凭证或线上部署。同步中英文 MPA 部署契约。回归验证默认值及自定义/空值覆盖，运行环境、CLI 和 Runtime 测试，统计增量覆盖率后提交并推送用户仓库。

验证：34 项环境、Runtime、CLI 测试通过；修改的环境构建函数覆盖 17/17 可执行行（100%），新增字典默认值已显式断言。pre-commit（Ruff 检查、格式、密钥扫描）和 Pyright 通过。未修改云资源。
