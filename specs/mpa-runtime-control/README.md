# MPA Runtime Control

- Component ID: `mpa-runtime-control`
- Status: `draft`; S1, S2, S3, S4, S5-01, S5-01a, S5-04, and the S5-08 Session creation fix are implemented; S5-06 and S5-07 no-impact records are captured; remaining S5 contracts remain target behavior
- Revised: 2026-09-18
- Chinese: [README.zh.md](README.zh.md)
- PRD: [MPA AgentKit P0 Functional Migration](../../prd-spec/features/mpa-p0-productionization/2026-09-15-mpa-p0-productionization-design.md)
- Owning code: Agent, Session, A2A, worker, authorization, and diagnostics modules in `agentkit-mpa-agent`

## Responsibility and authority

AgentKit Studio owns the MPA authoring entry and platform Skill, Tool, Environment, Vault, and other resources. P0 does not use Managed Agent CRUD/version/Session. mpa-agent owns immutable executable Profile revisions, session execution configuration versions, Turn execution records, participant state, and diagnostic linkage. It does not provide templates, experts, review/install, or a separate publishing service. Studio/BFF is a client and orchestrator, not execution-state authority.

At code revision `2f5e039`, the Runtime already had Agent config revisions, Session CRUD/run/SSE/events/MCP, A2A generation/lease and pause/resume, worker interruption, health/readiness, and Runtime Console. Those were reuse points. The current P0 branch has since implemented the S1 Profile/readiness/auth foundation, the S2 Session execution-config/Profile-upgrade Runtime subset, the S3 Turn acceptance, dispatcher recovery, and refresh cursor subset, the S4-01/S4-02 participant data-model plus pause-barrier subset, the S4-03 lease-aware resume boundary, the S4-04 Runtime linked continuation API/outbox, and the S5-08 MPA Session creation initialization fix described below. Studio control wiring and final diagnostics remain later target contracts.

## CON-1: Identity and authorization

P0 uses one `RuntimePrincipal v1`: `iss`, `aud`/authorized client, `sub`, `account_id`, `workspace_id`, `agent_id`, `actions[]`, `iat`, `nbf`, `exp`, and `jti`, with 30 seconds of clock skew. Studio's OAuth/gateway middleware first validates the user bearer token and BFF forwards only that validated token. AgentKit Runtime custom JWT authorization and mpa-agent validate the same issuer discovery/JWKS signature, `kid` rotation, audience/client, and time claims. Token TTL follows the existing issuer policy and M0 records the observed value; BFF neither self-signs nor assumes five minutes. Current authorization/revocation is checked before each side effect through the injectable `RuntimePrincipalAuthorizer` seam. Browser owner/account headers are never trusted, and Runtime key-auth is not an end-user identity.

REST uses `Authorization: Bearer <runtime-assertion>`. A2A uses `X-Ve-TIP-Token`, but its verifier must map the token into the same `RuntimePrincipal` instead of retaining only `sub`. Existing `X-Jwt-Token` is a legacy-capability path: callers without v1 scope claims may read legacy resources but cannot call new Profile, execution-config, run, or continue writes. `DISABLE_JWT_AUTH` is local-test-only; enabling it in AgentKit mode makes execution readiness fail.

When `MPA_AGENTKIT_MODE=true`, legacy ADK endpoints that still depend on `require_auth`, including `GET /list-apps`, authenticate from the same AgentKit `Authorization` Runtime principal instead of independently requiring `X-Jwt-Token`. This is an adapter compatibility rule, not a second identity mechanism. Outside AgentKit mode, the existing `X-Jwt-Token` contract remains unchanged. Missing or invalid AgentKit credentials fail closed in either the direct Runtime route or Studio BFF proxy path.

Check relevant scope before Profile apply, Session create/read, execution-config mutation, Turn acceptance, resume/continue, secret resolution, and external tool dispatch. The implemented S4-06 subset persists only a normalized non-secret `RuntimePrincipal` snapshot in accepted Turn dispatch payloads and inbox metadata so background execution and restart recovery can recheck grants without storing bearer tokens. Revocation blocks later effects; already dispatched external effects are not claimed undone. Ordinary responses, logs, traces, errors, and diagnostics contain no secret values. The implemented S5-01a subset registers legacy plaintext secret literals discovered during secret-reference migration in a process-local redaction registry, then redacts those exact values across API access logs, client-visible Session output/events, Runtime Console responses, lifecycle details, and trace-step persistence. This value-aware redaction intentionally preserves non-secret business handles such as `flow_id` and `user_code`.

## CON-2: Studio MPA Profile execution projection

`PUT /api/v1/agents/{mpaInstanceId}/profile` follows the existing runtime instance identity and accepts only a Profile validated and normalized by BFF from an accepted Studio draft. The request carries `sourceProfileId`, digest, name/description/system/model/tools/skills/MCP/Multiagent, and allowlisted metadata. BFF does not allocate a revision; Runtime allocates and returns the unique `profileRevision` inside the successful CAS transaction. First apply must carry `If-None-Match: *`; later apply must carry `If-Match: "<runtimeRevision>"`. Supplying both returns `400 invalid_precondition`; supplying neither returns `428 precondition_required`. Successful apply/status responses carry a strong ETag.

Runtime maps the Profile to a new `mpa_agents` revision and stores source Profile ID/digest plus apply state. Same operation key/digest returns the prior allocated revision; stale ETag returns `412 profile_changed`; replaying one allocated revision with different content returns `409 profile_version_conflict`; unknown Tool/Skill/Multiagent shapes return `422 unsupported_profile_field`. `GET /api/v1/agents/{mpaInstanceId}/profile-status` returns `pending|applying|applied|failed`, target/applied revisions, runtime revision, operation ID, safe error, and retryability.

## CON-3: Session execution configuration version

A “session execution configuration version” is a monotonically revisioned record of one Session's execution choices, not a platform-resource copy. It combines a pinned MPA Profile revision with Session overrides and stores only IDs, explicit versions or digests, model override, permission revision, invalid references, and timestamps for Skill/Tool/MCP/Environment/Knowledge/Vault resources. AgentKit still owns resource bodies and secrets.

The runtime persistence contract is append-only. `session_execution_configs` is keyed by `(app_name, session_id, revision)` and stores strong `etag`, `mpa_instance_id`, `profile_revision`, `profile_default_revision`, JSON `overrides`, JSON `effective_refs`, JSON `invalid_refs`, `updated_by`, `created_at`, and `updated_at`. Current reads use `(app_name, session_id, revision DESC)`. SQL writes serialize one Session's revision stream with a PostgreSQL advisory transaction lock, then compare the supplied ETag and append revision N+1; existing rows are never updated in place.

`POST /api/v1/sessions` initializes the first execution-config revision when the request carries `mpaInstanceId + profileRevision` and does not explicitly carry `executionConfigRevision`. The response then returns `executionConfigRevision=1`, so Studio can immediately pass a valid version into the first MPA `/run`. If a recovery or migration caller explicitly supplies `executionConfigRevision`, the Runtime preserves that value.

`GET /api/v1/sessions/{sessionId}/execution-config` returns a revision and strong ETag. `PATCH` requires `If-Match` and applies category-level replace, clear, or inherit. A match atomically creates the next revision; a missing precondition returns `428`; a conflict returns `412 execution_config_changed` with the safe current revision; validation failure creates no revision. Changes affect the next Turn only and never mutate an active Turn. `POST /api/v1/sessions/{sessionId}/profile-upgrade` carries `targetProfileRevision`, the same ETag, and `Idempotency-Key`; the target Profile must already be applied. It may be submitted while a Turn is active but affects only the next Turn. Downgrade returns `409 downgrade_not_allowed`; concurrent change returns `412`.

The implemented S2-03 subset supports `model` and `mcpServers` category changes. Unsupported categories return `422 unsupported_execution_config_category` until the corresponding AgentKit resource resolver exists. Unknown MCP IDs return `422 resource_unavailable` and do not create a revision. Non-MPA Sessions that do not carry `mpaInstanceId + profileRevision` return `404 execution_config_not_found` instead of implicitly creating MPA state.

The implemented S2-05 profile-upgrade subset exposes `POST /api/v1/sessions/{sessionId}/profile-upgrade`. It requires `Idempotency-Key` and the current execution-config `If-Match`, accepts only a higher applied `targetProfileRevision`, preserves explicit overrides, and recomputes inherited defaults from the target Profile. The schema-version-8 SQL `runtime_operations` ledger persists the request hash and safe result, so same-key/same-target retries replay across Runtime processes; same-key/different-target returns `409 idempotency_mismatch`.

Before a Turn is accepted, the Runtime resolves the selected execution-config revision into an immutable `SessionExecutionConfigSnapshot`. The snapshot includes the accepted revision and ETag, MPA instance, Profile revision, Profile-default revision, overrides, effective references, invalid references, and accepted timestamp. It is a value object used by Turn acceptance and trace linkage; it is not a second mutable configuration record.

Example: Session revision 6 uses Skill `s-1@3`. Client A changes the model to M2 and creates revision 7. Client B tries a Skill update with ETag 6 and receives 412. The running Turn continues with revision 6; a later Turn uses revision 7.

## CON-4: Turn acceptance and idempotency

`POST /api/v1/sessions/{sessionId}/run` explicitly accepts `executionConfigVersion` and `Idempotency-Key`. The A2A Agent Card advertises `urn:veadk:mpa:execution:v1`; `params.metadata.veadkExecution` carries the same fields. Legacy A2A calls without the extension may use only the default revision and no Session overrides. Runtime resolves resource versions outside the transaction, then atomically compares Session/permission versions, claims the active Turn, writes immutable `turn_execution_records` and a dispatch intent, and only then triggers external execution. Materialization rechecks version/digest and permission; drift fails before side effects.

Run idempotency is scoped by `user_id + app_name + session_id + source + Idempotency-Key`, uniquely enforced by `turn_execution_records`, and retained with canonical request hash, frozen config snapshot, `accepted|dispatching|succeeded|failed_retryable|failed_terminal`, and durable `turnId/invocationId/operationId` values. Same key/hash returns the original accepted invocation; same key/different payload returns `409 idempotency_mismatch`. A pending Profile never becomes the current `mpa_agents` revision; only the success transaction switches the applied revision. Crash recovery reuses the dispatch key and cannot create a second Turn.

The implemented S3 subset uses `turn_execution_records` as the durable run-acceptance ledger. REST `/run` requires the idempotency key and requested execution-config revision for MPA Sessions, stores the frozen `SessionExecutionConfigSnapshot`, returns `turnId`, `operationId`, and `executionConfigRevision`, and preserves the legacy response shape for non-MPA Sessions. A2A accepts the same metadata through `params.metadata.veadkExecution`, binds the accepted invocation ID to the ADK request, updates dispatch status to `dispatching`, then records `succeeded` or `failed_retryable`. Replaying the same A2A key/hash returns a completed idempotent replay notice and does not execute the model again. `dispatch_payload` allows restart recovery to rebuild missing/error inbox rows without introducing a second dispatcher. Studio sends the last completed event ID back to Runtime SSE so browser refresh resumes after the cursor rather than replaying from the beginning.

## CON-5: Whole-Turn lifecycle and continuation

The state machine is `queued -> running -> pausing -> paused -> resuming -> running -> completed|failed|cancelled`. `a2a_task_controls` retains aggregate generation. Every active primary executor/worker registers lease, state, safe point, and checkpoint in `a2a_turn_participants`. The Turn becomes `paused` only after all active participants acknowledge the same generation; partial acknowledgement remains `pausing` or ends in a classified timeout.

The implemented S4-02 subset wires pause requests through `ParticipantBarrierService` when `a2a_turn_participants` is available. A pause command advances the aggregate task generation and copies active participants from the previous generation. A participant ACK only affects its own row; the service calls task-level `acknowledge_safe_point` only after all current-generation active participants are `paused` or terminal. ACKs for old generations or wrong owners are ignored. A Codex worker that starts after the aggregate task is already `paused` still registers in the current generation, receives a worker pause command, acknowledges the same generation, and waits for resume. Completed, failed, or cancelled worker turns mark their participant row terminal so later pause generations do not wait for an already-ended worker. When resume is acknowledged, the Runtime seeds the next running participant generation from the previous paused generation.

Resume rechecks authorization and participant viability. The implemented S4-03 boundary resumes the same business Turn only when the task is paused for no more than 300 seconds, the task owner lease is still viable, and the participant generation has no `lost|failed` participant or still-running participant with an expired/missing lease. A still-running participant with a valid lease makes resume return `409 invalid_state` so the caller waits for the safe point; it is not converted into continuation. Past 300 seconds, after owner lease loss, after participant loss/failure, or after an unrecoverable restart, resume returns `new_turn_required`. The `new_turn_required` transition records the resume idempotency key and replays safely for the same key.

Only explicit user action calls `POST /api/v1/a2a/tasks/{taskId}/continue`. The implemented S4-04 Runtime API requires `Idempotency-Key` and `expectedGeneration`, accepts only `interrupted|orphaned` control states, resolves the previous business Turn from the old task invocation, and inserts a linked `turn_execution_records` row with `continuation_of=<oldTurnId>`. The continuation reuses the frozen execution-config snapshot and dispatch payload, closes the old active dispatch row, and schedules the existing inbox/outbox worker with `enqueue_once`. Same-key/same-request calls replay the same continuation; same-key/different-request calls return `idempotency_mismatch`. The contract does not promise distributed ACID with the SDK `DatabaseTaskStore`; the existing outbox recovers accepted continuation dispatches. Studio no longer constructs a prompt and calls ordinary send once S4-05 is wired.

## CON-6: Events, refresh, and diagnostics

SSE replay reuses persistent ADK Session events plus the inbox terminal fence. The in-memory StreamHub is only the low-latency live path and is not refresh authority. The cursor is a persistent event ID; the server replays in persisted Session-event order and then joins the live stream. An unknown non-empty cursor returns `410 cursor_expired` instead of silently replaying from the beginning. Event/invocation/type identity prevents duplicate text, usage, or artifacts; a missing terminal remains unknown/failed rather than success.

Runtime Console/trace reuses existing stores and adds indexed MPA instance, Profile revision, session execution-config revision, Turn, and worker run/session linkage. Details are redacted and bounded; core correlation does not depend on parsing arbitrary JSON. The implemented S5-04 slice exposes a normalized `correlation` object on invocation trace responses and each trace step, extracting MPA instance, Profile revision, execution-config revision/ETag, business Turn, A2A task, Runtime ID/version, and Codex/subagent worker session/turn/profile identifiers from already-redacted detail payloads.

Execution configuration and event persistence serve only the mpa-agent business Session. P0 does not create an AgentKit Managed Agent Session or maintain dual Session IDs. AgentKit `AgentWithOverrides` remains a recorded platform capability outside this contract.

## CON-7: APIs and errors

| API | Status | Contract |
| --- | --- | --- |
| `PUT /api/v1/agents/{mpaInstanceId}/profile` | new | Always requires `Idempotency-Key`; first apply uses only `If-None-Match: *`, later apply only `If-Match: "<runtimeRevision>"`, mutually exclusive; payload carries Studio Profile source ID/digest and Runtime allocates the revision |
| `GET /api/v1/agents/{mpaInstanceId}/profile-status` | new | Profile apply status and recoverable operation |
| `GET /api/v1/sessions/{sessionId}/execution-config` | new | Authoritative session execution-config version and ETag |
| `PATCH /api/v1/sessions/{sessionId}/execution-config` | new | CAS update affecting the next Turn |
| `POST /api/v1/sessions/{sessionId}/profile-upgrade` | new | Explicit Session Profile upgrade; target Profile must be applied |
| `POST /api/v1/sessions/{sessionId}/run` | extend | Add `executionConfigVersion` and durable idempotency |
| A2A submission | extend | `urn:veadk:mpa:execution:v1` extension uses the same Turn-acceptance service |
| `GET/POST /api/v1/a2a/tasks/{taskId}/control...` | extend | Preserve URLs; add participant aggregation and request-hash idempotency |
| `POST /api/v1/a2a/tasks/{taskId}/continue` | new | Runtime-owned linked continuation |
| `GET /api/v1/runtime-operations/{operationId}` | new | Principal/target-authorized async status and safe replay result for Profile/run/upgrade/continue |
| Session CRUD/SSE/events/MCP/health/readiness/console | reuse | Add scope, cursor, and correlation fields |

New APIs use `error.code/message/requestId/retryable/currentState`. Existing clients retain their current envelope until a capability-version negotiation permits change. Old Runtime versions stay discoverable as read-only/unsupported; AgentKit P0 cannot disable authorization or fall back to browser/ArkClaw authority.

## CON-8: Data model

| Model | Proposed change |
| --- | --- |
| `mpa_agents` | Add source Profile ID/digest, apply status/operation/error, `agent_api_key_ref`, `model_api_key_ref`, `secret_migration_status`, and `secret_migration_operation_id`; existing Runtime-assigned revision is the sole `profileRevision` |
| `mpa_meta` | Add AgentKit mode, workspace, bootstrap revision, readiness phase, finalization operation, last error |
| `session_meta` | Add account/workspace/MPA-instance/Profile/execution-config revision |
| `session_execution_configs` | New append-only table for `(app_name, session_id, revision)`, strong ETag, MPA instance, Profile revision, Profile-default revision, overrides/effective/invalid references, updater, and timestamps |
| `turn_execution_records` | New table for accepted config, resolved refs, model/policy/secret refs, dispatch key/hash/status, and `continuation_of` |
| `a2a_turn_participants` | New table for each generation's participants, lease, safe point, checkpoint, ACK, and terminal times |
| `a2a_task_controls` | Add command request hash/result reference; add approval fields only when a real P0 high-risk tool flow needs them |
| `runtime_operations` | New table for Profile lifecycle and future long-running control operations: unique principal/operation/target/key, request hash, state, response snapshot, resource IDs, expiry. Run acceptance uses `turn_execution_records`; execution-config PATCH uses revision/ETag; pause/resume uses `a2a_task_controls`, without duplicate ledger writes |
| Trace/lifecycle | Add indexed task/config/runtime/worker references where needed |

Do not add Agent definition/version, template/expert, review/install, independent continuation, or generic policy-evaluation tables. The implemented S5-01 slice adds `agent_api_key_ref`, `model_api_key_ref`, `secret_migration_status`, and `secret_migration_operation_id` to `mpa_agents`. AgentKit mode rejects new writes to the existing plaintext `agent_api_key` and `model_api_key` columns. Existing new-platform values are migrated reference-first: the external secret reference is created with a stable idempotency key before the Runtime clears plaintext in one database transaction. Failure before the database update retains plaintext so retry remains possible; successful migration clears plaintext for the MPA agent rows and keeps only references. Runtime execution resolves `agentApiKeyRef`/`modelApiKeyRef` only at secret-use boundaries and fails closed if no resolver is configured. S5-01a adds process-local value-aware redaction for the legacy plaintext values read during migration and for future registered secret literals. Registered literals are redacted inside nested values and free text before API/log/Runtime Console/trace exposure, while non-secret references and business parameters remain visible. Runtime operation response/resource snapshots use that same redaction boundary, and the status API omits principal, idempotency key, and request hash. Legacy mode retains read-only plaintext compatibility for one version and removes the plaintext read path in the next major version. Structural changes use an explicit ordered migration; SQL and in-memory stores stay aligned. AgentKit-owned tables are not extended and ArkClaw data is not migrated.

Migration order is `runtime_operations -> additive mpa_agents/mpa_meta/session_meta columns -> session_execution_configs -> turn_execution_records -> a2a_turn_participants -> indexes/constraints`, with a schema version after every step. Expand schema first, deploy dual-version-readable code second, and enable new writes last; reject rollback when an older image cannot read the state safely.

## CON-9: Performance and retention

- Profile apply, run, pause/resume/continue acceptance: p95 <= 500 ms; asynchronous completion uses operation/status lookup.
- execution-config GET/PATCH: p95 <= 300 ms; remote resource lookup holds no database lock.
- first SSE event on a warm Runtime: p95 <= 2 s, excluding model first-token SLA.
- list/detail: p95 <= 1 s, default 20/max 100, with no N+1 platform scan.
- Idempotency results are retained at least 24 hours; terminal execution evidence defaults to 30 days; active Sessions and referenced configuration versions do not expire automatically. Production retention is explicitly configured.

## Verification

Implementation follows TDD: add Profile mapping/version/idempotency, execution-config CAS, run crash recovery, multi-participant barrier, continuation, SSE replay, scope, and redaction tests before implementation. Add a real PostgreSQL two-connection/restart lane for CAS, one active Turn, outbox, migration, and dual-version reads; in-memory stores are not final evidence for these guarantees. Runtime baseline command:

```bash
uv run --group dev pytest \
  tests/test_session_auth.py \
  tests/test_subagent_binding_store.py \
  tests/test_a2a_task_control.py \
  tests/test_turn_control_api.py \
  tests/test_codex_adapter.py
```

This command is required during implementation and is `not_run` for this documentation-only change. Real integration must cover Profile apply, two-client CAS, failure retry, multi-worker pause/resume, the 300-second boundary, replay, and revocation.

## Confirmed product decisions

The user confirmed on 2026-09-15 that an existing Session pins its creation-time MPA Profile revision and uses a newer revision from the next Turn only after a successful explicit upgrade; an active Turn never switches. After Studio accepts MPA creation, the UI shows deploying and reports runnable only after Runtime, Profile application, and execution-ready smoke all pass. Both are P0 acceptance constraints.

## Change record

2026-09-15: Removed Managed Agent and duplicate template/expert/version products; established Studio authoring authority, Runtime Profile-revision authority, and explicit execution-config, API, idempotency, state-machine, data-model, and verification contracts.

2026-09-15: Implemented the execution-config storage/API foundation in `agentkit-mpa-agent`: `session_execution_configs` schema version 4, append-only store, per-session PostgreSQL advisory lock for CAS, `GET/PATCH /api/v1/sessions/{sessionId}/execution-config`, and the P0 `model`/`mcpServers` patch subset.

2026-09-15: Added immutable `SessionExecutionConfigSnapshot` as the handoff value for future Turn acceptance.

2026-09-15: Implemented the explicit Session Profile upgrade API/service subset for higher applied MPA Profile revisions, including ETag/CAS, downgrade rejection, unavailable-target rejection, override preservation, and current-process idempotent replay.

2026-09-15: Verified the implemented S2 Runtime subset with `uv run pytest -q tests/test_session_execution_config.py tests/test_session_execution_config_service.py tests/test_agentkit_session_auth.py tests/test_agent_config_service_unit.py tests/test_agent_config_store.py tests/test_profile_apply.py tests/test_profile_apply_api.py tests/test_sessions.py::test_create_get_include_mpa_profile_pointers_when_supplied tests/test_session_mcp_update.py` (46 passed), focused Ruff, `make test-postgres` (5 passed), and pre-documentation `git diff --check`.

2026-09-16: Implemented `turn_execution_records` schema version 5, SQL/in-memory acceptance store, REST `/run` MPA idempotency and config-version enforcement, A2A execution metadata acceptance, dispatch status progression, and Studio/BFF run metadata forwarding. Verification covered Runtime focused S3 regression (64 passed), Runtime Ruff, Runtime `make test-postgres` (6 passed), VeADK MPA server/integration pytest (47 passed), BFF bridge pytest (3 passed), frontend focused source-contract tests (14 passed), full frontend tests (1212 passed), i18n, build, and two-repository diff hygiene.

2026-09-16: Implemented the accepted-turn recovery portion of S3-03. `turn_execution_records` now persists `dispatch_payload`, `SessionService.initialize()` rehydrates missing/error inbox rows from active or retryable Turn records and schedules normal workers, already-terminal inboxes synchronize back to Turn status, and lease-expired inbox rows mark linked Turns `failed_retryable`. Verification covered Runtime S3 regression (72 passed), Runtime Ruff, Runtime `make test-postgres` (6 passed), and diff hygiene.

2026-09-16: Implemented S3-04/S3-05/S3-06 refresh recovery. Runtime SSE rejects unknown non-empty cursors with `410 cursor_expired`; Studio restores persisted Runtime Agent and Session IDs after browser refresh, hydrates the selected Session, and sends `lastEventId` into MPA Runtime `/sse`. Real-browser `BC-06` passed with system Google Chrome via Playwright; evidence is under `evidence/browser/mpa-s3-1789516481/BC-06/`.

2026-09-16: Implemented S4-01 participant state foundation. Runtime now has `a2a_turn_participants` schema version 6 plus SQL/in-memory stores for per-generation participant registration, owner-scoped lease heartbeat, generation-checked safe-point ACK, terminal marking, and ordered generation snapshots.

2026-09-16: Implemented the S4-02 participant pause-barrier subset. Runtime pause requests now copy the current active participant set, A2A primary and Codex worker safe-point ACKs aggregate through `ParticipantBarrierService`, partial ACK remains `pausing`, all current-generation active participants advance the task to `paused`, late paused-generation workers receive pause before resume, terminal workers stop blocking future pauses, and resume seeds the next running generation. Verification covered Runtime S4-02 focused regression (27 passed), focused Ruff, and Runtime `make test-postgres` (7 passed).

2026-09-16: Implemented the S4-03 lease-aware resume boundary. Runtime now returns same-Turn resume only inside the 300-second paused window when the owner lease remains viable and participant state is resumable. It returns `new_turn_required` for pause age greater than 300 seconds, owner lease loss, participant `lost|failed`, or expired/missing running participant lease, and records the resume key for idempotent replay. A valid still-running participant blocks resume with `invalid_state` until it ACKs or expires. Verification covered S4-03 focused boundary tests (8 passed), broader S4 control regression (104 passed), focused Ruff, and Runtime `make test-postgres` (7 passed).

2026-09-16: Implemented the S4-04 Runtime-owned linked continuation API/outbox. Runtime now accepts `POST /api/v1/a2a/tasks/{taskId}/continue` after `new_turn_required`, writes a linked `turn_execution_records` row through `accept_continuation`, reuses the frozen snapshot and dispatch payload, terminates the old active dispatch row, and schedules the existing inbox worker. Verification covered S4-04 focused tests (4 passed), broader S4 control/acceptance regression (125 passed), focused Ruff, and Runtime `make test-postgres` (8 passed).

2026-09-16: Implemented the S4-06 RuntimePrincipal revocation and side-effect recheck subset. Runtime now exposes shared authorization helpers plus an injectable authorizer seam; `/run`, resume, and `/continue` recheck the current grant before accepting side effects. Accepted Turn/inbox records carry a non-secret principal snapshot for background execution and restart recovery. ADK before-tool callbacks, direct sandbox dispatch, model/workload TIP resolution, OpenViking API-key resolution, and sandbox `begin_run` all recheck before using a secret or external tool effect. Verification covered S4-06 focused auth/secret/tool tests (46 passed), broader S4 Runtime regression (206 passed), and focused Ruff. Real AgentKit revocation lookup remains a deployed S5 release gate.

2026-09-16: Closed the S4-07 lifecycle/PostgreSQL/browser gate. Runtime focused auth/secret/tool tests returned 46 passed, and `make test-postgres` returned 8 passed with PostgreSQL resources cleaned. The VeADK loopback `turn_lifecycle` scenario now exercises Session/task control status, pause/resume, `new_turn_required`, explicit `/continue`, continuation SSE, call counts, and persisted state evidence. Real-browser `BC-09` passed with system Google Chrome via Playwright; evidence is under `evidence/browser/mpa-s4-1789532050/BC-09/`.

2026-09-16: Implemented the S5-01 secret-reference migration foundation. Runtime schema version 7 adds secret reference and migration status columns to `mpa_agents`. `AgentConfigService` rejects new plaintext `agentApiKey`/`modelApiKey` writes in AgentKit mode while accepting reference fields. `SecretReferenceMigrationService` creates protected references before clearing plaintext, preserves plaintext when the provider or database update fails, and is retryable with the same idempotency key. Runtime model and built-in MCP paths can resolve references at execution-time secret-use boundaries; missing resolvers fail closed instead of falling back to another credential.

2026-09-16: Implemented the S5-01a canary-safe redaction subset. Secret-reference migration registers legacy plaintext values for value-aware redaction before external reference creation. API access logs, Session visible text/events, Runtime Console responses, lifecycle details, and trace-step persistence redact registered canary literals even under non-sensitive keys, while preserving `flow_id` and `user_code`. Verification covered focused S5 redaction pytest (89 passed), broader S5 Runtime regression (178 passed), focused Ruff, and `make test-postgres` (9 passed).

2026-09-16: Implemented the S5-04 Runtime Console/Trace correlation subset. Invocation trace responses and individual trace steps now expose stable `correlation` fields for MPA instance, Profile/config revisions, Turn/task/runtime identity, and worker linkage. Verification covered Runtime Console/Trace pytest (72 passed) and focused Ruff.

2026-09-16: S5-06 compatibility preflight is a Studio/VeADK write-path guard and does not change the `agentkit-mpa-agent` Runtime API or database schema. The Runtime contract remains the already implemented Profile, Session execution-config, Turn acceptance, lifecycle, secret-reference, and diagnostics contracts above; final release evidence still depends on the pinned cross-repository manifest in VC-19.

2026-09-16: S5-07 delete preview and staged cleanup is also a Studio/VeADK orchestration slice and does not require a new `agentkit-mpa-agent` table or endpoint. Studio reuses Runtime `GET /api/v1/agents/{mpaInstanceId}/profile-status`, `GET /api/v1/sessions?include_a2a=true`, and `DELETE /api/v1/sessions/{sessionId}` before calling the AgentKit Runtime delete API. Studio treats `queued|running|pausing|paused|resuming` Sessions as active blockers and treats per-session delete `404` as already cleaned for retry safety. The current contract can only prove the sessions visible through the authorized target Runtime API; a future cross-user global active-session guarantee would require a separate Runtime/global admin API and is not claimed by S5-07.

2026-09-17: Implemented the S5-08 MPA Session creation initialization fix. Runtime now creates the first `session_execution_configs` revision during `POST /api/v1/sessions` when Studio supplies `mpaInstanceId + profileRevision` and omits an explicit `executionConfigRevision`, then returns `executionConfigRevision=1` in the create response. Explicit caller-supplied revisions remain preserved for migration/recovery callers. Verification covered focused Runtime tests (186 passed), focused Ruff, and a released Runtime image `agentkit-platform-2112682748-cn-beijing.cr.volces.com/agentkit/mpa_agent:mpa-p0-sessioncfg-init-local-20260917` on Runtime `r-yeuujrrcowb21078p9jh` version 58. Live BFF/runtime checks showed native Session create returning revision 1, `/run` accepting `executionConfigVersion=1`, and `/sse` emitting final text plus `event: done`.

2026-09-17: Implemented schema version 8 and completed the durable Runtime operation/Profile CAS contract. SQL and in-memory operation stores now enforce the same 24-hour identity/replay policy, persist redacted safe results, and compare-and-swap state transitions. Profile apply uses the authenticated principal and full normalized payload hash, maps all P0 Profile resource categories, and performs ETag validation plus current-revision switching in one PostgreSQL transaction. A real two-connection contract proves that only one concurrent writer can consume a given ETag.

2026-09-18: Aligned legacy ADK endpoint authentication with AgentKit key-auth in Runtime commit `eecc6e3`. In AgentKit mode, `require_auth` now derives the Runtime principal from `Authorization`; outside AgentKit mode it retains the existing `X-Jwt-Token` behavior. Focused tests returned 49 passed, full `make test` returned 2506 passed and 14 skipped, and focused Ruff plus diff hygiene passed. The resulting image `agentkit-platform-2112682748-cn-beijing.cr.volces.com/agentkit/mpa_agent:mpa-p0-adk-auth-eecc6e3-20260917` (`sha256:6ac6a2712ecd1c7950125dc9afc6467373a08142fbd6c3577aba12f126079bef`) is deployed as Runtime `r-yeuujrrcowb21078p9jh` version 62 and is `Ready`; direct and Studio BFF `/list-apps` calls both returned `200 ["default"]`. No Runtime schema or persisted model changed.

2026-09-18: Live Studio acceptance against Runtime version 62 created Session `bee3db38-edcc-4020-b925-3d9d6a3a7adc` and executed `printf 'MPA_V62_BROWSER_OK\n'` in the sandbox. The parent sandbox activity and child command activity both reached `completed`; the final answer remained visible at completion and after 30 seconds, and a full refresh restored the answer and terminal tool cards with no spinner or running text. Evidence is under `evidence/browser/mpa-v62-live/`. This validates the exercised chat-display path only and does not close the full S5-12 `BC-01`–`BC-09` gate.
