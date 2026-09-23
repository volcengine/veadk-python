# MPA per-session TOS output mount

- Status: approved
- Date: 2026-09-23
- Owner: VeADK MPA provisioning
- Approval: the requester approved implementation on 2026-09-23

## Problem

An MPA Runtime provisioned by VeADK can create a dedicated Codex worker Tool,
but the Tool and its Sessions currently have no TOS output mount. Outputs under
`/data/output` therefore have no per-conversation TOS namespace.

## Goals

1. Accept `tos-access-key`, `tos-secret-key`, and `tos-bucket` in the existing
   private MPA YAML for both `mpa create` and managed `mpa provision`.
2. Put the TOS credentials only in the Tool `TosMountConfig`; do not copy them
   into Runtime environment variables, dry-run output, logs, or registry rows.
3. Mount TOS read-write at `/data/output` and derive its endpoint from the Tool
   region.
4. Tell the Runtime to generate `CreateSessionRequest.TosMountPoints` for each
   newly created Session. The SDK-standard path is
   `/sandbox-session/tool-{tool_id}/session-{session_id}/`.
5. Preserve current behavior when all three settings are absent and reject a
   partial tuple before cloud or database side effects.

## Non-goals

- Updating a pre-existing Tool or remounting an already running Session.
- Making the bucket prefix, endpoint, local path, or read-only mode configurable.
- Replacing the worker's existing output mirroring behavior.

## Design

The flat YAML keys remain the single secret input contract. Managed profile
loading copies the validated tuple into the in-memory worker options. A newly
created Tool receives an access-key `TosMountConfig` with the canonical base
path `/sandbox-session/default/default` and local path `/data/output`. VeADK
sets `MPA_CODEX_WORKER_TOS_MOUNT_ENABLED=true` and the non-secret bucket name
on the Runtime. AK/SK never enter the Runtime.

When that flag is enabled, mpa-agent delegates path derivation to AgentKit
SDK's `build_session_bucket_path` and attaches the result to
`CreateSessionRequest`. It does not call GetTool because the TIP Session client
does not support that operation. A missing bucket fails closed instead of
silently creating an unmounted Session. Existing Sessions remain unchanged.

## Acceptance criteria

- Complete TOS YAML produces the expected Tool mount configuration and Runtime
  flag in both legacy and managed provisioning.
- Partial TOS YAML fails locally without exposing secret values.
- Two Session IDs produce distinct bucket paths and the same `/data/output`
  local path.
- Disabled configuration performs no extra GetTool request.
- Unit tests cover validation, payload construction, secret redaction, and
  Session request behavior; changed executable lines remain above 95% coverage.

## Review record

The design was checked directly because the repository's optional
`review-spec` skill is unavailable. The contract keeps credentials at the Tool
boundary, uses the SDK's canonical per-session path helper, and introduces no
new public mount knobs. No blocking inconsistency was found.
