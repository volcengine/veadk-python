# MPA Runtime Provisioning

- **Component ID:** `mpa-runtime-provisioning`
- **Status:** Draft; proposed changes are governed by the related PRD
- **Revision:** 2026-09-20
- **Chinese version:** [README.zh.md](README.zh.md)
- **Related PRD:** [MPA Runtime Integration Hardening](../../prd-spec/bugfixes/mpa-runtime-integration/2026-09-12-mpa-runtime-integration-hardening.md)
- **Related PRD:** [MPA Studio Workload Identity Provisioning](../../prd-spec/features/mpa-studio-workload-identity/2026-09-20-mpa-studio-workload-identity.md)
- **Owned code:** `veadk/cli/cli_mpa.py`, `veadk/integrations/mpa/mpa_provision.py`, `veadk/integrations/mpa/mpa_runtime.py`

## Responsibility

This component converts `veadk mpa create` inputs into one recoverable AgentKit Runtime or VeFaaS deployment, binds its Tool, seeds/finalizes `mpa_meta`, publishes the public A2A endpoint and Runtime credentials to the server-side environment, and verifies that the endpoint is reachable. PostgreSQL, OpenViking, model services, ArkClaw control-plane resources, and Studio presentation remain owned by their respective systems.

## Entry points and dependencies

- CLI: `veadk mpa create`.
- Control planes: AgentKit Runtime by default; VeFaaS is a compatibility option.
- Data: caller-supplied external PostgreSQL and optional OpenViking.
- Runtime consumer: the independently versioned mpa-agent image.

## Contract

- `CON-1`: The VeADK deployment profile sets `IDENTITY_STARTUP_ENABLED=false`, `MPA_LAZY_LOGIN=false`, `APPCENTER_RESOURCE_DISCOVERY_ENABLED=false`, and retains the derived `CLAW_SPACE_ID` compatibility value. This disables ArkClaw UserPool startup but does not disable outbound workload-token use.
- `CON-2`: Key-auth is enabled by default. After the endpoint and key exist, phase two releases an environment containing both `A2A_PUBLIC_URL` and `CODEX_MCP_RUNTIME_API_KEY`. The key is never printed and is treated as a secret in previews.
- `CON-3`: AgentKit Runtime create and convergent update set `ApmplusEnable=true`. Trace content remains disabled by `APMPLUS_TRACE_CONTENT=false` unless the operator explicitly overrides it.
- `CON-4`: Phase one writes placeholders before startup; phase two overwrites them only with non-empty authoritative Runtime values. A phase-two deployment failure is reported as failure, not partial success.
- `CON-5`: Explicit caller `extra_env` remains last-wins, including an intentional override of VeADK profile defaults.
- `CON-6`: AgentKit Runtime create and convergent update persist `veadk:agent-type=mpa` as the stable Studio classification tag. Untagged Runtime resources remain outside the MPA filter until an explicit tag repair is performed.
- `CON-7`: Before other provisioning mutations, the CLI creates or reuses the account-and-region scoped pool `agentkit-studio-workload` and identity `{MPA_AGENT_ID}-studio`, then injects them as `MPA_WORKLOAD_POOL_NAME` and `MPA_WORKLOAD_IDENTITY_NAME`.
- `CON-8`: Generated and explicit ids accepted by `veadk mpa create` match `mi-[0-9a-z]{12}`. The base id remains the Runtime and metadata identity; only the workload identity receives the `-studio` suffix.
- `CON-9`: Workload get-or-create is exact-name idempotent. Concurrent create conflicts are followed by a read. Other Identity errors fail before Tool, database, or Runtime mutations. Created identity resources are retained for retry.

## State, security, and compatibility

The lifecycle is `prepared -> resource-created -> ready -> environment-finalized -> metadata-finalized -> verified`. Reuse-by-name converges the existing Runtime through `UpdateRuntime(ReleaseEnable=True)` and waits for a newer ready version. Secrets remain process/control-plane data and must be redacted from CLI output, documents, logs, and test fixtures. Native mpa-agent deployments retain their own defaults because the opt-out switches are injected by this component rather than changing native defaults.

## Failure and observability

Missing endpoint, key, Runtime ID, or APIG ID blocks metadata finalization. Runtime terminal states and readiness timeouts raise `MpaRuntimeError`. The CLI reports created resource identifiers needed for recovery without exposing credentials. APMPlus enablement is verified from Runtime metadata; trace read authorization is a separate Studio concern.

## Verification

| Contract | Validation |
| --- | --- |
| `CON-1`, `CON-2`, `CON-5`, `CON-7`, `CON-8` | `uv run --extra dev pytest tests/integrations/test_mpa_provision_env.py tests/cli/test_cli_mpa.py` |
| `CON-2`, `CON-3`, `CON-4`, `CON-6` | `uv run --extra dev pytest tests/integrations/test_mpa_runtime.py` |
| `CON-7`, `CON-9` | `uv run --extra dev pytest tests/integrations/test_mpa_identity.py tests/cli/test_cli_mpa.py` |
| End-to-end | Create/reuse an isolated Runtime, inspect metadata without printing keys, invoke A2A and built-in MCP, and observe two MCP-cache intervals |

VeADK MPA provisioning defaults DISABLE_JWT_AUTH to true. Explicit extra_env values override this default, including false. Gateway authentication and other deployment paths are unchanged.

MPA provisioning defaults `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS` to `sqlalchemy,asyncpg,psycopg,psycopg2,dbapi`, suppressing database auto-instrumentation while preserving business tracing. Explicit `extra_env` overrides win, including an empty string to re-enable instrumentation. This applies to newly provisioned or explicitly redeployed resources, not existing running instances.

## Managed creation boundary

Studio MPA creation and `veadk mpa provision` are owned by [Studio MPA creation](../studio-mpa-creation/README.md). That path prepares account resources and uses real Runtime metadata bootstrap. The existing responsibilities and legacy entry points described here remain unchanged.

## Proposed AgentKit P0 profile

Governed by [P0 functional migration](../../prd-spec/features/mpa-p0-productionization/2026-09-15-mpa-p0-productionization-design.md). Baseline `CON-1` through `CON-6` remain historical/current integration contracts; the following explicitly proposed profile strengthens readiness and security without claiming implementation. Native/VeFaaS compatibility is separate. No ArkClaw users, metadata or old identifiers are imported.

- `CON-7`: AgentKit-mode bootstrap uses a versioned manifest of account/workspace/MPA-instance/Runtime identity, endpoint, resource and server-side credential references. `agentkit-mpa-agent` consumes it and never calls ArkClaw configuration/identity/AppCenter fallback for required P0 functionality. Missing configuration returns a classified not-ready state and recoverable finalization step. Internal compatibility names such as `CLAW_SPACE_ID` may remain only as derived values with no old service lookup. Runtime owns MPA Profile revisions; bootstrap records only the binding and applied revision.
- `CON-8`: Preserve prepare/create/finalize phases, but distinguish transport-ready from execution-ready. An unfinalized Runtime may answer bootstrap health while refusing user execution. This avoids requiring finalized endpoint credentials before the platform can report transport readiness. After endpoint/key/Tool and manifest finalization, execution readiness and A2A/worker smoke must pass before success is reported. Repeated create/finalize uses a stable operation ID and resource ownership checks; partial failure reports safe created IDs and next recovery step.
- `CON-9`: Configure AgentKit custom-JWT issuer discovery and allowed client/audience per [runtime identity contract](../mpa-runtime-control/README.md), `CON-1`, and let BFF forward only a validated bearer. API key-auth and user identity are separate. New AgentKit profile validates final merged configuration after caller overrides; insecure JWT bypass or enabled legacy fallback is rejected. This deliberately constrains baseline last-wins `extra_env` only in the opt-in profile and must be tested as a public CLI/config boundary.
- `CON-10`: Key rotation updates server-side references/configuration and reconciles runtime, built-in MCP and worker clients. Neither CLI nor UI receives secret values in normal results. Reconciliation failure remains failure, supports retry with the same operation ID, and never claims the old key was revoked before consumers are ready. Exact key release/rotation operations must be verified against platform APIs in PRD `T-1`.
- `CON-11`: Release metadata pins Runtime image digest, applied MPA Profile revision, session execution-config schema, and worker protocol compatibility. Reuse the AgentKit SDK Runtime create/get/list/update/release/delete/listVersions/listInstances/getLogs methods; Managed Agent APIs are not part of P0. Implementation must still verify Runtime write permissions, idempotency, errors, and rollback behavior. Compatible rollback waits for execution readiness and smoke. New-platform schema evolution is additive; reject incompatible downgrade before mutation. Historical ArkClaw migration is not part of this lifecycle.
- `CON-12`: Delete requires authorized impact preview, active Session/job and resource-reference checks, explicit confirmation, and durable cleanup progress. Shared Tool/Skill/storage resources are retained unless owned exclusively by the operation and separately authorized. Failed cleanup returns retryable/blocked status with safe identifiers; never report full deletion while owned runtime resources remain.

These guarantees apply to both Studio and CLI through shared orchestration. The target platform operation inventory and bootstrap field/config names are a blocking `T-1` deliverable, not a claim of existing APIs.

Verification maps `CON-7` through `CON-12` to PRD `AC-1`, `AC-2`, `AC-9`, `AC-10`: fresh bootstrap with legacy endpoints blocked; missing/finalization failure and restart; unsafe overrides; credential rotation/retry; compatible rollback; active/shared-resource deletion. Reuse existing provisioning regression targets above and add failing tests for the new profile. All proposed runtime/live results are `not_run`.

2026-09-15: profile drafted for functional migration without historical data import; implementation and live evidence pending.
