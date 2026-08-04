# OpenViking 改动技术方案
## 本次改动概览
本次改动为 OpenViking 后端补齐了配置加载、资源归属、默认 URI、生命周期释放、示例工程和使用文档。
KnowledgeBase 的 OpenViking 后端新增了 `openviking_user_id` 配置，用于区分 OpenViking 资源归属；当用户没有显式传入 `target_uri` 时，会根据 `openviking_user_id` 和知识库 `index` 生成默认资源 URI。
LongTermMemory 的 OpenViking 后端新增了 `openviking_user_id` 和 `memory_policy` 配置，用于区分长期记忆归属并允许用户配置记忆策略。
OpenViking 后端补齐了配置初始化能力，避免仅使用 KnowledgeBase 或 LongTermMemory 时 `.env`、`config.yaml` 中的 OpenViking 配置未被加载。
KnowledgeBase 新增了 `close()` 释放入口，OpenViking KnowledgeBase 后端也新增了客户端关闭与再次使用时重建客户端的能力，避免长生命周期进程中连接资源无法主动释放。
OpenViking KnowledgeBase 默认 URI 的路径片段增加了校验，避免 `openviking_user_id` 或 `index` 中包含不安全路径字符导致资源路径异常。
配置模型新增了 OpenViking 的 `user_id` 与 `memory_policy` 字段，方便通过统一配置文件描述 OpenViking 知识库与长期记忆行为。
示例目录新增了 `examples/13_openviking`，提供独立的 OpenViking 使用示例，覆盖 KnowledgeBase、LongTermMemory、环境变量、显式 `backend_config` 和资源释放用法。
已有示例中的 `examples/*/.env.example` 补充了 OpenViking 相关注释，说明用户如何配置 OpenViking 服务地址、资源 URI、用户标识和记忆策略。
README 与文档补充了 OpenViking 的配置说明、URI 规则、示例入口和使用注意事项，帮助用户从本地 RAG 或 LongTermMemory 示例切换到 OpenViking。
## 配置优先级
KnowledgeBase 的 `target_uri` 优先级为：调用 `add_resource`、`search`、`read` 等方法时显式传入的 `target_uri` 最高，其次是 `backend_config["target_uri"]`，再次是环境变量 `DATABASE_OPENVIKING_TARGET_URI`，最后才使用默认生成的 URI。
KnowledgeBase 的 `openviking_user_id` 优先级为：`backend_config["openviking_user_id"]` 最高，其次兼容 `backend_config["user_id"]`，再次是环境变量 `DATABASE_OPENVIKING_USER_ID`，最后使用 `default`。
KnowledgeBase 的 `index` 在未显式传入 `backend_config` 时可来自 `KnowledgeBase(index=...)` 或应用名；如果已经显式传入 `backend_config`，则推荐在 `backend_config["index"]` 中声明，避免资源路径不明确。
LongTermMemory 的 `memory_policy` 优先级为：`backend_config["memory_policy"]` 最高，其次是环境变量或配置文件中的 `DATABASE_OPENVIKING_MEMORY_POLICY`，最后使用后端默认策略。
OpenViking 服务连接配置优先级为：代码中显式传入的 `url`、`api_key` 优先，其次读取环境变量或配置文件中的 `DATABASE_OPENVIKING_URL`、`DATABASE_OPENVIKING_API_KEY`。
`Runner.user_id` 主要用于会话和记忆使用者身份，不等同于 OpenViking 资源归属；OpenViking 资源归属应使用 `openviking_user_id` 或 `DATABASE_OPENVIKING_USER_ID` 配置。
## URI 规则说明
`DATABASE_OPENVIKING_URL` 是 OpenViking 服务地址，例如 HTTP API 地址；它只用于连接服务，不参与资源路径拼接。
`target_uri` 是完整的 OpenViking 资源 URI；只要用户显式配置了 `target_uri`，后端会直接使用该值，不会再把它和 `openviking_user_id`、`index` 做二次拼接。
当用户没有配置 `target_uri` 时，KnowledgeBase 会按 `viking://user/{openviking_user_id}/resources/{index}/` 生成默认 URI。
当显式 `target_uri` 使用 `viking://` 协议且末尾没有 `/` 时，后端会补齐尾部 `/`，以保持资源目录语义一致。
LongTermMemory 不使用 KnowledgeBase 的 `resources/{index}` 路径，而是按用户和 peer 维度写入记忆 URI，默认形态为 `viking://user/{openviking_user_id}/peers/{peer_id}/memories`。
示例：不显式配置 `target_uri` 时，`openviking_user_id=demo_user` 且 `index=company_faq` 会生成如下 KnowledgeBase URI。
```text
viking://user/demo_user/resources/company_faq/
```
示例：显式配置 `target_uri` 时，后端直接使用该完整 URI，不再拼接 `openviking_user_id` 或 `index`。
```text
viking://user/shared/resources/company_faq/
```
## 推荐配置方式
推荐通过 `.env` 或 `config.yaml` 管理 OpenViking 连接配置，通过代码中的 `KnowledgeBase(index=...)` 或 `backend_config` 管理具体业务资源。
如果一个项目只连接一个 OpenViking 服务，建议把服务地址和 API Key 放在 `.env` 中，把业务资源 ID 放在代码或 `config.yaml` 中。
如果一个项目需要同时访问多个 OpenViking 资源，建议在代码中为不同 KnowledgeBase 或 LongTermMemory 显式传入 `backend_config`，避免环境变量造成资源混用。
示例 `.env` 配置如下。
```env
DATABASE_OPENVIKING_URL=https://example.openviking.volces.com
DATABASE_OPENVIKING_API_KEY=your-api-key
DATABASE_OPENVIKING_USER_ID=demo_user
DATABASE_OPENVIKING_TARGET_URI=viking://user/demo_user/resources/company_faq/
```
示例 `backend_config` 配置如下。
```python
knowledgebase = KnowledgeBase(
    backend_config={
        "type": "openviking",
        "index": "company_faq",
        "openviking_user_id": "demo_user",
    },
)
```
示例显式 `target_uri` 配置如下。
```python
knowledgebase = KnowledgeBase(
    backend_config={
        "type": "openviking",
        "target_uri": "viking://user/shared/resources/company_faq/",
    },
)
```
示例长期记忆策略配置如下。
```python
long_term_memory = LongTermMemory(
    backend_config={
        "type": "openviking",
        "openviking_user_id": "demo_user",
        "memory_policy": {
            "max_recent_items": 20,
            "enable_summary": True,
        },
    },
)
```
## 示例与文档补充
新增的 `examples/13_openviking` 是独立 OpenViking 示例，用户可以从该目录直接查看 `.env.example`、README、示例知识文件和 `main.py`。
`examples/13_openviking/main.py` 展示了如何创建 OpenViking KnowledgeBase、添加文档资源、执行检索、启用 LongTermMemory，并在结束时调用 `knowledgebase.close()` 释放客户端资源。
`examples/13_openviking/.env.example` 展示了 OpenViking 服务地址、API Key、默认用户 ID、完整 `target_uri` 和长期记忆策略的配置方式。
`examples/05_knowledgebase_rag/.env.example` 和 `examples/09_long_term_memory/.env.example` 补充了 OpenViking 相关注释，说明原有示例如何切换到 OpenViking 后端。
`examples/README.md` 和 `examples/README.zh.md` 补充了 OpenViking 示例入口，方便用户从示例总览中找到独立 OpenViking 用法。
## 验证范围
已补充 OpenViking KnowledgeBase 与 LongTermMemory 的单元测试，覆盖配置加载、默认 URI、显式 `target_uri`、用户 ID 优先级、记忆策略、非法路径校验和资源释放行为。
已运行 OpenViking 相关测试并通过，覆盖文件为 `tests/test_openviking_knowledgebase.py` 和 `tests/test_openviking_long_term_memory.py`。
已运行 pre-commit 并通过，覆盖 ruff 检查、ruff format 和 hardcoded secrets 检查。
