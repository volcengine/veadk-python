# Managed Agent resource adapters

[中文版](README.zh.md)

Component ID: `managed-agent-resources`. Status: `active`. Revised: 2026-10-10.
Related approved PRD: [managed-agents-upstream](../../prd-spec/features/managed-agents-upstream/2026-10-10-non-ui-migration.md), `FR-3`, `FR-4`, `T-2`, `AC-2`.
Dependent component: [managed-agent-runtime](../managed-agent-runtime/README.md).

## Scope and structure

Migrate the source backend changes without copying frontend or Studio APIs. Ark
request behavior remains in `veadk/models/ark_llm.py`; credential API requests stay
in `veadk/integrations/ve_identity/identity_client.py`; the standalone Managed
Agents skills transport lives in `veadk/skills/ma_infra.py`. Runtime credential
resolution belongs to the runtime adapter, which calls IdentityClient rather
than embedding a second SDK client. Existing upstream workload/user-pool helpers
and default environment handling remain intact.

## Behavioral contract

- `CON-1`: Ark continuation requests preserve currently authorized tool declarations;
  absence of tools does not imply any additional authorization.
- `CON-2`: Default request construction does not inject a one-hour `expire_at`. Explicit
  caller retention is preserved; otherwise the remote service chooses retention.
- `CON-3`: `retry_expired_response` defaults to the existing replay behavior. A managed
  runtime can disable replay to prevent silently discarding prior conversation.
- `CON-4`: `MANAGED_AGENT_MODEL_TRACE=true` enables a dedicated metadata-only JSON trace:
  model/tool names, tool selection, presence of a continuation, and event/output
  types. Prompts, responses, API keys, tool arguments and continuation IDs are
  excluded. Tracing is disabled by default.
- `CON-5`: IdentityClient accepts optional `pool_name` for API-key resolution; omission
  preserves the SDK default. Credentials remain in process memory.
- `CON-6`: The skills client uses the configured `/v1/skills` endpoint, account header and
  API-key header. It exposes synchronous operations and thread-backed asynchronous
  counterparts. Pagination metadata remains available; `latest` resolves to a
  concrete version before downloading content. Archives exceeding 32 MiB fail.
- `CON-7`: HTTP and service errors become typed skills errors with status, code and retry
  classification. Multipart publishing lets the HTTP library set its boundary.

## Entry points, configuration and state

Public imports are `veadk.models.ark_llm.ArkLlm`,
`veadk.integrations.ve_identity.identity_client.IdentityClient`, and
`veadk.skills.ma_infra.{MaInfraSkillConfig,MaInfraSkillsClient,MaInfraSkillError}`.
Ark calls its existing SDK Responses API; IdentityClient calls the Identity SDK
`get_resource_api_key`. For example, `client.get_api_key(provider_name="model",
agent_identity_token=token, pool_name="customer")` selects that credential pool.
The credentials remain runtime values, never serialized to this document.

`MaInfraSkillConfig.from_env()` reads `MA_SKILLS_BASE_URL`, `MA_SKILLS_API_KEY`,
and `MA_SKILLS_ACCOUNT_ID`; an absent base URL disables configuration by
returning `None`. Explicit configuration takes precedence by being passed directly
to the client. Default timeout is 30 seconds; redirects are disabled. Calls cover
GET/POST `/v1/skills`, GET/DELETE `/v1/skills/{id}`, and GET/POST versions/content
beneath that skill. The control plane owns authorization and registry state.
The client owns no local persistent cache, version migration, deduplication or
automatic mutation retries. Callers must `close()` the synchronous HTTP client.
Async methods use `asyncio.to_thread`; cancelling the awaiting coroutine does not
interrupt an in-flight synchronous HTTP request, which remains timeout bounded.

## Security, compatibility and failures

Skills requests attach only the configured API-key and account headers. External
resource identifiers and archive bytes are passed to the control plane; downloads
are returned as bytes and this component does not extract archives. Runtime Skill
extraction and temporary-directory cleanup belong to the dependent runtime.
Only whitelisted Ark trace metadata is emitted. SDK/service failure behavior and
caller-owned credentials remain unchanged; no credential is logged by the new
Identity pool forwarding. Typed skills errors expose `status_code`, `code`, and
`retryable`: network errors map to retryable 502; 429 and 5xx are retryable, other
HTTP errors are not. Server error text is returned to callers; it is not logged
by the skills client. The 32 MiB download cap is checked after transfer; upload
size enforcement belongs to the service.

Python 3.10-3.13 remains supported. Existing Identity calls omit `pool_name` and
preserve the service default. Ark replay remains enabled by default; runtime
callers explicitly disable it when full history cannot be replayed. No schema or
SDK pin changes are required by these resource adapters.

## Acceptance

Local tests cover continuation tool preservation, retention defaults and explicit
values, expired-context fail-fast behavior, trace field redaction, Identity pool
forwarding, skills headers/pagination/version pinning/error handling and async
helpers. No real cloud mutation or credential-bearing configuration is needed.

## Local verification record

On 2026-10-10, `pytest tests/models tests/skills
tests/test_ve_identity_api_key.py tests/integrations/test_mpa_identity.py -q`
passed **109 tests** against the target tree. New regression tests first failed
on the official baseline for tool removal, expiration override and missing pool
scope. Ruff 0.11.12 lint and formatting passed for the changed component files.
This is offline protocol/model coverage; live Identity and skills services were
not invoked.

Contract-to-test mapping: `CON-1`/`CON-2` use model context/expire-at tests;
`CON-3`/`CON-4` use model fallback/trace tests; `CON-5` uses
`tests/test_ve_identity_api_key.py`; `CON-6`/`CON-7` use
`tests/skills/test_ma_infra_skills_client.py`. Negative cases include absent
configuration/tools, expiration, oversized archives and service/network failures.
The 2026-10-10 migration changes only these contracts; no unresolved resource
contract questions remain. Cloud E2E and actual registry mutation remain outside
local acceptance.

Minimum-version verification: Python **3.10.20**, an isolated environment created
with `uv sync --frozen --python 3.10 --extra sandbox --extra extensions --extra dev`,
Anthropic **1.3.0**, Google ADK **2.2.0**. The focused runtime, MPA Session, model,
Skills, Identity and Feishu suites passed **356 tests** (17 deprecation warnings,
24.24 seconds). The new real-SDK transient-event transport regression also passed
individually. A Python 3.10 SDK GenericAlias response-cast incompatibility was
resolved with `typing.Dict` in the transient publisher and transport tests; no
dependency pin or target environment change was necessary. This verifies local
protocol behavior, not remote cloud deployment.
