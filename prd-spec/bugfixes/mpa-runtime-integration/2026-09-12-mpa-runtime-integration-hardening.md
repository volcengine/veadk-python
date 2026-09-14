# MPA Runtime Integration Hardening and Studio Diagnostics

- **Change ID:** `mpa-runtime-integration-hardening`
- **Status:** Approved for implementation
- **Created / revised:** 2026-09-12
- **Change type:** Bugfix with user-visible diagnostics extensions
- **Chinese version:** [2026-09-12-mpa-runtime-integration-hardening.zh.md](2026-09-12-mpa-runtime-integration-hardening.zh.md)
- **Affected components:** [MPA Runtime Provisioning](../../../specs/mpa-runtime-provisioning/README.md), [Studio Runtime Diagnostics](../../../specs/studio-runtime-diagnostics/README.md)

## 1. Background and evidence

An mpa-agent created by `veadk mpa create` runs without ArkClaw control-plane resources. It deliberately uses the compatibility value `CLAW_SPACE_ID=csi-<account_id>`, external PostgreSQL, and an external OpenViking service. Runtime logs nevertheless show `arkclaw:ListResources` returning `403 AccessDenied` every 120 seconds and once on normal A2A session startup. The concrete call sites are `McpToolsCache._load_candidate_resources()` and `SessionService._query_appcenter_mcp_ids()`. The failures are caught, so chat continues, but ArkClaw MCP discovery is unavailable and the logs are polluted by repeated tracebacks.

The same live run proves four adjacent integration defects:

1. The phase-two Runtime update writes `A2A_PUBLIC_URL` but not the real key-auth credential as `CODEX_MCP_RUNTIME_API_KEY`; the built-in MCP source therefore warns that worker calls may be rejected.
2. `IDENTITY_STARTUP_ENABLED=false` skips startup metadata loading, but lazy sandbox login remains enabled. A sandbox turn tries to build a login URL and logs `IdentityConfig.UserPoolConfig missing fields: user_pool_id`.
3. Sandbox progress uses `append=true` for the first artifact update. The A2A SDK rejects every chunk because the artifact does not yet exist: `Received append=True for nonexistent artifact index ... Ignoring chunk.` The worker completes, but progressive tool output is lost.
4. Runtime `r-yeuujrrcowb21078p9jh` reports `apmplus_enable=false`; Studio's `/web/runtime-trace` correctly returns 404 and cannot display spans.

Two Studio gaps are also verified. The Runtime log service requests only 500 lines while the UI promises 1,000, and the dialog has no download action. A2A sandbox `usage.updated` events reach the bridge, but `A2AStreamDecoder` does not map them to Studio `usageMetadata`, so the existing token indicator cannot account for them.

Per-conversation model selection is not currently supported. The primary agent resolves its model from the persisted agent record or Runtime environment, while Codex delegation accepts an independent `modelOverride`. Adding a model selector without a single request-scoped contract would therefore produce split-model turns.

## 2. Goals

- `FR-1`: VeADK-created runtimes must not call ArkClaw `ListResources` when ArkClaw resource discovery is not part of their provisioning model. Native ArkClaw deployments keep their current default behavior.
- `FR-2`: Phase-two provisioning must atomically publish the resolved public URL and Runtime key to the Runtime environment, without printing or persisting the key in source artifacts.
- `FR-3`: VeADK mode must not attempt user-pool login when no user pool was provisioned.
- `FR-4`: The first sandbox artifact update must create the artifact; subsequent updates may append to it, preserving event ordering and deduplication.
- `FR-5`: Runtime logs must remain live, display the latest 1,000 sanitized lines, and let the user download exactly the current sanitized snapshot.
- `FR-6`: Studio must reuse its existing token accounting UI for mpa-agent primary-model and delegated-worker usage, without counting cumulative snapshots repeatedly.
- `FR-7`: Studio may select an allowed model for one conversation turn. The override must apply consistently to the primary agent and delegated worker, must not expose credentials, and must fall back to the configured default when absent.
- `FR-8`: `veadk mpa create` must enable APMPlus tracing by default for AgentKit Runtime deployments, and Studio must retain its existing disabled, collecting, forbidden, ready, and error states.
- `FR-9`: Expected absence of optional control-plane configuration must be handled without full warning tracebacks; unexpected infrastructure failures must remain visible.

## 3. Non-goals

- Granting `arkclaw:ListResources` to synthetic compatibility spaces or creating ArkClaw user pools.
- Removing `CLAW_SPACE_ID`, changing PostgreSQL/OpenViking ownership, or changing APIG key-auth.
- Downloading an unbounded historical log archive; Runtime returns a bounded snapshot only.
- Sending model API keys to the browser or accepting arbitrary endpoint/provider credentials per request.
- Changing the behavior of native ArkClaw deployments.

## 4. Scenarios

1. **External-resource runtime:** Given a Runtime created by VeADK, when its cache refreshes or a session resolves MCP sources, then no AppCenter request is made and no `ListResources` warning is emitted.
2. **Built-in MCP:** Given a key-auth Runtime, when Codex calls the built-in MCP endpoint, then the phase-two Runtime key is used in the internal request header.
3. **No identity pool:** Given `IDENTITY_STARTUP_ENABLED=false`, when a turn delegates to sandbox, then no login URL is attempted and the sandbox proceeds with the configured shared credentials.
4. **Sandbox progress:** Given the first normalized worker event, when it is relayed through A2A, then the first artifact update uses `append=false`; later events use `append=true` and are visible to Studio.
5. **Logs:** Given a resolved Runtime instance, when logs refresh, then Studio replaces its bounded snapshot, retains at most 1,000 lines, and downloads the same text with a deterministic `.log` filename.
6. **Usage:** Given primary-model ADK usage or worker `usage.updated`, when Studio receives the event, then the existing indicator shows current and cumulative usage once per authoritative update.
7. **Model override:** Given an allowed model selected in Studio, when a message is sent, then the BFF places the model ID in A2A metadata and mpa-agent applies it request-locally to both the primary endpoint resolver and delegated worker. Invalid or unavailable IDs fail before model execution.
8. **Trace:** Given a newly provisioned Runtime and sufficient APMPlus read permission, when a completed session trace is opened, then Studio transitions from collecting to a span tree. Missing permission remains an explicit 403 rather than empty data.

## 5. Design

### 5.1 Provisioning mode and credentials

Use existing narrow switches instead of introducing a broad deployment-mode enum:

- Set `APPCENTER_RESOURCE_DISCOVERY_ENABLED=false` in the VeADK environment. Add this mpa-agent setting with a native-default value of `true`; it controls both the session fallback query and the AppCenter dependency supplied to `McpToolsCache`. `MCP_TOOLS_CACHE_ENABLED` remains enabled so explicitly cached/non-AppCenter sources can still benefit from it.
- Set `MPA_LAZY_LOGIN=false` together with `IDENTITY_STARTUP_ENABLED=false`. The identity-independent runtime must never enter the lazy user-pool login path.
- Set `APMPLUS_TRACE_CONTENT=false` by default; this retains span timing and structured details without exporting raw prompts or responses.
- Extend Runtime phase two to merge `A2A_PUBLIC_URL` and `CODEX_MCP_RUNTIME_API_KEY=<resolved key>` before `UpdateRuntime(ReleaseEnable=True)`. VeFaaS phase two receives the same pair. Add the Runtime key to the secret-redaction set.
- Pass `ApmplusEnable=true` on Runtime create and reuse/update. This is a Runtime control-plane field, not an environment variable.

This is preferred over granting ArkClaw permissions (wrong resource model) or merely reducing log level (would retain futile calls and broken functionality).

### 5.2 Expected optional-configuration failures

mpa-agent dependency construction passes `appcenter_client=None` when resource discovery is disabled. `SessionService` and `McpToolsCache` already treat `None` as no discovery. The sandbox desensitization lookup treats `AgentNotFound` as the expected absence of an agent configuration and falls back at debug/info level; transport/database errors continue to log warnings with tracebacks.

The compatibility 404s for `/list-apps` and `/web/agent-info/a2a-default` are Studio's legacy probe before its successful A2A agent-card fallback. They are not Runtime failures. This change does not add fake routes; follow-up logging may classify these known probe 404s below warning level without altering response semantics.

### 5.3 A2A artifact ordering

Maintain request-local state in `relay_codex_event`: the first emitted `sandbox-<invocation_id>` artifact uses `append=false`; every later event uses `append=true`. Event IDs remain the deduplication key. The state changes only after enqueue succeeds, so a failed first enqueue cannot cause later events to append to a nonexistent artifact.

### 5.4 Logs and download

`RuntimeLogService.read_logs()` requests `Limit=1000`, sanitizes the response, and bounds it to its final 1,000 logical lines. SSE continues to replace, not concatenate, the snapshot every second. The dialog download button creates a UTF-8 text Blob from the current rendered snapshot, downloads it locally, and immediately revokes the object URL. It is disabled when no log text exists. No new cloud endpoint or broader authorization scope is introduced.

### 5.5 Token usage projection

The A2A bridge maps two sources into the existing ADK event fields:

- A2A `metadata.adk_usage_metadata` becomes `usageMetadata` on the projected Studio event.
- Sandbox `usage.updated` maps worker fields (`inputTokens`, `outputTokens`, `totalTokens`, `cachedTokens`, `reasoningTokens`, `modelId`) into the existing camel-case ADK usage/model fields.

The decoder tracks the last authoritative usage snapshot per `(source, requestId/model)` and emits only a positive delta to cumulative accounting. This prevents repeated cumulative A2A status snapshots from inflating totals. Existing `addTokenUsageFor()` and `TokenUsageIndicator` remain the single owner of display.

### 5.6 Model selection

The first implementation is an allowlisted request override, not Runtime mutation:

- The mpa-agent agent card advertises model IDs from a new non-secret `MPA_SELECTABLE_MODELS` JSON/CSV environment value plus the configured default.
- Studio shows the selector only for the A2A virtual app and only when more than one model is advertised. Selection is session-local and disabled while a turn is running.
- `runSSE` sends `modelId` in `custom_metadata`; the A2A BFF forwards it as request metadata.
- mpa-agent validates the model ID, stores it in `InvocationContext`, and `ModelEndpointResolver` prefers it for that invocation while retaining configured provider/base URL/API key. Codex delegation receives the same `modelOverride.modelId`.
- Sessions and other channels keep the configured default unless their request explicitly carries an allowed override. No global environment update occurs.

If the deployed model endpoint does not support multiple model IDs with the same credential/base URL, only the default is advertised and the selector is hidden.

### 5.7 Trace observability

Provisioning sets `ApmplusEnable=true` and waits for the released version. Existing `/web/runtime-trace` authorization and normalization remain unchanged. Verification distinguishes:

- 404: Runtime tracing disabled (configuration defect);
- 425: trace still collecting (retryable);
- 403: Studio credentials lack `APMPlusServerReadOnlyAccess` (permission blocker);
- 200: normalized spans rendered by `TraceDrawer`.

## 6. Security, compatibility, and failure semantics

- All new switches default to current native mpa-agent behavior. Only `veadk mpa create` opts out of ArkClaw discovery/login.
- Runtime API keys remain server-side, are redacted in dry-run/output, and are never placed in agent-card metadata or browser payloads.
- Log downloads contain the same already-sanitized bounded snapshot visible in the UI.
- Model overrides are IDs only and must match the server-advertised allowlist. They cannot change provider, URL, or secret.
- Phase-two update failure is fatal because a partially configured Runtime cannot safely expose built-in MCP. The created resource ID remains in the error for recovery, without its key.
- APMPlus content tracing remains disabled unless explicitly overridden; enabling tracing does not authorize Studio to read it.

## 7. Implementation tasks

| ID | Work | Primary files | Depends on |
| --- | --- | --- | --- |
| `T-1` | Add discovery boundary and expected-absence handling in mpa-agent | `app/core/config.py`, `app/api/deps.py`, `app/integrations/agentkit_sandbox.py` | none |
| `T-2` | Correct first A2A artifact append semantics | `app/a2a/executor.py`, `tests/test_a2a_executor.py` | none |
| `T-3` | Inject VeADK mode env/key and enable Runtime APMPlus | `mpa_provision.py`, `mpa_runtime.py`, `cli_mpa.py` | `T-1` |
| `T-4` | Align 1,000-line snapshot and add download | `runtime_logs.py`, `RuntimeLogsDialog.tsx`, i18n/tests | none |
| `T-5` | Project authoritative token usage | `runtime_a2a_stream.py`, token projection tests | `T-2` |
| `T-6` | Add allowlisted request-scoped model selection | mpa-agent invocation/model/A2A files; Studio BFF/client/composer | `T-3` |
| `T-7` | Validate live trace and end-to-end behavior | Runtime/Studio live checks | `T-1`–`T-6` |

## 8. Tests and acceptance

| Requirement | Acceptance criterion | Verification | Initial result |
| --- | --- | --- | --- |
| `FR-1`, `FR-3` | No AppCenter/user-pool call in VeADK mode; native defaults preserved | mpa-agent config/dependency/session tests and live log observation over two refresh intervals | Unit tests `pass`; live new-image verification `not_run` |
| `FR-2` | Phase-two request contains URL and key; no output leaks key | `tests/integrations/test_mpa_runtime.py`, `test_mpa_provision_env.py`, CLI tests | `pass` |
| `FR-4` | First artifact creates, later artifacts append, all arrive | `tests/test_a2a_executor.py` plus real sandbox turn | Unit tests `pass`; live new-image verification `not_run` |
| `FR-5` | 1,000-line bounded live view and matching download | Runtime log backend/frontend tests plus browser check | Automated tests/build `pass`; browser check `blocked` by missing Playwright browser |
| `FR-6` | Primary and worker usage display once, reload remains consistent | decoder/token tests plus real Runtime turn | Automated tests `pass`; live new-image verification `not_run` |
| `FR-7` | Allowed override reaches both paths; invalid ID rejected; default unchanged | mpa-agent unit/integration tests and Studio browser test | Automated tests `pass`; live new-image verification `not_run` |
| `FR-8` | New/update Runtime has APMPlus enabled and TraceDrawer reaches 200 or reports an external 403 permission blocker | Runtime tests and live `/web/runtime-trace` | Runtime request tests `pass`; current version 31 remains `fail` (verified 404 disabled); no deployment performed |

Required repository checks include targeted Python tests, `npm --prefix frontend test`, `npm --prefix frontend run build`, changed-file Ruff/Pyright, the applicable broader Python regression, browser verification, and pre-commit. Real cloud checks are reported separately from simulated tests.

## 9. Review record

Design review found and resolved these blockers before implementation:

- **Over-broad mode flag:** replaced by the narrow `APPCENTER_RESOURCE_DISCOVERY_ENABLED` switch, preserving independent caches and native defaults.
- **Secret exposure risk:** model selection carries only IDs; phase-two keys remain server-side and join the redaction set.
- **Token double counting:** defined authoritative snapshot/delta normalization instead of forwarding cumulative values blindly.
- **Trace/privacy ambiguity:** separated `ApmplusEnable=true` from `APMPLUS_TRACE_CONTENT=false`.
- **Artifact race:** first-artifact state advances only after successful enqueue.
- **Unbounded log download:** download is exactly the sanitized 1,000-line current snapshot.

No unresolved design blocker remains. The user's explicit request to analyze and fix the reported exceptions and add the listed diagnostics is recorded as implementation approval for this scoped design. Any broader auth, control-plane, or model-credential change requires a new review.
