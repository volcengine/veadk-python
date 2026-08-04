# OpenViking 知识库 + 长期记忆

这个示例同时使用 OpenViking 做 VeADK 知识库检索和长期记忆。OpenViking 会在远端完成
索引与记忆抽取，因此不需要配置 `MODEL_EMBEDDING_*`。

> English version: [README.md](./README.md)

## 准备

```bash
cd examples/13_openviking
cp .env.example .env
```

填入：

```bash
MODEL_AGENT_API_KEY=...
DATABASE_OPENVIKING_URL=http://127.0.0.1:1933
DATABASE_OPENVIKING_API_KEY=...
DATABASE_OPENVIKING_USER_ID=openviking_demo
```

`DATABASE_OPENVIKING_USER_ID` 是 OpenViking 中的 owner/context 标识，用在
`viking://user/<user_id>/...` 路径里。建议每个 agent/application context 保持稳定，
从而隔离资源和记忆。

## 运行

```bash
python main.py
```

脚本会把 `docs/company_faq.md` 导入到：

```text
viking://user/{DATABASE_OPENVIKING_USER_ID or default}/resources/company_faq/
```

随后运行两轮会话。第一轮用知识库回答问题，并保存用户偏好；第二轮让智能体通过
OpenViking 长期记忆回忆该偏好，同时回答另一个制度问题。

## 配置方式

### 推荐：使用 `.env` 或 `config.yaml`

本示例把 OpenViking 连接信息放在代码外：

```python
knowledgebase = KnowledgeBase(backend="openviking", index="company_faq")
long_term_memory = LongTermMemory(backend="openviking", app_name=APP_NAME)
```

VeADK 会从 `.env`、系统环境变量，或等价的 `config.yaml` 结构读取配置：

```yaml
database:
  openviking:
    url: http://127.0.0.1:1933
    api_key: your-openviking-api-key
    user_id: openviking_demo
```

这是部署时的推荐方式：密钥不进入源码，同一份代码也可以切换到不同的 OpenViking
服务或 owner/context。

### `url` 与 `target_uri`

没有 `target_url` 这个参数。OpenViking 里这里涉及两个不同概念：

- `url` / `DATABASE_OPENVIKING_URL`：OpenViking HTTP 服务地址，例如
  `http://127.0.0.1:1933`。
- `target_uri` / `DATABASE_OPENVIKING_TARGET_URI`：知识库使用的 OpenViking
  资源目录，例如 `viking://user/openviking_demo/resources/company_faq/`。

`url` 用于连接服务，是必需配置。`target_uri` 是可选配置；未设置时，VeADK 会根据
`openviking_user_id` 和 `index` 生成默认资源目录。

### URI 拼接规则

对于 `KnowledgeBase(backend="openviking")`，VeADK 会按以下规则选择知识资源目录：

1. 如果设置了 `target_uri` 或 `DATABASE_OPENVIKING_TARGET_URI`，VeADK 会直接使用这个
   完整的 OpenViking resource URI，不会再和 `openviking_user_id` 或 `index` 拼接。
2. 如果没有设置 `target_uri`，VeADK 会生成：

   ```text
   viking://user/{openviking_user_id or default}/resources/{index}/
   ```

3. `openviking_user_id` 的解析顺序是
   `backend_config["openviking_user_id"]`、兼容 alias `backend_config["user_id"]`、
   `DATABASE_OPENVIKING_USER_ID`、最后是 `default`。
4. 不传 `backend_config` 时，`index` 来自 `KnowledgeBase(index=...)` 或 `app_name`；
   一旦传入 `backend_config`，请把 `index` 写在 `backend_config["index"]`。
5. 显式 `target_uri` 如果以 `viking://` 开头但没有 `/` 结尾，VeADK 会自动补尾部 `/`。

例如：

```python
KnowledgeBase(backend="openviking", index="company_faq")
```

配合 `DATABASE_OPENVIKING_USER_ID=team_a` 会使用：

```text
viking://user/team_a/resources/company_faq/
```

但如果写成：

```python
KnowledgeBase(
    backend="openviking",
    backend_config={
        "index": "company_faq",
        "target_uri": "viking://user/shared/resources/hr",
    },
)
```

则会直接使用：

```text
viking://user/shared/resources/hr/
```

### 显式传入 `backend_config`

当一个进程需要连接多个 OpenViking context，或测试时需要覆盖环境配置，可以使用
`backend_config`：

```python
knowledgebase = KnowledgeBase(
    backend="openviking",
    backend_config={
        "index": "company_faq",
        "url": "http://127.0.0.1:1933",
        "api_key": "your-openviking-api-key",
        "openviking_user_id": "openviking_demo",
        # 可选。只有需要固定到已有资源目录时才设置。
        # "target_uri": "viking://user/openviking_demo/resources/company_faq/",
    },
)

long_term_memory = LongTermMemory(
    backend="openviking",
    app_name=APP_NAME,
    backend_config={
        "openviking_user_id": "openviking_demo",
    },
)
```

如果传入 `KnowledgeBase.backend_config`，请把 `index` 也放在这个字典里。不传
`backend_config` 时，`index` 可以来自 `KnowledgeBase(index=...)` 或 `app_name`。

### 各个 id 的影响

- `DATABASE_OPENVIKING_USER_ID` / `openviking_user_id` 是 OpenViking 的
  owner/context 标识，会影响默认知识库目录和长期记忆命名空间。
- `Runner.user_id` 是最终用户标识。OpenViking 长期记忆后端会把它作为 `peer_id`
  传入，因此同一个 owner/context 下，不同最终用户的记忆会隔离。
- `KnowledgeBase.index` 用来命名默认资源目录。

不设置 `DATABASE_OPENVIKING_TARGET_URI` 时，知识资源会进入：

```text
viking://user/{openviking_user_id or default}/resources/{index}/
```

只有需要使用已有目录或自定义 OpenViking 资源目录时，才设置
`DATABASE_OPENVIKING_TARGET_URI`。一旦设置，VeADK 会直接使用该目录，而不是再根据
`openviking_user_id` 和 `index` 生成默认目录。

### Memory policy

通常不需要配置 `DATABASE_OPENVIKING_MEMORY_POLICY`。不配置时会使用 VeADK 默认策略。
只有想改变 OpenViking 如何抽取 self/peer 记忆，或调整存储的 memory types 时才需要设置。

## 说明

- 重复运行示例会再次导入本地文档。生产环境建议把知识导入放在初始化或 CI 流程中，
  不要放在每次请求路径上。
- 只有需要固定到自定义知识库目录时，才设置 `DATABASE_OPENVIKING_TARGET_URI`。
- 不配置 `DATABASE_OPENVIKING_MEMORY_POLICY` 时，会使用 VeADK 默认的 OpenViking 记忆策略。
