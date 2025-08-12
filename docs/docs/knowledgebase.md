# 知识库

VeADK 支持将结构化或文档型知识作为 Agent 的外部知识源接入。开发者可选择自建知识库，或使用火山引擎现有知识库。自建知识库与使用火山引擎现有知识库的最大区别是：知识文档的分片和数据库维护。VeADK 中知识库的创建如下：

```python
from veadk.knowledgebase.knowledgebase import KnowledgeBase

knowledgebase = KnowledgeBase(backend=...)
```

知识库中的 backend 字段定义如下：

| backend | 说明 |
| --- | --- |
| local | GIGO 模式的内存存储，不具备向量检索功能，仅用于测试 |
| [viking](https://www.volcengine.com/docs/84313/1254437) | 火山引擎 Viking DB 服务 |
| opensearch | OpenSearch 数据库 |
| redis | Redis 数据库，但不具备向量搜索功能 |
| mysql | MySQL 数据库，但不具备向量搜索功能 |

## 自建知识库

自建知识库需要开发者本地进行知识文档的切片，并维护一个数据库（或云数据库）来存储知识文档。

以下示例通过使用 opensearch 定义一个如下的自建知识库：

```python
from veadk import Agent
from veadk.knowledgebase.knowledgebase import KnowledgeBase

knowledgebase = KnowledgeBase(backend="opensearch")
knowledgebase.add(
    knowledgebase_data, app_name=app_name, user_id=user_id, session_id=session_id
) # knowledgebase_data 应当是已切片完成的格式，定义为`list[str]`

# 将知识库挂载至Agent
agent = Agent(knowledgebase=knowledgebase)
```

## 火山知识库

VeADK 中提供了火山引擎支持的知识库 [VikingDB](https://www.volcengine.com/docs/84313/1254437)，支持用户直接上传本地文档，文档切片和存储维护均在云上自动执行：

```python
from veadk import Agent
from veadk.knowledgebase.knowledgebase import KnowledgeBase

FILE_PATH = ...

knowledgebase = KnowledgeBase(backend="viking")
knowledgebase.add(
    FILE_PATH, app_name=app_name, user_id=user_id, session_id=session_id
)

agent = Agent(knowledgebase=knowledgebase)
```
