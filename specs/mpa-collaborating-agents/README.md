# MPA collaborating Agent configuration

Management base: `/api/v1/studio/collaborators`, scoped by the serving Runtime's configured `MPA_AGENT_ID`, never browser-provided ownership. Dedicated `X-MPA-Studio-Key` must match persisted current Runtime credential; Studio only injects it server-side for administrators. GET list; POST create; PATCH/DELETE `/{id}` and POST `/{id}/check` require positive `revision` (DELETE query). Version mismatch 409, missing record 404, unauthenticated 401, missing durable backend/Runtime identity 503. Public output excludes all credential values.

Database: additive `mpa_collaborating_agents` table with composite MPA/id key, JSON configuration and monotonically increasing revision. No volatile fallback. Existing Runtime business PG owns records. Migration is additive; rollback keeps the table and deploys the previous binaries. Older Studio/Runtime remain unchanged.

Connection check: HTTPS only; no userinfo/query/fragment; fixed explicit Card URL. Resolve and pin DNS for the request; reject non-global addresses by default and cloud metadata/loopback/link-local always. Explicit operator-configured `MPA_COLLABORATOR_PRIVATE_ORIGINS` permits private VPC destinations only for listed HTTPS origins. No redirects or environment proxies, bounded timeout and response size, TLS verification on. Card execution endpoint must have the same origin as the configured Card. Store only bounded allowlisted metadata, never arbitrary Card JSON. Check unsupported transport/auth schemes explicitly; no OAuth refresh in this version.


[Design](../../prd-spec/features/mpa-collaborating-agents/2026-10-20-collaborating-agents.md)

## Configuration and dispatcher handoff

As a Studio administrator, open **Agents → MPA → selected agent → Collaborating Agents**, the tab below **Basic information**, then **Add Agent**. Enter its name, purpose, full HTTPS Agent Card URL and authentication configuration. Save, then check the connection. Capabilities come from Card `skills`; they are not a second manually maintained list. This entry appears for MPAs only.

For Bearer/API Key authentication, enter the actual credential in Studio. New input is masked by default and can be shown temporarily. Saved credentials are never returned to the browser. Blank edits preserve an existing credential only for the same authentication mode, header and destination origin; a new origin requires re-entry. Selecting no authentication clears the credential. API keys also require a target-specific `X-` header. Old `MPA_COLLABORATOR_` environment references remain supported by Runtime APIs.

For a private endpoint, also set `MPA_COLLABORATOR_PRIVATE_ORIGINS=https://research.internal.example:443` on the Runtime and provide network connectivity and trusted TLS. Allowlisting an origin does not create VPCs, routes or firewall rules. Public endpoints need no allowlist. Cross-origin execution endpoints, plaintext HTTP, OAuth refresh, cloud AK/SK signing and non-JSONRPC transports are not supported in this version.

Example registration body (through the authenticated Studio proxy):
```json
{
  "name": "Research assistant",
  "description": "Find sources and organize evidence",
  "card_url": "https://research.example/.well-known/agent-card.json",
  "enabled": true,
  "auth_type": "bearer",
  "secret": "<target-agent-token>",
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

UI lifecycle: mount management only for the selected tab of an MPA with a Runtime and admin/super_admin permission. Key by region and Runtime ID; unmounting on tab/target/permission changes aborts requests and discards transient state. General agents, drafts and non-administrators have no entry or requests; unsupported focus falls back to Basic. Chat no longer exposes the entry.


## Credential storage and compatibility
`secret` is write-only (at most 8192 characters, no control characters). `credential_configured` is the public saved-credential indicator, not proof of a successful connection. Runtime encrypts the credential together with its MPA and registration ID in `config.encrypted_secret`. A dedicated key is generated once under a DB transaction lock and persisted as `collaborator_credential_key` in `mpa_deployment_settings`. No operator environment variable is needed. Keys and ciphertext must be backed up together; missing or corrupt keys fail with `credential_store_unavailable`, never automatic rotation. This protects response and ordinary configuration exposure, not database administrators, who can access both tables. Responses exclude plaintext and ciphertext; validation errors exclude raw input. Browser state is transient, never local storage. Direct-input Studio requires an upgraded Runtime; deploy the backend before the UI. For rollback, preserve both tables and use this version or a later compatible version to manage encrypted registrations. Old binaries do not support direct credentials.

Enabled controls dispatch eligibility; disabled registrations remain stored. Check success alone does not mean task dispatch has been implemented. [Direct credentials design](../../prd-spec/features/mpa-collaborating-agents/2026-10-20-direct-credentials.md).
