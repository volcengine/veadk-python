# 安装

本章主要介绍 VeADK 的安装方法和基本配置项。

## 环境

### PyPI

您可以直接使用`pip`从 [PyPI 平台](https://pypi.org/project/veadk-python/)进行安装：

```bash
pip install veadk-python
```

### 从源码构建

本项目使用`uv`进行构建（[安装`uv`](https://docs.astral.sh/uv/getting-started/installation/)）。

```bash
# clone repo first
git clone https://github.com/volcengine/veadk-python.git

cd veadk-python

uv venv --python 3.10
# Activate
# macOS/Linux: source .venv/bin/activate
# Windows CMD: .venv\Scripts\activate.bat
# Windows PowerShell: .venv\Scripts\Activate.ps1

# only install necessary requirements
uv sync

# or, install extra requirements
# uv sync --extra database
# uv sync --extra eval
# uv sync --extra cli

# or, directly install all requirements
# uv sync --all-extras

# install veadk-python with editable mode
uv pip install -e .
```

## 配置

VeADK 在仓库中提供了一个示例配置文件`config.yaml.example`，其中标明了一个智能体运行的必需（required）配置和可选（optional）配置。您可以基于该示例文件，在项目根目录下创建实际使用的配置文件`config.yaml`。VeADK 中的配置模块将自动查找并加载该文件内容，并将其中的配置项映射为运行时环境变量，从而帮助您省去环境配置的时间。

完整的配置项可以参考[`config.yaml.example`文件](https://github.com/volcengine/veadk-python/blob/main/config.yaml.example)。

### 说明

下面是详细的配置说明：

```yaml
model:
  # [required] for running agent
  agent:
    provider: openai  # 如果使用的是方舟大模型，请在这里填入openai
    name: doubao-1-5-pro-256k-250115
    api_base: https://ark.cn-beijing.volces.com/api/v3/
    api_key:
  # [optional] for llm-as-a-judge a evaluation
  judge:  
    name: doubao-1-5-pro-256k-250115
    api_base: https://ark.cn-beijing.volces.com/api/v3/
    api_key: 
  # [optional] for knowledgebase
  embedding:
    name: doubao-embedding-text-240715
    dim: 2560
    api_base: https://ark.cn-beijing.volces.com/api/v3/embeddings
    api_key:

volcengine:
  # [optional] for Viking DB and `web_search` tool in VolcEngine (https://console.volcengine.com/iam/keymanage/)
  access_key:
  secret_key:

tool:
  # [optional] https://console.volcengine.com/ask-echo/my-agent
  vesearch: 
    endpoint:   # `bot_id`
    api_key: 
  # [optional] https://www.volcengine.com/docs/84296/1494115
  web_scraper: 
    endpoint: 
    api_key:    # `token`
  # [optional] https://open.larkoffice.com/app
  lark: 
    endpoint:   # `app_id`
    api_key:    # `app_secret`
    token:      # `user_token`
  # [optional] for Volcengine Lake AI Service (https://www.volcengine.com/product/las)
  las:
    url:        # mcp sse url
    dataset_id: # dataset name

observability:
  # [optional] for exporting tracing data to Volcengine CozeLoop and APMPlus platform
  opentelemetry:
    apmplus:
      endpoint: http://apmplus-cn-beijing.volces.com:4317
      api_key: 
      service_name: 
    cozeloop:
      endpoint: https://api.coze.cn/v1/loop/opentelemetry/v1/traces
      api_key: 
      service_name: # Coze loop `space_id`
    tls:
      endpoint: https://tls-cn-beijing.volces.com:4318/v1/traces
      service_name: # TLS `topic_id`
      region: cn-beijing
  # [optional] for exporting evaluation data to Volcengine VMP (https://console.volcengine.com/prometheus)
  prometheus:
    pushgateway_url: 
    username: 
    password: 


database:
  # [optional]
  opensearch:
    host:       # should without `http://` or `https://` 
    port: 9200  # default OpenSearch port
    username: 
    password: 
  # [optional]
  mysql:
    host: 
    user: 
    password: 
    database: 
    charset: utf8
  # [optional]
  redis:
    host: 
    port: 6379  # default Redis port
    password: 
    db: 0       # default 
  # [optional] for knowledgebase (https://console.volcengine.com/vikingdb)
  viking:
    project:    # user project in Volcengine Viking DB
    region: cn-beijing
  # [optional] for knowledgebase with viking database (https://console.volcengine.com/tos)
  tos:
    endpoint: tos-cn-beijing.volces.com # default Volcengine TOS endpoint
    region: cn-beijing                  # default Volcengine TOS region
    bucket:

# [optional] for prompt optimization in cli/app (https://www.volcengine.com/docs/82379/1587837)
agent_pilot:
  api_key:

logging:
  # ERROR
  # WARNING
  # INFO
  # DEBUG
  level: DEBUG
```

### 管理

为管理繁多的配置项，VeADK 提供了根据`config.yaml`文件的自动化配置管理方案。您在配置文件中的所有配置将会根据层级，自动转为大写并使用下划线连接，统一注册成为运行时的环境变量。

例如下面的配置项：

```yaml
model:
  name:
  api_key:
  api_base:
    base_a:
    base_b:
    ...
```

将会被转为如下几条环境变量：

```bash
MODEL_NAME=
MODEL_API_KEY=
MODEL_API_BASE_BASE_A=
MODEL_API_BASE_BASE_B=
...
```

VeADK 中提供了一个`getenv`方法来读取相关配置，您无需在各组件中次手动传入某个配置的参数。
