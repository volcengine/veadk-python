# VeADK 配置项

为支持企业级应用的安全配置管理，VeADK 能够直接读取环境变量中的规定配置项，来实现代码脱敏。

## 优先级

VeADK 读取的环境变量优先级如下（优先级依次递减）：

1. 系统环境变量（已经在系统级别预设的环境变量）
2. `.env` 文件环境变量
3. `config.yaml` 文件中的配置项值

## 环境变量对照表

### 火山引擎生态

统一前缀： `VOLCENGINE_`

| 环境变量名称 | 释义 |
| :- | :- |
| `VOLCENGINE_ACCESS_KEY` | 火山引擎 Access Key |
| `VOLCENGINE_SECRET_KEY` | 火山引擎 Secret Key |

对应 `yaml` 文件格式：

```yaml title="config.yaml"
volcengine:
  access_key:
  secret_key:
```

### 模型类

统一前缀： `MODEL_`

| 子类 | 环境变量名称 | 释义 |
| :- | :- | :- |
| Agent 推理模型 | `MODEL_AGENT_NAME` | 模型名称 |
| | `MODEL_AGENT_PROVIDER` | 符合 LiteLLM 规范的模型提供商 |
| | `MODEL_AGENT_API_BASE` | 访问地址 |
| | `MODEL_AGENT_API_KEY` | 访问密钥 |
| Embedding 模型 | `MODEL_EMBEDDING_NAME` | Embedding 模型名称 |
| | `MODEL_EMBEDDING_DIM` | Embedding 模型维度 |
| | `MODEL_EMBEDDING_API_BASE` | 访问地址 |
| | `MODEL_EMBEDDING_API_KEY` | 访问密钥 |
| 评测模型 | `MODEL_JUDGE_NAME` | 模型名称 |
| | `MODEL_JUDGE_API_BASE` | 访问地址 |
| | `MODEL_JUDGE_API_KEY` | 访问密钥 |

### 内置工具类

统一前缀： `TOOL_`

| 子类         | 环境变量名称           | 释义                    |
|------------| ---------------------- |-----------------------|
| VeSearch   | `TOOL_VESEARCH_ENDPOINT` | 火山引擎搜索机器人 ID（bot_id）  |
|            | `TOOL_VESEARCH_API_KEY`  | 火山引擎搜索服务密钥            |
| WebScraper | `TOOL_WEB_SCRAPER_ENDPOINT` | WebScraper 端点         |
|            | `TOOL_WEB_SCRAPER_API_KEY`  | WebScraper 密钥（token）  |
| Lark       | `TOOL_LARK_ENDPOINT`    | Lark 应用 ID（app_id）    |
|            | `TOOL_LARK_API_KEY`     | Lark 应用密钥（app_secret） |
|            | `TOOL_LARK_TOKEN`       | Lark 用户 token         |
| LAS        | `TOOL_LAS_URL`          | LAS SSE 服务地址（含 token） |
|            | `TOOL_LAS_DATASET_ID`   | LAS 数据集 ID            |
| VOD        | `TOOL_VOD_GROUPS`   | 视频编辑能力组               |
|            | `TOOL_VOD_TIMEOUT`   | VOD工具连接超时时长           |


### 数据库类

统一前缀： `DATABASE_`

| 子类      | 环境变量名称                                | 释义 |
| --------- | ------------------------------------------- | ---- |
| OpenSearch | `DATABASE_OPENSEARCH_HOST`                 | OpenSearch 主机地址（不含 http/https） |
|           | `DATABASE_OPENSEARCH_PORT`                  | OpenSearch 端口，默认 9200 |
|           | `DATABASE_OPENSEARCH_USERNAME`              | OpenSearch 用户名 |
|           | `DATABASE_OPENSEARCH_PASSWORD`              | OpenSearch 密码 |
|           | `DATABASE_OPENSEARCH_CERT_PATH`             | OpenSearch 证书路径。**生产环境下建议通过证书访问。** |
|           | `DATABASE_OPENSEARCH_USE_SSL`               | 是否启用 SSL 验证（`https`），默认 True |
| MySQL     | `DATABASE_MYSQL_HOST`                       | MySQL 主机地址 |
|           | `DATABASE_MYSQL_USER`                       | MySQL 用户名 |
|           | `DATABASE_MYSQL_PASSWORD`                   | MySQL 密码 |
|           | `DATABASE_MYSQL_DATABASE`                   | MySQL 数据库名称 |
|           | `DATABASE_MYSQL_CHARSET`                    | MySQL 字符集，默认 utf8 |
| Redis     | `DATABASE_REDIS_HOST`                       | Redis 主机地址 |
|           | `DATABASE_REDIS_PORT`                       | Redis 端口，默认 6379 |
|           | `DATABASE_REDIS_PASSWORD`                   | Redis 密码 |
|           | `DATABASE_REDIS_DB`                         | Redis 数据库编号，默认 0 |
| VikingDB  | `DATABASE_VIKING_PROJECT`                   | Viking DB 项目名称 |
|           | `DATABASE_VIKING_REGION`                    | Viking DB 区域 |
| TOS       | `DATABASE_TOS_ENDPOINT`                     | TOS 访问端点 |
|           | `DATABASE_TOS_REGION`                       | TOS 区域 |
|           | `DATABASE_TOS_BUCKET`                       | TOS 桶名称 |

### 可观测

统一前缀： `OBSERVABILITY_`

| 子类       | 环境变量名称                                        | 释义 |
| ---------- | --------------------------------------------------- | ---- |
| APMPlus    | `OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT`      | APMPlus 上报地址 |
|            | `OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY`       | APMPlus 鉴权密钥 |
|            | `OBSERVABILITY_OPENTELEMETRY_APMPLUS_SERVICE_NAME`  | APMPlus 服务名称 |
| CozeLoop   | `OBSERVABILITY_OPENTELEMETRY_COZELOOP_ENDPOINT`     | CozeLoop 上报地址 |
|            | `OBSERVABILITY_OPENTELEMETRY_COZELOOP_API_KEY`      | CozeLoop 鉴权密钥 |
|            | `OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME` | CozeLoop 服务空间 ID（space_id） |
| TLS        | `OBSERVABILITY_OPENTELEMETRY_TLS_ENDPOINT`          | TLS 上报地址 |
|            | `OBSERVABILITY_OPENTELEMETRY_TLS_SERVICE_NAME`      | TLS topic_id |
|            | `OBSERVABILITY_OPENTELEMETRY_TLS_REGION`            | TLS 区域 |
| Prometheus | `OBSERVABILITY_PROMETHEUS_PUSHGATEWAY_URL`          | Prometheus Pushgateway 地址 |
|            | `OBSERVABILITY_PROMETHEUS_USERNAME`                 | Prometheus 用户名 |
|            | `OBSERVABILITY_PROMETHEUS_PASSWORD`                 | Prometheus 密码 |

### Prompt Pilot

| 环境变量名称 | 释义 |
| :- | :- |
| `PROMPT_PILOT_API_KEY` | Prompt Pilot 产品密钥 |

### Agent Identity 身份认证

统一前缀： `VEIDENTITY_`

| 环境变量名称 | 释义 |
| :- | :- |
| `VEIDENTITY_REGION` | Agent Identity 服务区域，默认 cn-beijing |
| `VEIDENTITY_ENDPOINT` | Agent Identity 服务端点（可选，不提供时自动生成） |

对应 `yaml` 文件格式：

```yaml title="config.yaml"
veidentity:
  region: cn-beijing
  endpoint:  # 可选，不提供时自动生成
```

## 内置常量

在 VeADK 中，某些值如果没有显示指定，且环境变量中也不存在时，如下值将会取默认值：

| 名称 | 值 | 释义 |
|------|----|------|
| DEFAULT_AGENT_NAME | `veAgent` | Agent 的缺省名称 |
| DEFAULT_MODEL_AGENT_NAME | `doubao-seed-1-6-250615` | Agent 的推理模型名称 |
| DEFAULT_MODEL_AGENT_PROVIDER | `openai` | Agent 的推理模型提供商 |
| DEFAULT_MODEL_AGENT_API_BASE | `https://ark.cn-beijing.volces.com/api/v1/` | 模型 API 基础地址 |
| DEFAULT_APMPLUS_OTEL_EXPORTER_ENDPOINT | `http://apmplus-cn-beijing.volces.com:4317` | APMPlus OpenTelemetry Trace 导出地址 |
| DEFAULT_APMPLUS_OTEL_EXPORTER_SERVICE_NAME | `veadk_tracing` | APMPlus 服务名 |
| DEFAULT_COZELOOP_OTEL_EXPORTER_ENDPOINT | `https://api.coze.cn/v1/loop/opentelemetry/v1/traces` | CozeLoop OTEL Trace 上报地址 |
| DEFAULT_TLS_OTEL_EXPORTER_ENDPOINT | `https://tls-cn-beijing.volces.com:4318/v1/traces` | TLS Trace 上报地址 |
| DEFAULT_TLS_OTEL_EXPORTER_REGION | `cn-beijing` | TLS 区域 |
| DEFAULT_CR_INSTANCE_NAME | `veadk-user-instance` | 容器镜像仓库实例名 |
| DEFAULT_CR_NAMESPACE_NAME | `veadk-user-namespace` | 容器镜像仓库命名空间 |
| DEFAULT_CR_REPO_NAME | `veadk-user-repo` | 容器镜像仓库名称 |
| DEFAULT_TLS_LOG_PROJECT_NAME | `veadk-logs` | TLS 日志项目名称 |
| DEFAULT_TLS_TRACING_INSTANCE_NAME | `veadk-tracing` | TLS Tracing 实例名称 |
| DEFAULT_TOS_BUCKET_NAME | `veadk-default-bucket` | 默认 TOS 存储桶名称 |
| DEFAULT_COZELOOP_SPACE_NAME | `VeADK Space` | CozeLoop 空间名称 |
