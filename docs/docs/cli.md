---
title: VeADK 命令行工具
---

## 命令行工具概述

VeADK 提供如下命令便捷您的操作：

| 命令 | 描述 | 说明 |
| :-- | :-- | :-- |
| `veadk init` | 生成可在 VeFaaS 中部署的项目脚手架 | 生成完整的项目目录结构，包括智能体定义文件、部署配置、依赖文件等，支持标准智能体和Web应用两种模板。 |
| `veadk create` | 在当前目录中创建一个新的智能体 | 创建智能体项目结构，生成.env环境配置文件、agent.py智能体定义文件和__init__.py包初始化文件。 |
| `veadk web` | 支持长短期记忆、知识库的前端调试界面 | 启动本地Web服务器，生成调试界面访问地址，配置记忆服务和知识库集成环境。 |
| `veadk kb` | 知识库相关操作 | 创建知识库索引文件，支持多种后端存储，生成向量化文档和检索配置文件。 |
| `veadk deploy` | 将某个项目部署到 VeFaaS 中 | 生成部署包文件，创建云资源配置，部署智能体到火山引擎函数计算服务并生成API访问端点。 |
| `veadk eval` | 支持不同后端的评测 | 生成评测报告文件，包含性能指标数据和测试结果，支持本地和远程智能体评估。 |
| `veadk prompt` | 优化智能体系统提示词 | 生成优化后的提示词文件，在PromptPilot工作空间中保存优化记录和版本历史。 |
| `veadk uploadevalset` | 评测集相关操作 | 上传评测数据集到Cozeloop平台，生成平台上的评测集记录和访问权限配置。 |
| `veadk pipeline` | 持续交付相关操作 | 创建CI/CD配置文件，设置自动化构建流水线。 |

## 项目初始化

### 简介

`veadk init` 命令用于初始化一个可部署到火山引擎 FaaS 的新 VeADK 项目。

该命令通过一个交互式设置流程，根据预定义的模板创建一个新的 VeADK 项目。它会生成一个完整的项目结构，包含所有部署到火山引擎云平台所需的文件、配置和部署脚本。

**可用模板:**

- **'template' (默认)**: 创建一个包含天气预报示例的 A2A/MCP/Web 服务器模板，适用于大多数智能体开发场景。
- **'web_template'**: 创建一个包含简单博客示例的 Web 应用模板，专为带有 UI 组件的 Web 应用设计。

### 参数说明

`veadk init` 命令本身主要通过交互式问答来收集项目名称、描述等信息，但也接受以下命令行参数：

| 参数 | 类型 | 描述 |
| :--- | :--- | :--- |
| `--vefaas-template-type` | TEXT | 指定项目初始化时使用的模板类型。 |
| `--help` | | 显示此帮助信息并退出。 |

### 使用示例

启动交互式初始化流程：
```bash
veadk init
```
执行以上命令后，您将被引导完成项目初始化流程。根据提示输入项目名称、本地目录名称、Volcengine FaaS 应用名称、Volcengine API Gateway 实例名称、服务名称、上游名称等信息，以默认项目名称`weather-reporter`为例：
![veadk_init](./assets/images/cli/cli_veadk_init.gif)
您也可以在初始化时直接指定使用 `web_template` 模板：
```bash
veadk init --vefaas-template-type web_template
```
执行完成之后，命令所生成的目录结构如下：
```
weather-reporter/
├────src                    # 智能体项目源代码目录
│   ├────weather_report     # 天气预报智能体项目目录
│   │    ├──────agent.py    # 主要智能体定义文件
│   │    └──────__init__.py # 智能体项目包初始化文件
│   ├── agent.py            # 主要智能体定义文件
│   ├── app.py              # 主要 Web 应用定义文件
│   ├── requirements.txt    # 项目依赖文件
│   ├── run.sh              # 项目运行脚本
│   └── __init__.py         # 智能体项目包初始化文件
├────clean.py               # 清理脚本，用于删除项目生成的临时文件
├────deploy.py              # 部署脚本，用于将项目部署到火山引擎 FaaS 平台
└────__init__.py            # 智能体项目包初始化文件
```

## 创建智能体

### 简介

`veadk create` 命令用于创建一个新的 VeADK 智能体项目，并预置模板文件。

此命令会创建一个新的智能体项目目录，其中包含开始 VeADK 智能体开发所需的所有文件，包括环境配置、智能体定义和包初始化。该命令会通过交互式提问处理缺失的参数，并对已存在的目录进行安全检查。

### 参数说明

| 参数 | 类型 | 描述 |
| :--- | :--- | :--- |
| `AGENT_NAME` | TEXT | (可选) 要创建的智能体的名称，也将作为目录名。如果未在命令行中提供，将以交互方式提示用户输入。 |
| `--ark-api-key` | TEXT | (可选) 用于模型身份验证的 ARK API 密钥。如果未提供，将提示用户输入或稍后配置。 |
| `--help` | | 显示此帮助信息并退出。 |

**注意：**

- 智能体名称将同时作为目录名和项目标识符。
- API 密钥可以稍后通过编辑 `.env` 文件进行配置。
- 生成的智能体可立即使用 `veadk web` 命令运行。

### 使用示例

启动交互式创建流程：
```bash
veadk create
```
您也直接指定智能体名称来创建，例如：
```bash
veadk create location-agent
```
在执行以上命令后，您将被引导完成智能体创建流程。首先，系统会提示您选择以何种方式提供 API Key，您可以选择直接输入或稍后配置。如下所示：
![veadk_create](./assets/images/cli/cli_veadk_create.gif)
您也可以在创建时同时提供 API Key：
```bash
veadk create location-agent --ark-api-key "xxxxxx"
```
该命令会创建一个包含 API Key 的 `.env` 文件。您可以稍后编辑此文件以更新 API Key。命令创建的完整目录结构如下：
```
location-agent/
├── .env          # 包含 API key 的环境配置
├── __init__.py   # Python 包初始化文件
└── agent.py      # 主要智能体定义文件
```
这时，您可以使用 `veadk web` 命令来运行示例`location-agent` 智能体，具体执行方式及参数说明请参考下一节：[Web 调试界面](#web-调试界面)。

## Web 调试界面

### 简介

`veadk web` 命令用于启动一个本地 Web 服务器，以便在浏览器中与您的智能体进行交互和调试。VeADK 完全兼容 Google ADK 的 `adk web` 命令，确保与现有 Google ADK 生态系统的无缝集成。

该命令会启动一个支持 VeADK 智能体短期和长期记忆功能的 Web 服务器。它会自动检测并加载当前目录下的智能体，并配置相应的记忆服务。

### 参数说明

`veadk web` 命令全面兼容 Google ADK 中的 `adk web` 命令，支持相同的参数接口和行为模式。

| 参数 | 类型 | 描述 |
| :--- | :--- | :--- |
| `--port` | INTEGER | 指定 Web 服务器监听的端口号，默认值为 8000 |
| `--host` | TEXT | 指定 Web 服务器绑定的主机地址，默认值为 127.0.0.1 |
| `--log-level` | [debug\|info\|warning\|error] | 设置日志输出级别，默认值为 info |
| `--help` | | 显示此帮助信息并退出 |

**长短期记忆机制**

VeADK Web 调试界面支持智能体的短期记忆和长期记忆功能，这些机制通过以下方式传递到 Web 界面中：

**短期记忆传递**：
   - 智能体在交互过程中产生的对话历史会自动保存为短期记忆
   - Web 界面通过会话 ID 关联智能体的短期记忆数据
   - 每次对话都会加载对应的短期记忆上下文

**长期记忆传递**：
   - 智能体的知识库配置信息会传递给 Web 界面
   - Web 界面支持基于长期记忆的智能体行为定制
   - 长期记忆数据通过智能体配置自动加载

**记忆服务集成**：
   - 自动检测并配置相应的记忆后端服务
   - 支持多种记忆存储类型（local、mysql、redis等）
   - 记忆数据在 Web 界面中实时同步和更新

### 使用示例

在您的智能体项目根目录下，直接运行以下命令即可启动 Web 调试界面：

```bash
# 使用默认配置启动 Web 服务器
veadk web
# 指定端口
veadk web --port 8080
```

该命令能够自动读取执行命令目录中的 `agent.py` 文件，并加载其中的 `root_agent` 全局变量。服务启动后，通常可以在 `http://127.0.0.1:8000` 访问。


### 使用示例

使用示例如下图示：
![veadk_web](./assets/images/cli/cli_veadk_web.gif)
在界面左上角的选择框中，您可以选择要调试的智能体。在本示例中，您可以看到您创建的`location-agent`智能体。


## 知识库

`veadk kb` 命令是用于管理 VeADK 知识库的命令集。

### `veadk kb add`

将文件或目录添加到指定的知识库后端。

#### 简介

该命令支持多种后端类型，用于存储和索引知识内容：

- **local**: 基于 SQLite 的本地文件存储，适用于开发和小型部署。
- **opensearch**: 兼容 Elasticsearch 的搜索引擎，推荐用于具有大量文档的生产环境。
- **viking**: 火山引擎的托管向量数据库服务，为语义搜索和 RAG 应用优化。
- **redis**: 具有向量搜索功能的内存数据存储，适用于快速检索、较小的知识库。

该命令可以处理单个文件（如 PDF, TXT, MD, DOCX 等）或包含多个受支持文件的整个目录。

#### 参数说明

| 参数 | 类型 | 描述 |
| :--- | :--- | :--- |
| `--backend` | [local\|opensearch\|viking\|redis] | **(必需)** 知识库后端类型。 |
| `--app_name` | TEXT | 用于组织和隔离知识库数据的应用标识符。 |
| `--index` | TEXT | 知识库索引标识符，在 `app_name` 内唯一。|
| `--path` | TEXT | **(必需)** 要添加的知识内容的文件或目录路径。 |
| `--help` | | 显示此帮助信息并退出。 |

其中，backend当前支持4种类型：local、opensearch、viking、redis。

- **local**: 基于本地内存的知识库存储，适用于开发和小型部署。
- **opensearch**: 兼容 Elasticsearch 的搜索引擎，推荐用于具有大量文档的生产环境。
- **viking**: 火山引擎的托管向量数据库服务，为语义搜索和 RAG 应用优化。
- **redis**: 具有向量搜索功能的内存数据存储，适用于快速检索、较小的知识库。

**注意**

veadk kb add 命令需要将您的文档内容转换成向量，这个过程默认会使用一个嵌入模型（Embedding Model）服务，该服务会将文档内容转换为向量表示。您可以根据需要配置不同的嵌入模型，例如火山引擎的方舟大模型平台。

您可以通过在项目根目录下的`.env`文件设置环境变量 `MODEL_EMBEDDING_API_KEY` 来指定您的嵌入模型服务的API Key。

同时，如果选择非本地后端（如 opensearch、viking、redis），您需要确保已正确配置相关环境变量（可以在项目根目录下的`.env`文件中设置）等。

#### 使用示例

下面的示例将演示将单个文件添加到redis作为后端的知识库，并在后续的智能体调用中使用。

假设您在当前目录下有一个名为`qa.md`的文件，内容如下：
```
# 智能客服知识库

## 1. 公司简介

VE科技是一家专注于智能客服与知识管理的高科技公司。我们的产品名称是 **智能客服系统**，通过自然语言处理与知识库检索，为企业客户提供高效、智能的自动化客服解决方案。

---

## 2. 产品功能说明

- **自动问答**：基于知识库，快速响应常见问题。  
- **多渠道接入**：支持网页、App、微信、飞书等渠道。  
- **智能推荐**：根据上下文推荐相关答案。  
- **数据分析**：提供用户问题统计与客服绩效报告。  
- **自助知识库管理**：支持非技术人员快速编辑知识内容。  

---

## 3. 常见问题 (FAQ)

### Q1: 智能客服系统支持哪些语言？

A1: 目前支持 **中文** 和 **英文**，后续将逐步增加日语、韩语等多语言支持。  

### Q2: 系统可以接入现有的 CRM 吗？

A2: 可以。我们的系统支持通过 API 与主流 CRM 系统（如 Salesforce、Zoho、金蝶）进行无缝集成。  

### Q3: 如果机器人无法回答用户问题，会怎么办？

A3: 系统会自动将问题转接至人工客服，并在后台记录该问题，方便管理员补充到知识库。  

### Q4: 知识库内容多久更新一次？

A4: 知识库支持 **实时更新**，管理员提交后即可立即生效。  

---

## 4. 联系我们

- 官网：[https://www.example.com](https://www.example.com)  
- 客服邮箱：support@ve
- 服务热线：400-123-4567  

```

您可以使用以下命令将其添加到本地知识库：
```bash
veadk kb add --backend redis --app_name app --path ./qa.md
```
**注意**

- 在本例中，我们选择的是redis后端。您需要事先在本地目录的`.env`文件中配置好`DATABASE_REDIS_HOST`,`DATABASE_REDIS_HOST`,`DATABASE_REDIS_PORT`,`DATABASE_REDIS_PASSWORD`(以及可选的`DATABASE_REDIS_USER`)等环境变量。
- 您需要确认您配置的redis服务是否正常运行，并且端口号是否与您在`.env`文件中配置的一致。
- 您需要确保redis服务已开启向量搜索功能。

操作如下图示：
![veadk_kb_add](./assets/images/cli/cli_veadk_kb_add.gif)

接下来，您可以通过如下代码来验证智能库是否添加成功：
```python
import asyncio

from veadk import Agent, Runner
from veadk.knowledgebase import KnowledgeBase
from veadk.memory import ShortTermMemory

app_name = "app"
user_id = "user"
session_id = "session"

knowledgebase = KnowledgeBase(backend="redis", app_name=app_name, index="v1")

agent = Agent(
    name="customer_service",
    instruction="Answer customer's questions according to your knowledgebase.",
    knowledgebase=knowledgebase,
)
root_agent = agent

runner = Runner(
    agent=agent,
    short_term_memory=ShortTermMemory(),
    app_name=app_name,
    user_id=user_id,
)

response = asyncio.run(
    runner.run(messages="你们的产品都有什么功能？", session_id=session_id)
)

print(response)

```
**注意**

- 您需要确认您运行上述代码时，redis服务正常运行并已经开启向量搜索功能。同时，这段代码需要和上面的命令共享相同的环境变更配置（建议在相同目录下运行，这样可以共享相同的.env配置文件。）
- 代码中的'app_name'需要与上面的命令中的'app_name'保持一致，在本 示例中为'app'。

操作如下图示：
![veadk_kb_test](./assets/images/cli/cli_veadk_kb_test.gif)

## 部署

### 简介

`veadk deploy` 命令用于将一个 VeADK 项目部署到火山引擎的函数即服务 (FaaS) 平台。

该命令会从本地项目创建一个部署包，配置必要的云资源，并管理整个部署过程，包括模板生成、文件复制和云资源配置。部署流程会自动处理 `requirements.txt` 文件，并出于安全原因排除 `config.yaml`。

### 参数说明

| 参数 | 类型 | 描述 |
| :--- | :--- | :--- |
| `--access-key` | TEXT | 火山引擎访问密钥 (AK)。如果未提供，将尝试使用 `VOLCENGINE_ACCESS_KEY` 环境变量。 |
| `--secret-key` | TEXT | 火山引擎秘密密钥 (SK)。如果未提供，将尝试使用 `VOLCENGINE_SECRET_KEY` 环境变量。 |
| `--vefaas-app-name` | TEXT | **(必需)** 将要部署到的目标火山引擎 FaaS 应用的名称。 |
| `--veapig-instance-name` | TEXT | (可选) 用于配置外部 API 访问的火山引擎 API 网关实例名称。 |
| `--veapig-service-name` | TEXT | (可选) 火山引擎 API 网关服务名称。 |
| `--veapig-upstream-name` | TEXT | (可选) 火山引擎 API 网关上游名称。 |
| `--short-term-memory-backend`| [local\|mysql] | 短期记忆存储的后端类型。默认为 `local`。 |
| `--use-adk-web` | | 为部署的智能体启用 ADK Web 界面。 |
| `--path` | TEXT | 包含要部署的 VeADK 项目的本地目录路径。默认为当前目录 `.`。 |
| `--help` | | 显示此帮助信息并退出。 |

### 使用示例

在项目根目录下，执行部署（需要提供AK/SK和FaaS应用名）：
```bash
veadk deploy \
  --vefaas-app-name my-cloud-app \
  --access-key "YOUR_ACCESS_KEY" \
  --secret-key "YOUR_SECRET_KEY"
```

部署指定路径下的项目，并启用 Web 界面：
```bash
veadk deploy \
  --path ./my-agent-project \
  --vefaas-app-name my-cloud-app \
  --use-adk-web \
  --access-key "YOUR_ACCESS_KEY" \
  --secret-key "YOUR_SECRET_KEY"
```

**注意**

- 您也可以在项目根目录下的`.env`文件中设置 `VOLCENGINE_ACCESS_KEY` 和 `VOLCENGINE_SECRET_KEY` 环境变量，避免在命令行中明文暴露 AK/SK。

- 部署时可以指定 `--veapig-instance-name`、`--veapig-service-name`、`--veapig-upstream-name` 来配置外部 API 访问，如果未指定，系统将使用默认值并自动创建. 您可以使用已经创建的VeAPIG实例和服务，也可以在部署时由系统自动创建新的实例和服务.

- 在部署过程中，您可以在火山引擎[VeFaas控制台](https://console.volcengine.com/vefaas/)查看部署状态和日志，确保部署成功。也可以在控制台上查看部署过程的详细日志，如下图示：![部署日志](./assets/images/cli/cli_veadk_deploy_vefaas_log.png)

部署成功后，您可以在在火山引擎[VeFaas控制台](https://console.volcengine.com/vefaas/)查看您部署的智能体应用。

## 提示词优化

### 简介

`veadk prompt` 命令使用火山引擎 PromptPilot 服务，根据反馈和最佳实践来优化智能体的系统提示词 (System Prompt)。

该命令会从指定的本地文件中加载智能体，并使用指定的模型对其提示词进行智能优化。

### 参数说明

| 参数 | 类型 | 描述 |
| :--- | :--- | :--- |
| `--path` | TEXT | 包含 `agent=...` 全局变量的智能体文件路径。默认为当前目录 `.`。 |
| `--feedback` | TEXT | 用于优化提示词的用户反馈和建议。 |
| `--api-key` | TEXT | PromptPilot 服务的 API Key。 |
| `--workspace-id` | TEXT | PromptPilot 的工作空间 ID。 |
| `--model-name` | TEXT | 用于提示词优化的模型名称。 |
| `--help` | | 显示此帮助信息并退出。 |

### 使用示例

以优化weather_reporter智能体的系统提示词为例：

```bash
veadk prompt --path ./weather_reporter/agent.py --feedback "希望提示词能够更加具体明确" --api-key "YOUR_API_KEY" --workspace-id "YOUR_WORKSPACE_ID"
```
** 注意 **

- 您需要先在火山引擎[PromptPilot控制台](https://promptpilot.volcengine.com/)创建一个项目，并获取 API Key 和工作空间 ID。
- 您也可以在项目根目录下的`.env`文件中设置 `PROMPTPILOT_API_KEY` 环境变量，避免在命令行中明文暴露 API Key。
- 本命令会自动读取智能体代码中的`Agent`对象的`instruction` 内容，作为目标来进行提示词优化。本本例中，原始的`instruction`内容如下所示：
```
Once user ask you weather of a city, you need to provide the weather report for that city by calling `get_city_weather`
```
本命令运行的结果如下所示：
```
Optimized prompt for agent weather_reporter:
# Role
You are a weather information provider. When the user asks about the weather of a city, your task is to offer an accurate weather report for that city.

# Task Requirements
- **User Inquiry**: Once the user asks about the weather of a specific city, you must call the `get_city_weather` function to obtain the relevant weather data.
- **Report Content**: The weather report should include at least the current temperature, weather conditions (such as sunny, cloudy, rainy), and wind speed of the city. If available, you can also provide additional information like humidity and air quality.
- **Format**: Present the weather report in a clear and easy - to - understand format. For example: "In [City Name], the current temperature is [Temperature], the weather condition is [Weather Conditions], and the wind speed is [Wind Speed]."

# Additional Notes
- If the user's inquiry is not clear about the city name or contains ambiguous information, ask the user to clarify the city name before proceeding.
- Ensure that the information provided is based on the data obtained from the `get_city_weather` function and is as accurate as possible.
```


## 评测

### 简介

`veadk eval` 命令使用指定的评测数据集和指标来对智能体进行综合评估。

该命令支持两种评估模式：

- **本地评估**: 从本地源代码加载并评估智能体。
- **远程评估**: 通过 URL 连接并评估已部署为 A2A 模式的智能体。

同时支持两种评估框架：

- **adk**: Google 的 Agent Development Kit 评估框架，提供标准化指标。
- **deepeval**: 更高级的评估框架，支持包括 GEval 和工具使用准确性在内的可定制指标。

### 参数说明

| 参数 | 类型 | 描述 |
| :--- | :--- | :--- |
| `--agent-dir` | TEXT | (本地评估) 待评估智能体的本地目录路径。必须包含一个导出了 `root_agent` 变量的 `agent.py` 文件。默认为当前目录 `.`。 |
| `--agent-a2a-url` | TEXT | (远程评估) 已部署的 A2A (Agent-to-Agent) 模式智能体的完整 URL。 |
| `--evalset-file` | TEXT | **(必需)** Google ADK 格式的评测数据集文件路径。 |
| `--evaluator` | [adk\|deepeval] | **(必需)** 要使用的评估框架，选择 `adk` 或 `deepeval`。 |
| `--judge-model-name` | TEXT | 用于评估判断的语言模型名称。默认为 `doubao-1-5-pro-256k-250115`。此参数在 `adk` 评估器下无效。 |
| `--volcengine-access-key` | TEXT | 用于火山引擎模型认证的访问密钥 (AK)。 |
| `--volcengine-secret-key` | TEXT | 用于火山引擎模型认证的秘密密钥 (SK)。 |
| `--help` | | 显示此帮助信息并退出。 |

**注意：**

- 必须提供 `--agent-dir` 或 `--agent-a2a-url` 两者之一。
- 如果两者都提供，`--agent-a2a-url` 优先。
- 需要事先准备好评测数据集文件，您可以参考[评测](/observation/evaluation)中的说明，创建一个符合 Google ADK 格式的 JSON 文件。

### 使用示例

**本地评估示例:**
```bash
veadk eval \
  --agent-dir ./my-agent \
  --evalset-file ./eval.json \
  --evaluator adk
```

**远程评估示例:**
```bash
veadk eval \
  --agent-a2a-url http://my-agent-url.com/invoke \
  --evalset-file ./eval.json \
  --evaluator deepeval \
  --volcengine-access-key "YOUR_AK" \
  --volcengine-secret-key "YOUR_SK"
```

## 评测集

### 简介

`veadk uploadevalset` 命令用于将评测数据集的条目从本地 JSON 文件上传到 CozeLoop 平台，以进行智能体评估和测试。

该命令会处理 Google ADK 格式的评测用例，并将其转换为 CozeLoop 期望的格式。

### 参数说明

| 参数 | 类型 | 描述 |
| :--- | :--- | :--- |
| `--file` | TEXT | **(必需)** 包含数据集条目的 JSON 文件路径。 |
| `--cozeloop-workspace-id` | TEXT | CozeLoop 工作空间 ID。如果未提供，将使用 `OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME` 环境变量。 |
| `--cozeloop-evalset-id` | TEXT | CozeLoop 评测集 ID。如果未提供，将使用 `OBSERVABILITY_OPENTELEMETRY_COZELOOP_EVALSET_ID` 环境变量。 |
| `--cozeloop-api-key` | TEXT | CozeLoop API 密钥。如果未提供，将使用 `OBSERVABILITY_OPENTELEMETRY_COZELOOP_API_KEY` 环境变量。 |
| `--help` | | 显示此帮助信息并退出。 |

### 使用示例

```bash
veadk uploadevalset \
  --file ./my_eval_set.json \
  --cozeloop-workspace-id "YOUR_WORKSPACE_ID" \
  --cozeloop-evalset-id "YOUR_EVALSET_ID" \
  --cozeloop-api-key "YOUR_API_KEY"
```

## 持续交付

### 简介

`veadk pipeline` 命令用于将您的 VeADK 项目与火山引擎流水线集成，以实现自动化的 CI/CD 部署。

该命令会建立一个完整的 CI/CD 流水线，每当有变更推送到指定的 GitHub 仓库时，流水线会自动构建、容器化并部署您的 VeADK 智能体项目。它会创建所有必要的云基础设施，包括容器镜像仓库 (CR) 资源、FaaS 函数和流水线配置。

### 参数说明

| 参数 | 类型 | 描述 |
| :--- | :--- | :--- |
| `--veadk-version` | TEXT | 用于容器化的基础 VeADK 镜像标签。可以是 'preview', 'latest', 或特定版本。 |
| `--github-url` | TEXT | **(必需)** 您的项目的 GitHub 仓库 URL。 |
| `--github-branch` | TEXT | **(必需)** 您项目的 GitHub 分支。 |
| `--github-token` | TEXT | **(必需)** 用于管理您项目的 GitHub 令牌。 |
| `--volcengine-access-key` | TEXT | 火山引擎访问密钥 (AK)。如果未设置，将使用环境变量 `VOLCENGINE_ACCESS_KEY`。 |
| `--volcengine-secret-key` | TEXT | 火山引擎秘密密钥 (SK)。如果未设置，将使用环境变量 `VOLCENGINE_SECRET_KEY`。 |
| `--region` | TEXT | 火山引擎 VeFaaS, CR, 和 Pipeline 的地域。默认为 `cn-beijing`。 |
| `--cr-instance-name` | TEXT | 火山引擎容器镜像仓库 (CR) 实例名称。默认为 `veadk-user-instance`。 |
| `--cr-namespace-name` | TEXT | CR 命名空间名称。默认为 `veadk-user-namespace`。 |
| `--cr-repo-name` | TEXT | CR 仓库名称。默认为 `veadk-user-repo`。 |
| `--vefaas-function-id` | TEXT | 火山引擎 FaaS 函数 ID。如果未设置，将自动创建一个新函数。 |
| `--help` | | 显示此帮助信息并退出。 |

**注意：**

- GitHub 令牌必须具有适当的仓库访问权限。
- 所有火山引擎资源都将在指定的地域创建。
- 流水线将在创建后立即触发以进行初始部署。

### 使用示例

```bash
veadk pipeline \
  --github-url https://github.com/your-user/your-repo \
  --github-branch main \
  --github-token YOUR_GITHUB_TOKEN \
  --volcengine-access-key YOUR_AK \
  --volcengine-secret-key YOUR_SK \
  --region cn-beijing
```

## AgentKit 命令兼容

VeADK 命令行兼容 AgentKit 命令，您可以直接在 AgentKit 相关命令前添加 `veadk` 前缀，例如：

创建一个新的 AgentKit 项目：

```bash
veadk agentkit init
```

进行项目配置：

```bash
veadk agentkit config
```

部署项目到火山引擎 AgentKit 平台：

```bash
veadk agentkit launch
```

更多 AgentKit 命令请参考 [AgentKit 命令行工具](https://volcengine.github.io/agentkit-sdk-python/content/2.agentkit-cli/1.overview.html)。
