# Dev Loop Spec Review: MPA Runtime Integration Hardening

- **Change ID:** `mpa-runtime-integration-hardening`
- **Status:** Approved
- **Date:** 2026-09-13
- **Chinese version:** [2026-09-13-dev-loop-review.zh.md](2026-09-13-dev-loop-review.zh.md)
- **Reviewed design:** [2026-09-12-mpa-runtime-integration-hardening.md](2026-09-12-mpa-runtime-integration-hardening.md)

## Review conclusion

The design is implementable and aligned with the current VeADK/mpa-agent boundaries. No P0/P1 blocker remains. The review covered context consistency, ambiguity, SDD/TDD fit, minimal implementation, compatibility, existing deployments, failure recovery, security, observability, and extensibility.

## Findings and resolutions

| Priority | Finding | Resolution |
| --- | --- | --- |
| P1 | A broad VeADK mode flag could disable unrelated caches. | Use the narrow `APPCENTER_RESOURCE_DISCOVERY_ENABLED` switch and keep native default `true`. |
| P1 | A model-generated `sandbox_task.modelOverride` could bypass the Studio allowlist. | A validated request-scoped model always overrides the tool argument. |
| P1 | The first A2A progress update used `append=true` before the artifact existed. | First successful enqueue creates the artifact; only subsequent events append. |
| P1 | Runtime key injection could leak through dry-run output. | Treat `CODEX_MCP_RUNTIME_API_KEY` as a secret and inject it only server-side during phase two. |
| P2 | Replayed usage snapshots could inflate session totals. | Track source/request snapshots and emit only positive deltas. |
| P2 | Enabling APMPlus could unintentionally expose prompt content. | Enable Runtime tracing while retaining `APMPLUS_TRACE_CONTENT=false`. |
| P2 | Log download could bypass the display bound or sanitization. | Download exactly the server-sanitized current 1,000-line snapshot. |
| P3 | Existing Runtime version 31 cannot prove the new behavior. | Record live verification as blocked until a new image is published and the Runtime is updated. |

## Approval gate

- P0: none
- P1: all resolved
- P2/P3: treatment recorded above
- Result: approved for the existing SDD/TDD implementation and verification workflow.
