# 知识库

自建知识库与使用火山引擎现有知识库的最大区别是：知识文档的分片和数据库维护。


## 自建知识库

自建知识库需要开发者本地进行知识文档的切片，并维护一个数据库（或云数据库）来存储知识文档。

你可以通过如下方式定义一个自建知识库：

```python
from veadk.knowledgebase.knowledgebase import KnowledgeBase

knowledgebase = KnowledgeBase(backend="opensearch")
knowledgebase.add(
    knowledgebase_data, app_name=app_name, user_id=user_id, session_id=session_id
) # 这里的数据应当是已切片完成的格式，定义为`list[str]`

# 将知识库挂载至Agent
agent = Agent(knowledgebase=knowledgebase)
```

## 火山知识库

VeADK中提供了VikingDB支持的数据库，支持用户直接上传本地文档，文档切片和存储维护均在云上自动执行：

```python
from veadk.knowledgebase.knowledgebase import KnowledgeBase

FILE_PATH = ...

knowledgebase = KnowledgeBase(backend="viking")
knowledgebase.add(
    FILE_PATH, app_name=app_name, user_id=user_id, session_id=session_id
)
```