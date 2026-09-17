# MPA Runtime Provisioning

- **Component ID:** `mpa-runtime-provisioning`
- **Status:** Draft; proposed changes are governed by the related PRD
- **Revision:** 2026-09-12
- **Chinese version:** [README.zh.md](README.zh.md)
- **Related PRD:** [MPA Runtime Integration Hardening](../../prd-spec/bugfixes/mpa-runtime-integration/2026-09-12-mpa-runtime-integration-hardening.md)
- **Owned code:** `veadk/cli/cli_mpa.py`, `veadk/integrations/mpa/mpa_provision.py`, `veadk/integrations/mpa/mpa_runtime.py`

## Responsibility

This component converts `veadk mpa create` inputs into one recoverable AgentKit Runtime or VeFaaS deployment, binds its Tool, seeds/finalizes `mpa_meta`, publishes the public A2A endpoint and Runtime credentials to the server-side environment, and verifies that the endpoint is reachable. PostgreSQL, OpenViking, model services, ArkClaw control-plane resources, and Studio presentation remain owned by their respective systems.

## Entry points and dependencies

- CLI: `veadk mpa create`.
- Control planes: AgentKit Runtime by default; VeFaaS is a compatibility option.
- Data: caller-supplied external PostgreSQL and optional OpenViking.
- Runtime consumer: the independently versioned mpa-agent image.

## Contract

- `CON-1`: The VeADK deployment profile sets `IDENTITY_STARTUP_ENABLED=false`, `MPA_LAZY_LOGIN=false`, `APPCENTER_RESOURCE_DISCOVERY_ENABLED=false`, and retains the derived `CLAW_SPACE_ID` compatibility value.
- `CON-2`: Key-auth is enabled by default. After the endpoint and key exist, phase two releases an environment containing both `A2A_PUBLIC_URL` and `CODEX_MCP_RUNTIME_API_KEY`. The key is never printed and is treated as a secret in previews.
- `CON-3`: AgentKit Runtime create and convergent update set `ApmplusEnable=true`. Trace content remains disabled by `APMPLUS_TRACE_CONTENT=false` unless the operator explicitly overrides it.
- `CON-4`: Phase one writes placeholders before startup; phase two overwrites them only with non-empty authoritative Runtime values. A phase-two deployment failure is reported as failure, not partial success.
- `CON-5`: Explicit caller `extra_env` remains last-wins, including an intentional override of VeADK profile defaults.
- `CON-6`: AgentKit Runtime create and convergent update persist `veadk:agent-type=mpa` as the stable Studio classification tag. Untagged Runtime resources remain outside the MPA filter until an explicit tag repair is performed.

## State, security, and compatibility

The lifecycle is `prepared -> resource-created -> ready -> environment-finalized -> metadata-finalized -> verified`. Reuse-by-name converges the existing Runtime through `UpdateRuntime(ReleaseEnable=True)` and waits for a newer ready version. Secrets remain process/control-plane data and must be redacted from CLI output, documents, logs, and test fixtures. Native mpa-agent deployments retain their own defaults because the opt-out switches are injected by this component rather than changing native defaults.

## Failure and observability

Missing endpoint, key, Runtime ID, or APIG ID blocks metadata finalization. Runtime terminal states and readiness timeouts raise `MpaRuntimeError`. The CLI reports created resource identifiers needed for recovery without exposing credentials. APMPlus enablement is verified from Runtime metadata; trace read authorization is a separate Studio concern.

## Verification

| Contract | Validation |
| --- | --- |
| `CON-1`, `CON-2`, `CON-5` | `uv run --extra dev pytest tests/integrations/test_mpa_provision_env.py tests/cli/test_cli_mpa.py` |
| `CON-2`, `CON-3`, `CON-4`, `CON-6` | `uv run --extra dev pytest tests/integrations/test_mpa_runtime.py` |
| End-to-end | Create/reuse an isolated Runtime, inspect metadata without printing keys, invoke A2A and built-in MCP, and observe two MCP-cache intervals |

VeADK MPA provisioning defaults DISABLE_JWT_AUTH to true. Explicit extra_env values override this default, including false. Gateway authentication and other deployment paths are unchanged.
