# Per-MPA collaborating Agents

> Credential input/storage decisions below are superseded by the 2026-10-20 direct-credentials design; other registration behavior is unchanged.

Date: 2026-10-20. Status: implemented; local verification recorded below, not released.

## Approval and scope
The user approved implementing registration under one selected MPA, then explicitly included the Studio configuration page. This approval covers additive management APIs and persistence. Task dispatch, streaming/event collection, remote deployment, Main/Worker changes and `dispatch_a2a_task` belong to another owner and are excluded.

## Evidence and intent
Runtime subagent bindings represent Worker execution handles, not durable external Agent registration. Studio already authorizes Runtime access and proxies requests with server-resolved credentials. Reuse this boundary. No global catalog or automatic sharing between MPAs.

## Requirements and tasks
- R1/T1: persist named registrations scoped by MPA, with description, Agent Card URL, enabled flag, authentication configuration and revision; list/create/update/delete. Deletion never deletes the target Agent.
- R2/T2: explicit connection check fetches a bounded A2A Agent Card, records name, description, skills, endpoint and protocol version. A successful check means discovery only, never task execution. Edits invalidate prior checks; concurrent edits/probes use compare-and-swap revisions.
- R3/T3: none, bearer and API-key authentication use Runtime environment references restricted to `MPA_COLLABORATOR_` names. Values never enter database records, API responses, browser persistence or logs. Missing secrets fail explicitly. Configure values through existing Runtime environment management; this version does not create a secret vault or accept raw secret input.
- R4/T4: Studio selected-MPA information panel opens configuration; supports loading/empty/error/retry, creation, editing, enable/disable, validation and removal confirmation. Switching Runtime closes/aborts outstanding work; late responses cannot overwrite another selection. Old Runtime 404 reports upgrade required, not empty success. Admin-only consistent with channel administration.
- R5/T5: internal server-side `resolve_for_dispatch(mpa_id, registration_id)` returns a frozen configuration snapshot only for enabled, successfully checked registrations. It resolves current secret references, without dispatching a task or exposing credentials in HTTP. Dispatcher must use the guarded transport again at execution and enforce its own caller authorization.

## Contract
Management base: `/api/v1/studio/collaborators`, scoped by the serving Runtime's configured `MPA_AGENT_ID`, never browser-provided ownership. Dedicated `X-MPA-Studio-Key` must match persisted current Runtime credential; Studio only injects it server-side for administrators. GET list; POST create; PATCH/DELETE `/{id}` and POST `/{id}/check` require positive `revision` (DELETE query). Version mismatch 409, missing record 404, unauthenticated 401, missing durable backend/Runtime identity 503. Public output excludes all credential values.

Database: additive `mpa_collaborating_agents` table with composite MPA/id key, JSON configuration and monotonically increasing revision. No volatile fallback. Existing Runtime business PG owns records. Migration is additive; rollback keeps the table and deploys the previous binaries. Older Studio/Runtime remain unchanged.

Connection check: HTTPS only; no userinfo/query/fragment; fixed explicit Card URL. Resolve and pin DNS for the request; reject non-global addresses by default and cloud metadata/loopback/link-local always. Explicit operator-configured `MPA_COLLABORATOR_PRIVATE_ORIGINS` permits private VPC destinations only for listed HTTPS origins. No redirects or environment proxies, bounded timeout and response size, TLS verification on. Card execution endpoint must have the same origin as the configured Card. Store only bounded allowlisted metadata, never arbitrary Card JSON. Check unsupported transport/auth schemes explicitly; no OAuth refresh in this version.

## Design review
Reviewed ownership, credential handling, SSRF/redirect/DNS rebinding, cancellation, cross-MPA queries, stale results, old Runtime compatibility and bilingual equivalence. Existing dependencies suffice. Runtime registration and Studio proxy tests must establish authorization independently. UI skills referenced by frontend/SPEC.md are absent from this checkout and local skills directories; apply the repository's existing component/foundation standards directly. No speculative executor integration.

## Acceptance / verification
| Requirement | Evidence | Status |
| --- | --- | --- |
| R1 | Durable store isolation, restart, CAS and delete tests | verified locally |
| R2/R3 | Invalid card, SSRF, authentication, timeout, redaction and stale-check tests | verified locally |
| R4 | Studio proxy tests, UI interaction tests, frontend test/build and browser checks | verified locally |
| R5 | Internal snapshot enablement/revision/auth tests | verified locally |
Required Runtime gates: `make lint`, `make test`; Studio affected Python tests/Ruff/Pyright, `npm --prefix frontend test`, `npm --prefix frontend run build`. Actual results are recorded below. No production release, cloud mutations or live third-party credential tests authorized by this implementation request.

## Configuration and dispatcher handoff

As a Studio administrator, select an MPA and open **Collaborating Agents** in its conversation information rail, then **Add Agent**. Enter its name, purpose, full HTTPS Agent Card URL and authentication configuration. Save, then check the connection. Capabilities come from Card `skills`; they are not a second manually maintained list. This entry appears for MPAs only.

For Bearer authentication, an operator first configures `MPA_COLLABORATOR_RESEARCH` in the Runtime environment. Enter only that variable name in Studio. API key authentication additionally takes a target-specific `X-` header name. Secret values never pass through this form. Apply environment changes through the platform's Runtime release/restart process and check again.

For a private endpoint, also set `MPA_COLLABORATOR_PRIVATE_ORIGINS=https://research.internal.example:443` on the Runtime and provide network connectivity and trusted TLS. Allowlisting an origin does not create VPCs, routes or firewall rules. Public endpoints need no allowlist. Cross-origin execution endpoints, plaintext HTTP, OAuth refresh, cloud AK/SK signing and non-JSONRPC transports are not supported in this version.

Example registration body (through the authenticated Studio proxy):
```json
{
  "name": "Research assistant",
  "description": "Find sources and organize evidence",
  "card_url": "https://research.example/.well-known/agent-card.json",
  "enabled": true,
  "auth_type": "bearer",
  "secret_env": "MPA_COLLABORATOR_RESEARCH",
  "header_name": ""
}
```
The response includes `id`, `mpa_id`, `revision` and `check`. New entries are `not_checked`; `POST /{id}/check` takes the current `revision` and returns a new one. `verified` means Card discovery and format compatibility only, not successful task execution. Editing invalidates the check. If a mutation's outcome is unknown after a connection failure, the UI requires refresh before another mutation, avoiding blind duplicate creation.

Handoff to the `dispatch_a2a_task` owner:
```python
# Use an injected CollaboratorService; mpa_id comes from trusted execution context.
snapshot = await service.resolve_for_dispatch(mpa_id, registration_id)
# snapshot: mpa_id / registration_id / revision / endpoint /
#           headers (server-only, hidden from repr) / protocol_version
```
The dispatcher must authorize the caller for that MPA, revalidate destination/DNS safety at request time, and implement tasks, SSE, cancellation, results and trace. Never expose `headers` in model context, execution traces or HTTP responses; do not use an unguarded HTTP client. Disabled or unverified records return `registration_not_ready`. This change does not inject registrations into the model or make them callable automatically.

Persistence borrows the existing Runtime channel-store engine: business PostgreSQL in production, durable SQLite files for local development, with in-memory SQLite rejected. The additive `0013_collaborating_agents.sql` migration also has the existing first-use table-creation path; restricted DB users can have the migration applied by an operator first. Records are scoped to the current MPA; there is no global catalog or new PG instance. Rollback retains the table and registrations.

## Verification record (2026-10-20)

- Runtime: Python 3.12; **23 passed** for the new registration module, including PostgreSQL 16 migration SQL, persistence after reconnect, MPA isolation and competing revision updates; **38 passed** including metadata/migration contract regressions. New-module statement coverage **93.77% (286/305)** and combined branch coverage **91.99%**. `make lint`, focused Ruff/Pyright, diff whitespace checks and production-code secret scan passed.
- Full Runtime `make test`: initial **9294 passed / 249 skipped / 1 failed** due to an obsolete local Codex entry (`Codex 0.155.1 is required`). After installing pinned 0.155.1, the affected native test **passed**; the final full rerun completed with **9298 passed / 250 skipped / 0 failed** (635.44 seconds, exit 0).
- Studio: proxy policies and the entire Runtime proxy test module **133 passed**; frontend Node **1389 passed**, Vitest **123 passed (9 files)**; TypeScript `tsc --noEmit`, frontend production build and affected Python Ruff passed. The new Python helper has zero Pyright errors. The whole `cli_frontend.py` has **37 existing Pyright errors**, identical to HEAD after normalizing filenames and line numbers, with no added diagnostics. Full Studio Python type checking is therefore not claimed as passing.
- Browser: real configuration component against local Runtime registration API/storage; create, Card check, edit/disable, removal confirmation, close/reopen, 360px narrow scrolling, keyboard authentication selection and missing-secret feedback passed. The fixture mocks the remote Card and local authentication; Studio BFF authorization is covered separately by integration tests. This is not cloud end-to-end acceptance.
- Not verified / excluded: real external credentials or private connectivity, production release, cloud mutations, full remote formal/coverage CI gates, and `dispatch_a2a_task` execution. Existing full-suite event-loop cleanup warnings remain in reports; they are not described as business failures. No commit, push or deployment performed.

UI location superseded by the [detail-tab design](2026-10-20-collaborating-agents-detail-tab.md).
