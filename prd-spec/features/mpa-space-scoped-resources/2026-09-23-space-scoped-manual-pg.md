# Space-scoped MPA resources and pre-created AIDAP PostgreSQL

> Superseded by [two PG Workspaces](2026-09-23-two-pg-workspaces.md): one management Workspace and one shared business Workspace with per-agent databases. The per-agent Workspace/Space-selector proposal below is historical.

[中文版](2026-09-23-space-scoped-manual-pg.zh.md)

- Change ID: `mpa-space-scoped-resources`
- Date: 2026-09-23
- Status: proposed; implementation decisions about Space selection and PG credential references are pending.
- Contracts: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), [MPA Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md).
- Supersedes the automatic business-Workspace path proposed in [automatic PG design](../mpa-serverless-pg/2026-09-21-deployment-account-pg.md) for this creation flow.

## Background and evidence

Current VeADK uses `account_id + region` for `mpa_account_network` and `mpa_account_apig`, then creates a logical database per MPA on the administrator PG host. `frontend/server/mpa_creation.py` stores only nonsecret PG host/port and requires that they match one server administrator URL. There is no Claw Space ID in the Studio create request. The current `agentkit-mpa-agent` image also looks up its shared APIG registry by account and region, so changing VeADK alone cannot guarantee Space isolation.

The locally inspected `arkclaw-team/pkg/service/multiplayer_agent/quota.go` resolves an MPA's `SpaceID` and queries `claw_space_application_conf` for that Space's `apig_instance_id`. Its create workflow stores a PG Workspace ID on each MPA. The reference establishes the intended sharing boundary; this change does not depend on the ArkClaw database or service at runtime.

## Goals, non-goals and scenarios

Create or reuse one VPC/subnet and APIG/IM Gateway per verified account, region and logical Space ID. Keep each MPA's Runtime, worker, Skill Space, routes and pre-created AIDAP business PG Workspace independent. A shared Studio registry PG remains deployment-scoped and is not an agent's business Workspace. The PG step must link to the [AIDAP console](https://console.volcengine.com/aidap/region:aidap+cn-beijing/).

Two MPAs in the same Space reuse the same VPC/APIG but use different business Workspaces. Two Spaces in the same account and region must never be assigned the same managed VPC/APIG just because the account matches. Retrying an MPA uses its original Space and PG Workspace. Existing deployments continue to resolve their registered gateway and database during migration.

Non-goals: creating or deleting AIDAP PG Workspaces; importing ArkClaw's `claw_space_application_conf`; changing generic Studio agents; live resource creation as part of tests.

## Requirements and design

- **FR-1 — Space identity:** Studio creation must choose an existing, server-authorized logical Space. Validate the Space against the deployment account and region before cloud mutation. Persist it with request identity, task and deployment record. Set the Runtime's `CLAW_SPACE_ID` to the selected value, not an account-derived fallback. A retry that changes Space fails.
- **FR-2 — shared resources:** Key network/APIG records, locks, stable names and ownership markers by account, region and Space. Verify explicit VPC/subnet/APIG adoption against the chosen Space. Preserve old account-scoped records for existing agents; do not silently reassign an existing gateway or overwrite a legacy row.
- **FR-3 — runtime contract:** The deployed `agentkit-mpa-agent` must resolve the same Space-scoped gateway. Update its lookup contract and image before enabling this flow; otherwise block creation with an actionable compatibility error. Do not expose registry write credentials to Runtime beyond its existing contract during this change.
- **FR-4 — manual PG:** The operator creates one AIDAP business Workspace per MPA before submitting creation. The server resolves its connection and credentials from an administrator-managed secret reference bound to that MPA; the browser/task payload contains only nonsecret Workspace identity and host/port. Verify the Workspace is reachable and distinct from the registry and other agents' Workspace IDs. Record Workspace ID and host without secrets. Do not create a replacement Workspace on retry or failure.
- **FR-5 — compatibility and failure:** Existing agent records remain pinned to their original network/APIG/PG and are not migrated by opening the dialog. Empty, conflicting, missing, rotated or unreachable resource choices fail before paid cloud mutations where possible. Cancellation preserves resources and binding for same-ID retry. Surface safe errors without URLs, passwords or provider response bodies.
- **FR-6 — UI and docs:** Keep the three-step wizard. Identify the selected Space in basics and the manually created AIDAP Workspace on the PG step. Explain Space-level sharing and per-agent PG. Update English/Chinese copy, operator configuration examples, contracts and generated web assets together.

## Affected files and tasks

Expected VeADK areas: `veadk/integrations/mpa/managed/{config,registry,database,network,gateway,service,runtime,runner,tasks}.py`, Studio create API/types/dialog/i18n, tests, operator guide and generated assets. The independent `agentkit-mpa-agent` registry/client contract requires a coordinated change and image release.

1. Resolve the pending choice of Space catalog/selection and server-side per-agent PG credential references; review bilingual contracts and migration before production changes.
2. Write failing tests for two Spaces in one account, two agents in one Space, PG Workspace uniqueness, retry, legacy records, runtime gateway lookup and safe errors.
3. Implement configuration, API, registry, orchestration and runtime integration without weakening ownership checks.
4. Verify targeted tests, frontend build/browser cases, shared regressions and generated assets. Run a separately authorized isolated cloud smoke only if available.

## Risks and acceptance

The current Runtime image can recreate or read an account-scoped gateway; a VeADK-only change is unsafe. The existing shared registry schema has account-region primary keys and needs additive migration or new tables. A manually created Workspace may be private to a different VPC; verify connectivity rather than assuming it. Never store PG passwords in browser storage, task SQLite, deployment records, source or logs.

Acceptance: same-Space agents share exactly the verified VPC/APIG; different Spaces do not; each new MPA uses its own pre-created PG Workspace; the shared registry remains separate; repeated creation keeps original bindings; old agents remain usable; failures do not silently allocate replacement resources. Verification status on 2026-09-23: AIDAP dialog link test `pass`; all new architecture and live checks `not_run` pending design decisions and implementation.
