# OpenViking Knowledge + Memory

This example uses OpenViking for both VeADK knowledge base retrieval and
long-term memory. OpenViking handles indexing and memory extraction remotely, so
you do not need `MODEL_EMBEDDING_*` settings.

> 中文版见 [README.zh.md](./README.zh.md)

## Setup

```bash
cd examples/13_openviking
cp .env.example .env
```

Fill in:

```bash
MODEL_AGENT_API_KEY=...
DATABASE_OPENVIKING_URL=http://127.0.0.1:1933
DATABASE_OPENVIKING_API_KEY=...
DATABASE_OPENVIKING_USER_ID=openviking_demo
```

`DATABASE_OPENVIKING_USER_ID` is the OpenViking owner/context id used in
`viking://user/<user_id>/...`. Keep it stable for one agent/application context
so resources and memories stay isolated.

## Run

```bash
python main.py
```

The script imports `docs/company_faq.md` into:

```text
viking://user/{DATABASE_OPENVIKING_USER_ID or default}/resources/company_faq/
```

Then it runs two sessions. Session 1 answers with the knowledge base and stores
a user preference. Session 2 asks the agent to recall that preference via
OpenViking long-term memory and answer another policy question.

## Configuration patterns

### Recommended: `.env` or `config.yaml`

The example keeps OpenViking connection settings out of code:

```python
knowledgebase = KnowledgeBase(backend="openviking", index="company_faq")
long_term_memory = LongTermMemory(backend="openviking", app_name=APP_NAME)
```

VeADK reads these settings from `.env`, system environment variables, or the
equivalent `config.yaml` structure:

```yaml
database:
  openviking:
    url: http://127.0.0.1:1933
    api_key: your-openviking-api-key
    user_id: openviking_demo
```

This is the best default for deployment: secrets stay outside source code, and
the same code can run against different OpenViking services or contexts.

### `url` vs `target_uri`

There is no `target_url` parameter. OpenViking uses two different concepts:

- `url` / `DATABASE_OPENVIKING_URL`: the OpenViking HTTP service endpoint, such
  as `http://127.0.0.1:1933`.
- `target_uri` / `DATABASE_OPENVIKING_TARGET_URI`: the OpenViking resource
  directory for the knowledge base, such as
  `viking://user/openviking_demo/resources/company_faq/`.

`url` is required for connecting to the service. `target_uri` is optional; when
it is unset, VeADK generates the default resource directory from
`openviking_user_id` and `index`.

### URI construction rules

For `KnowledgeBase(backend="openviking")`, VeADK chooses the knowledge resource
directory like this:

1. If `target_uri` or `DATABASE_OPENVIKING_TARGET_URI` is set, VeADK uses that
   full OpenViking resource URI directly. It is not joined with
   `openviking_user_id` or `index`.
2. If `target_uri` is not set, VeADK builds:

   ```text
   viking://user/{openviking_user_id or default}/resources/{index}/
   ```

3. `openviking_user_id` is resolved from
   `backend_config["openviking_user_id"]`, then the compatibility alias
   `backend_config["user_id"]`, then `DATABASE_OPENVIKING_USER_ID`, then
   `default`.
4. `index` comes from `KnowledgeBase(index=...)` or `app_name` when
   `backend_config` is omitted. When `backend_config` is provided, include
   `backend_config["index"]`.
5. If an explicit `target_uri` starts with `viking://` but does not end with
   `/`, VeADK appends the trailing slash.

Examples:

```python
KnowledgeBase(backend="openviking", index="company_faq")
```

with `DATABASE_OPENVIKING_USER_ID=team_a` uses:

```text
viking://user/team_a/resources/company_faq/
```

But:

```python
KnowledgeBase(
    backend="openviking",
    backend_config={
        "index": "company_faq",
        "target_uri": "viking://user/shared/resources/hr",
    },
)
```

uses exactly:

```text
viking://user/shared/resources/hr/
```

### Explicit `backend_config`

Use `backend_config` when one process needs to talk to multiple OpenViking
contexts, or when a test should override environment settings:

```python
knowledgebase = KnowledgeBase(
    backend="openviking",
    backend_config={
        "index": "company_faq",
        "url": "http://127.0.0.1:1933",
        "api_key": "your-openviking-api-key",
        "openviking_user_id": "openviking_demo",
        # Optional. Use only when you want to pin an existing resource directory.
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

When `KnowledgeBase.backend_config` is provided, include `index` in that
dictionary. Without `backend_config`, `index` can come from
`KnowledgeBase(index=...)` or `app_name`.

### What each id changes

- `DATABASE_OPENVIKING_USER_ID` / `openviking_user_id` is the OpenViking
  owner/context id. It scopes both the default knowledge directory and
  long-term memory namespace.
- `Runner.user_id` is the end-user id. The OpenViking long-term-memory backend
  sends it as `peer_id`, so different end users get separate memories under the
  same owner/context.
- `KnowledgeBase.index` names the default resource directory.

Without `DATABASE_OPENVIKING_TARGET_URI`, knowledge resources go to:

```text
viking://user/{openviking_user_id or default}/resources/{index}/
```

Set `DATABASE_OPENVIKING_TARGET_URI` only when you want to use an existing or
custom OpenViking resource directory. When it is set, VeADK uses that directory
directly instead of generating one from `openviking_user_id` and `index`.

### Memory policy

You usually do not need to configure `DATABASE_OPENVIKING_MEMORY_POLICY`. Omit it
to keep VeADK's default policy. Set it only when you want to change how
OpenViking extracts self/peer memories or which memory types it stores.

## Notes

- Re-running the example imports the local docs again. For production, import
  knowledge documents as part of setup or CI instead of every request path.
- Set `DATABASE_OPENVIKING_TARGET_URI` only when you want to pin the knowledge
  base to a custom resource directory.
- Omit `DATABASE_OPENVIKING_MEMORY_POLICY` to keep VeADK's default OpenViking
  memory policy.
