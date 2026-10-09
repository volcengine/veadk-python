# Automatic Serverless PostgreSQL for managed MPA creation

[中文版](2026-09-21-deployment-account-pg.zh.md)

> Superseded on 2026-09-23 for the current creation flow by [two manually prepared PG Workspaces](../mpa-space-scoped-resources/2026-09-23-two-pg-workspaces.md): one management Workspace and one shared business Workspace with per-agent databases. The automatic/per-agent Workspace design below is historical and is not being implemented.

## Metadata

- Change ID: `mpa-serverless-pg`
- Created/revised: 2026-09-21
- Status: `draft`; implementation has not started.
- Component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md).
- Predecessor: [managed creation](../mpa-agent-oneclick-provision/2026-09-20-studio-mpa-creation.md).
- User-approved intent: automatically create PG under the account owning VeADK deployment credentials. The user asked to follow ArkClaw for resource granularity; source inspection establishes one business PG Workspace per agent. The detailed VeADK registry adaptation remains under review.

## Background and evidence

`managed/config.py:load_profile` currently requires administrator and shared-registry PostgreSQL URLs. `managed/service.py:provision` initializes that registry before network/APIG creation. `managed/database.py` creates a per-agent database on an existing instance; it does not provision cloud PostgreSQL. Therefore adding a cloud call after registry initialization cannot support an account without PG.

The locally inspected ArkClaw implementation calls AIDAP `CreateWorkspace`, waits for Workspace/main-branch readiness, resolves compute/account/database/endpoint and calls `DescribeDBAccountConnection`. Its `CreateWorkspaceReq` exposes no ClientToken. ArkClaw uses another resource account through STS; VeADK must use its own refreshed, account-verified deployment credentials. Go types are implementation evidence, not proof that this user's account has service access or that every SDK/provider version is compatible.

## Goals, non-goals and scenarios

Goal: a configured fresh account can start managed MPA creation without entering PG credentials. Preserve existing-PG profiles and the current CLI/Studio creation entry points.

Selected business-resource granularity: one VeADK-managed PG Workspace per agent, following ArkClaw. Workspace identity is verified deployment account + region + stable agent ID; only the same agent may reuse it on retry. A different agent receives a separate Workspace, even within the same account and region. Reuse requires matching ownership and recorded creation identity; never pick an arbitrary existing PG. The earlier account-region shared business Workspace proposal is withdrawn.

Non-goals: copying ArkClaw's tenant/resource-account delegation, Debug PG branches, automatic IAM policy/service enrollment, traditional RDS provisioning, automatic deletion/migration of existing PG, multi-host independent bootstrap coordinators, or a live cloud deployment during implementation.

Scenarios:

1. With automatic mode and no managed PG, create it under verified deployment account A, initialize databases, then deploy the agent under A.
2. Retrying the same agent reuses its registered Workspace; a second agent gets a different business Workspace. Both use the independently managed shared registry.
3. An existing-PG profile keeps its current connection and permission behavior.
4. Access denied, account change, unrelated name collision, invalid response, deadline or uncertain create outcome cannot silently continue or allocate another Workspace.

## Requirements and design

- **FR-1 / account:** derive the account from the existing credential verification path before cloud mutation. PG uses the same refreshed credential loader and region as Runtime/network/APIG; do not introduce resource-account assumption or browser-supplied account/AK/SK. Credential rotation across accounts fails. Verify Workspace account/region/ownership before reuse.
- **FR-2 / configuration:** add `managed.postgres.mode: existing | serverless`, default `existing`. Existing mode retains required PG/admin/registry parameters. Explicit `serverless` mode permits their omission and treats the discovered connection as authoritative for managed database fields, including reference/template sources. Reject explicit conflicting PG overrides instead of silently connecting to another instance. Server-only project, engine, compute and endpoint/network settings must be validated against the supported provider contract. Add safe `postgresMode` and a localized resource-plan description to config/UI; no database URLs/passwords. Existing clients may ignore the added field. The web request cannot override cloud account or PostgreSQL credentials.
- **FR-3 / bootstrap:** before connecting to the PG registry, use a durable local SQLite bootstrap store under the existing private state directory. Key business bootstrap by verified account, region and agent ID; key a separately managed registry bootstrap by verified account, region and explicit registry purpose. Persist only creation identity, owner, configuration hash, lifecycle state and provider resource IDs. Mode 0600, no credentials. Use transactional ownership/serialization across CLI and Studio processes sharing the same store. Persist intent before CreateWorkspace and ID immediately after response. A single bootstrap coordinator/state store per account-region is required; independent hosts are outside this version's concurrency guarantee. Bootstrap the independent shared registry first, then create or recover the agent-specific business Workspace. Inject its connection only into that agent’s business database path; the shared registry URL continues to reference the independent management database. Existing per-agent business database naming can remain inside its dedicated Workspace, subject to provider SQL permissions.
- **FR-4 / recovery:** resolve all discovery pages; reject malformed/repeated pagination, multiple owned candidates and ownership conflicts. A create request with an uncertain outcome must reconcile its persisted unique marker through discovery. Because ClientToken support is not established, never blindly retry an uncertain CreateWorkspace or interpret eventual absence as permission to create again. Unrecoverable ambiguity yields an actionable redacted recovery error. A recorded missing/deleted ready Workspace must not trigger a replacement. Pending configuration changes fail explicitly. Preserve original account, mode and bootstrap configuration identity on task retry.
- **FR-5 / connectivity and credentials:** use bounded signed requests to an approved provider endpoint, with transport cleanup and sanitized errors. Resolve only the intended branch/compute/account/database/endpoint. Enforce TLS and verify Studio SQL connectivity, CREATEDB/owner rights and required extensions/initialization before proceeding. Define network/public-access settings explicitly; do not add permissive allowlists or claim a new VPC reaches a private PG automatically. Retrieved credentials stay server-side in memory or the existing required runtime secret configuration, never task JSON, SQLite bootstrap state, browser, logs or checked-in YAML. Redact provider connection response errors.
- **FR-6 / lifecycle:** add observable `postgres_creating`, `postgres_waiting`, `postgres_initializing` stages through the runner allowlist, task storage and both UI locales. Use task deadline plus per-request timeout and bounded polling. Cancellation stops local work and reaps the runner; in-flight cloud completion may still occur. Preserve PG resources and intent on cancellation/failure for reconciliation; no automatic delete. Authentication, failure and empty states remain distinct.
- **FR-7 / compatibility:** old YAML, `managed.version: 1`, existing task rows and legacy `veadk mpa create` retain behavior. `veadk mpa provision --dry-run` remains local and shows a safe PG plan without network or SQL calls. No implicit switch to automatic mode after an existing PG connection failure. Existing agents are not repointed or redeployed. Keep prepared account resources reusable through the existing registry.

Implementation sequence: local config validation → deployment identity → independent shared-registry preparation → agent-scoped durable PG bootstrap/discovery → create if safely absent → wait/resolve business connection → SQL permissions → existing network/APIG/worker/business-database/Skill Space/Runtime flow. Runtime model/image settings must be validated before billable mutations where possible; database permission checks necessarily follow new PG creation. The created PG remains for recovery if later checks fail.

## Contract impact and affected files

Update both `specs/studio-mpa-creation/README.*`: CON-1 configuration, CON-2 preparation, CON-3 identity, CON-6 stages, CON-7 cancellation, CON-8 persistence/security, CON-9 UI; add the PG bootstrap/reconciliation invariant. Preserve legacy provisioning contracts; SDK Agent/Runner, harness and channel protocols are unaffected.

Affected implementation: `veadk/integrations/mpa/managed/{config,service,runner,tasks,diagnostics}.py`, new PG cloud/bootstrap modules; `frontend/server/mpa_creation.py`, `frontend/src/adk/mpaCreation.ts`, creation dialog and both locales. Add focused tests under `tests/integrations/mpa_managed/` and update frontend creation tests. Synchronize managed READMEs, example YAML, CLI help as needed, and generated `veadk/webui/` assets. Do not edit the user's two unrelated pending type-verification documents or enable/change the ignored live profile without a separate concrete operational decision.

## Tasks and acceptance

| Task | Requirement | Acceptance |
| --- | --- | --- |
| T-1 | FR-1–7 | AC-1: record ArkClaw-aligned per-agent granularity; resolve independent registry bootstrap and complete bilingual contract/design review; validate provider request/response schemas before production edits. |
| T-2 | FR-1–5 | AC-2: test-first PG adapter/bootstrap covers account mismatch, rotated credentials, pagination, malformed responses, unknown create result, duplicate processes, ownership collisions, distinct Workspaces for two agents, same-agent retry reuse, registry/business connection separation, restart and missing resources. |
| T-3 | FR-2–7 | AC-3: integrate config/service/task retry snapshot and SQL initialization; existing-mode tests pass; no PG URL needed in automatic mode; no cloud calls in dry-run. |
| T-4 | FR-2,6 | AC-4: localized plan/progress and safe error/cancel/retry states work in the real dialog with isolated APIs. |
| T-5 | FR-1–7 | AC-5: reconcile paired docs/contracts, rebuild assets, run required checks, distinguish simulated verification from actual provider evidence. |

## Verification plan

Start with failing contract/regression tests. Run `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py`, changed-file Ruff/Pyright, `npm --prefix frontend test`, `npm --prefix frontend run build`, `npm --prefix frontend run test:webui-assets`, `npm --prefix frontend run check:i18n`. Run the default two-worker non-smoke Python regression for the shared configuration/orchestration change. Before any authorized commit, fetch/rebase onto the intended remote base and run `uv run --extra dev pre-commit run --all-files` plus unit tests. Real-browser checks cover normal/loading/error/cancellation/retry/keyboard/narrow views with fake APIs; no real cloud allocation. A separately authorized provider smoke must verify actual account ownership, service access, SQL permissions and connectivity before claiming live readiness.

## Risks, open decisions and review record

- Granularity resolved by the user’s instruction to follow ArkClaw: one business Workspace per agent. Remaining design decision is the independent management registry described below; do not reopen business-resource granularity as an arbitrary user choice.
- Unverified live assumptions: current account/region AIDAP access, engine/compute limits, default database account CREATEDB privileges and returned endpoint connectivity. Fail explicitly where unsupported; do not fabricate successful provisioning or relax checks.
- No verified provider create idempotency token: uncertain creates may require operator reconciliation. A local single-coordinator guarantee does not claim distributed cross-host exactly-once behavior.
- Creation allocates billable PG resources; deployment authorization is separate from this code request. No cloud writes, private-profile edits, commits or pushes are included in this design phase.
- `review-spec`, `frontend-design` and `ui-ux-pro-max` are unavailable in the local skill catalog. Direct review checks ownership, compatibility, bootstrap cycle, cancellation, credentials, testability and bilingual equivalence. No new visual layout is planned; reuse the current dialog under `frontend/SPEC.md`.
- 2026-09-21, base `3bbd260a`: code/contract inspection **pass**; implementation/runtime/browser/cloud verification **not_run** (draft design only). Component specs carry a clearly marked proposal for the selected granularity; active behavior remains unchanged until implementation. Detailed design approval remains pending.

## ArkClaw reference findings and registry adaptation (2026-09-21)

Verified reference paths in `arkclaw-team`:

- `pkg/service/multiplayer_agent/create.go:253` allocates an MPA instance identity and stores its own resource fields.
- `pkg/service/multiplayer_agent/create_workflow_executor.go:729` reads `PgWorkspaceID` from that specific instance, calls `CreateWorkspace` only if absent, and persists the result on that instance. `create_workflow.go:334` derives the resource name from its ID.
- `create_workflow_executor.go:775` adds a Debug branch inside the same Workspace; `:831` resolves both connections. This confirms separate Workspaces per agent, not separate Workspaces for formal/debug environments. Debug provisioning is recorded as reference behavior and remains outside this change’s existing single-Runtime scope.
- `pkg/model/model.go:22` initializes ArkClaw’s management database from server configuration independently of the per-agent PG. Its database ownership boundary cannot be replaced with the first created agent’s Workspace.

VeADK’s `SharedAPIGRegistry` explicitly requires every provisioner to use the same PostgreSQL registry, and the Runtime receives `SHARED_APIG_DATABASE_URL`. Proposed adaptation: reuse a configured shared registry; for a fresh account, an explicitly enabled automatic registry mode bootstraps a separate management PG Workspace once per account-region. The business Workspaces remain one per agent and never host the shared registry. Reuse scope, tags, durable keys and plan text distinguish `registry` from `agent` resources. Missing registry configuration must not silently allocate extra PG.

This adaptation needs detailed approval because it changes resource count: fully automatic first creation would prepare one management Workspace plus one business Workspace; subsequent agents add only their own business Workspace. Reusing a configured registry creates no additional management Workspace. This is a VeADK adaptation to its existing shared-APIG contract, not a claim that ArkClaw creates this extra Workspace per account. Do not introduce it as an invisible default or weaken the registry contract. No code, tests, cloud resources, local credentials or existing private YAML changed during this reference review.
