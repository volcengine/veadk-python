# Change: MPA AgentKit P0 productionization

## Why

AgentKit Studio can discover MPA Runtimes, and `agentkit-mpa-agent` already provides Session, A2A, worker delegation, lifecycle control, and diagnostics. The current system does not yet provide one authoritative Agent/Profile management path, durable cross-system Agent operations, server-owned Session execution configuration, crash-safe Turn acceptance, whole-Turn pause/continuation, or a verified Runtime lifecycle.

## What changes

Deliver six serial, independently reversible slices:

1. **M0 — executable foundation**
   - MPA Profile request/response fixtures and a typed Runtime adapter
   - live OAuth-bearer/TIP identity and Agent write-path proof
   - PostgreSQL 16 integration lane and deterministic fault injection
   - cross-repository compatibility manifest/runner
   - isolated browser scenario harness
   - authorized live E2E runner and zero-residue cleanup
2. **S1 — Agent creation to first chat**
   - BFF Agent API adapter and durable lifecycle operation
   - AgentKit-mode bootstrap/readiness
   - Runtime Profile projection and operation ledger
   - deterministic model and Worker smoke
   - minimum MPA creation/progress UI
3. **S2 — Session versioning**
   - server-owned execution-config revisions
   - resource validation and Turn freeze
   - explicit MPA Profile-revision upgrade
   - two-client CAS UI
4. **S3 — crash-safe run and refresh recovery**
   - durable Turn/dispatch outbox
   - run idempotency and recovery
   - persistent SSE cursor replay and terminal fencing
5. **S4 — whole-Turn lifecycle**
   - primary/worker participant registry
   - pause barrier and generation handling
   - lease-aware resume and explicit continuation
6. **S5 — management and release closure**
   - `MpaAgentView` and page isolation
   - Runtime update/release/delete/rollback
   - Debug/Trace correlation
   - shared CLI client and commands
   - secret-reference migration
   - browser, compatibility, performance, regression, and live gates

## Scope boundaries

- Studio/BFF is the accepted MPA Profile authoring boundary; mpa-agent is the immutable executable Profile-revision authority. Managed Agent is outside P0.
- `agentkit-mpa-agent` is the sole business Session/Turn authority. AgentKit Managed Agent Session is not created in P0.
- VeADK Studio/BFF owns presentation and orchestration, not execution state.
- The browser calls VeADK BFF; BFF validates the existing Studio Agent draft, forwards the validated identity, and applies the normalized Profile to mpa-agent. No Managed Agent control-plane request is part of P0.
- `mpa-codex-worker` remains unchanged unless M0 proves an actual protocol gap.
- No ArkClaw data migration or runtime fallback.
- No MPA template, expert, review/install, Resource Library, Search, scheduled-task, Feishu, or website-integration work.

## Compatibility

Use the PRD compatibility matrix. Runtime A2A capability and Codex Worker protocol are separate dimensions. Unlisted combinations are unsupported. Schema expansion precedes dual-readable code, which precedes new writes. Incompatible rollback is rejected before mutation.

## Verification

The authoritative plans are:

- [Functional verification Cases](../../../prd-spec/features/mpa-p0-productionization/2026-09-15-functional-validation-cases.md)
- [Browser verification runbook](../../../prd-spec/features/mpa-p0-productionization/browser-cases.md)

Every Task references at least one VC. Mock, in-memory, PostgreSQL, browser, and live-cloud evidence remain separate and cannot substitute for each other.

## Delivery gate

M0 is a hard feasibility gate. S1 through S5 are serial; each slice must pass its own Cases and continuous security Cases before the next begins. The change is complete only when every P0/P1 Case is `pass`, both code-review rounds pass, E2E is green, and documentation is reconciled with implementation.
