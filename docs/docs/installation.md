# 安装

本章主要介绍VeADK的安装方法和基本配置项。

## 环境

### 从源码构建

本项目使用`uv`进行构建（[安装`uv`](https://docs.astral.sh/uv/getting-started/installation/))。

```bash
# clone repo first
git clone https://github.com/volcengine/veadk-python.git

cd veadk-python

uv venv --python 3.10

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

### PyPI

本项目近期将发布在PyPI上，届时你可以使用`pip`进行安装。

```bash
pip install veadk-python
```

## 配置

VeADK在仓库中提供了一个`config.yaml.example`文件，你可以根据这个文件来创建你的配置文件。在样例文件中，我们标明了一个Agent运行的必需配置和可选（optional）配置。

### 说明

想要运行一个Agent，你需要进行基础配置。在你的项目根目录中创建一个`config.yaml`文件，并填入如下信息：

```yaml
# config.yaml
model:
  provider: # 如果你使用的是方舟大模型，请在这里填入`openai` 
  name: 
  api_base: 
  api_key: 
```

你创建的配置文件名称我们推荐为`config.yaml`，因为VeADK中的配置模块将会自动寻找并加载这个文件中的配置为环境变量，可以帮你省去填写配置项的时间。完整的配置项你可以参考[`config.yaml.example`文件](https://github.com/volcengine/veadk-python/blob/main/config.yaml.example)。

下面是详细的配置说明：

```yaml
model:
  # [required] for running agent
  agent:
    provider: openai
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
  # [optional] for Viking DB and `web_search` tool
  ak:
  sk:

tool:
  # [optional] https://console.volcengine.com/ask-echo/my-agent
  vesearch: 
    endpoint:   # `bot_id`
    api_key: 
  # [optional] 
  web_scraper: 
    endpoint: 
    api_key:    # `token`
  # [optional] https://open.larkoffice.com/app
  lark: 
    endpoint:   # `app_id`
    api_key:    # `app_secret`
    token:      # `user_token`


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
  # [optional] for knowledgebase with viking database
  tos:
    endpoint: tos-cn-beijing.volces.com # default Volcengine TOS endpoint
    region: cn-beijing                  # default Volcengine TOS region
    bucket:
```

### 管理

为管理繁多的配置项，我们提供了根据`config.yaml`自动化的配置管理方案：你在配置文件中的所有配置将会根据层级，自动转为大写并使用下划线连接，统一配置成为运行时的环境变量。

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

VeADK中提供了一个`getenv`方法来读取相关配置，你不必每次手动传入某个类的参数。
