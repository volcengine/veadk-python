# MPA collaborating Agents: A2A Center

[中文版](README.zh.md)

## Ownership and UI

Studio administrators manage **MPA → Collaborating Agents → A2A Center**. Select a target Runtime account/region and a space. Runtime GET/PUT `/api/v1/studio/collaborators/registry/binding` persists only one MPA-to-space association with revision CAS; registry/spaces and registry/agents query the target Runtime cloud identity. All compatible running members, including future members, can be discovered by the existing governed dispatcher. Registration acceptance alone is not proof of execution.

## Registration

POST `/web/a2a-agents?region=...` is a Studio control-plane endpoint, not a Runtime tool. It requires existing management authorization and access to targetRuntimeId. Source Runtime also authorizes runtimeId and passes RuntimeConfig with networkType public/private. Source Standard supports importType json (agentCard object) or url (cardUrl HTTPS). All requests include spaceId; source-specific fields are mutually exclusive. Studio signs CreateA2aAgent with existing server credentials and returns only `{id}`. Account/region access failures remain explicit. No new Runtime create privilege or external dependency is introduced.

Input is bounded to 128 KiB, IDs are validated, JSON requires name/url/version, URLs exclude userinfo/fragments. AgentKit fetches imported URLs; Studio does not fetch arbitrary URLs. Cards and credentials are never returned, logged, or persisted by the browser. JSON input is masked until explicitly revealed. No automatic create retry: network/5xx/cancel uncertainty requires refresh/reconciliation. A successful create followed by a failed refresh remains a successful create with a list error. Changing Runtime/region/space aborts stale UI responses and clears input; normal keyboard and IME behavior is retained.

## Legacy data and compatibility

Old local list/create/update/delete/check endpoints authenticate then return 410 `legacy_registration_retired`. Their manual form and local write/resolution service are removed. After schema migration, Runtime startup deletes only current-MPA rows from mpa_collaborating_agents, idempotently. Missing identity never deletes, missing table is a no-op. Preserve other MPAs, space associations, sessions and execution ledger. Preserve the shared collaborator_credential_key for rolling-upgrade safety. Published migrations and table structure remain unchanged. Deletion requires an existing DB backup for rollback; binary rollback cannot restore deleted rows. Current implementation does not deploy or delete live records until the upgraded Runtime starts.

## Existing dispatch safety

Model tools accept IDs resolved from the bound space, never arbitrary URLs/auth headers. Existing Harness identity/scope/grant/fence/ledger/terminal semantics are unchanged. Safe transport enforces HTTPS, DNS/address policy, TLS, no redirects, bounded responses/timeouts. Private origins require explicit Runtime allowlisting and connectivity. Only supported Card protocol/transport/auth configurations are callable. Worker and scheduled Main do not gain registration or collaboration privileges.

## Verification and design

[Registration and retirement design](../../prd-spec/features/mpa-collaborating-agents/2026-10-22-center-registration.md). Python route tests: tests/cli/test_a2a_center_registration.py; UI: frontend/tests/collaboratingAgents.test.tsx and mpaBasicDetails.test.tsx. Runtime cleanup tests live in agentkit-mpa-agent/tests/test_collaborator_retirement.py. Mocked tests and local browser checks are distinct from live cloud creation and real-PG cleanup.

## Space management (2026-10-22)

The binding and member areas are separate accessible sections. POST `/web/a2a-spaces?region=...` requires administrator and target Runtime authorization, accepts `{targetRuntimeId, name, projectName?, intentEnabled?}`, and returns `{id}` after signed CreateA2aSpace. Body limit is 4096 bytes; name/project are trimmed nonempty strings with at most 128 characters and no control characters; project defaults to default and semantic search to false. Reject unknown fields and non-boolean switches. Creation selects the confirmed space (including when absent from the current list page), never binds it automatically. Failed refresh preserves confirmed creation success. Uncertain writes/cancel require refresh before another mutation, with no automatic retry. Runtime/region switching cancels stale requests. Existing cloud identity/region and dispatch boundaries remain unchanged. Tags and space editing are outside the creation form; deletion follows the member-action contract below. See [space management design](../../prd-spec/features/mpa-collaborating-agents/2026-10-22-space-management.md).

The unbind action is offered only when the selected space equals the bound space. Switching spaces clears any prior confirmation; the mutation handler rejects unbinding another selected space. Space resource IDs remain in selection/request values but are omitted from user-facing names, status and destination labels.

## Member actions and deletion

Implemented locally: [member action design](../../prd-spec/features/mpa-collaborating-agents/2026-10-22-member-actions.md). Studio provides sanitized GET and confirmed DELETE /web/a2a-agents/{agentId}, scoped by targetRuntimeId, spaceId and region. Returned IDs must match. DELETE /web/a2a-spaces/{spaceId} checks current target binding, space identity and an empty member list before cloud deletion. No cascade, automatic unbinding, source Runtime deletion or automatic mutation retry. A2A-specific opt-in structured cloud errors distinguish known refusal from uncertainty; other helper callers retain existing behavior. Details exclude raw Cards, unsanitized URLs and provider errors. Closing pending mutations requires refresh reconciliation; identity changes abort stale UI updates.


## Deletion preflight authentication

CON-DELETE-AUTH: Runtime JSON collaborator requests apply the same administrator-only, server-owned `X-MPA-Studio-Key` policy as the dedicated collaborator proxy. Browser credentials cannot replace this key, and unrelated paths receive no collaborator key. Binding-read 401/403 yields `runtime_auth_failed` with the original status, performs no cloud calls and remains a retryable known preflight failure in the UI. Cloud permission refusals retain their separate behavior. See [authentication fix](../../prd-spec/bugfixes/mpa-a2a-space-deletion/2026-10-22-runtime-auth.md).


## Endpoint and skill metadata

CON-ENDPOINTS: GET /web/a2a-runtime-endpoints/{sourceRuntimeId} authorizes administrator and both targetRuntimeId/sourceRuntimeId in region. Return runtimeId and at most one configured safe HTTP(S) URL per public/private type. Registration offers only current configured types and blocks stale/unavailable selections; payload stays RuntimeId/NetworkType. No arbitrary endpoint URL is accepted.

CON-CARD-VIEW: Agent detail adds serviceAddress (string|null), skills (array|null) and skillsTruncated (boolean). Project only bounded name/description/tags/examples/ID, never raw Cards or authentication. Null indicates unavailable, [] confirmed empty; over 100 skills shows explicit truncation. Strip query/fragment; reject userinfo, malformed, control-character or non-HTTP(S) URLs. Metadata parsing affects View only, not deregistration. See [endpoint and skill design](../../prd-spec/features/mpa-collaborating-agents/2026-10-22-endpoints-and-skills.md).


## Runtime registration picker

CON-RUNTIME-PICKER: Runtime registration uses one required Select populated by authorized paginated Runtime reads. There is no separate manual ID field. The selected ID remains an internal request value; only a selection still present in the current list with a matching endpoint can submit. Loading, successful empty list and failed list reads remain distinct, with retry for empty/error and append pagination preserving selection. Standard imports and backend APIs are unchanged. See [single-picker fix](../../prd-spec/bugfixes/mpa-a2a-runtime-picker/2026-10-22-single-runtime-picker.md).

## 2026-10-22 Alias

Space-shared aliases are maintained by the Runtime in its account management database. Studio edits optional aliases with revision CAS through the authenticated Runtime proxy. No center name or Card is modified. See [alias design](../../prd-spec/features/mpa-collaborating-agents/2026-10-22-space-aliases.md). Implemented; local Node/Vitest tests, build and browser fixture verified. Cloud/model end-to-end acceptance pending.
