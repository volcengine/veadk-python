# MPA Studio Workload Identity Provisioning

- **Change ID:** `mpa-studio-workload-identity`
- **Created / revised:** 2026-09-20
- **Status:** implemented
- **Chinese:** [2026-09-20-mpa-studio-workload-identity.zh.md](2026-09-20-mpa-studio-workload-identity.zh.md)
- **Component:** [MPA Runtime Provisioning](../../../specs/mpa-runtime-provisioning/README.md)
- **Predecessor:** [MPA Agent One-click Provisioning](../mpa-agent-oneclick-provision/2026-09-10-mpa-agent-oneclick-provision-design.md)

## 1. Background and evidence

`veadk mpa create` currently generates `MPA_AGENT_ID` as `mi-` plus twelve lowercase alphanumeric characters and disables ArkClaw identity startup. The deployed mpa-agent still derives its outbound workload identity as `arkclaw-{CLAW_SPACE_ID}-workload` plus `MPA_AGENT_ID`. In the Studio topology that pool does not exist, so outbound TIP exchange fails even though the Runtime itself is healthy.

The approved Studio convention is one account-and-region scoped pool named `agentkit-studio-workload` and one identity per MPA instance named `{MPA_AGENT_ID}-studio`. The base MPA id remains the database, Runtime, Tool, channel, and observability identity.

## 2. Goals and non-goals

### Goals

1. Generate and validate canonical MPA ids in the form `mi-[0-9a-z]{12}`.
2. Idempotently create or reuse `agentkit-studio-workload` and `{MPA_AGENT_ID}-studio` before other provisioning side effects.
3. Inject explicit workload pool and identity names into the Runtime.
4. Preserve the existing ArkClaw-derived identity behavior for non-Studio mpa-agent deployments through a companion consumer change.
5. Produce actionable, redacted failures for missing Identity permissions.

### Non-goals

- Creating Identity UserPools, clients, groups, or ArkClaw control-plane records.
- Enabling inbound A2A TIP verification; APIG key authentication remains the Studio boundary.
- Automatically migrating already-running Runtimes or deleting unused workload identities.
- Porting the internal bit layout of ArkClaw's Go `ubw/id` generator. VeADK retains its existing secure random source and twelve-character suffix as approved.

## 3. Scenarios and requirements

### Scenario A: new Studio MPA

Given valid cloud credentials and no Studio workload pool, when the operator runs `veadk mpa create`, VeADK creates the shared pool, creates `{MPA_AGENT_ID}-studio`, injects both names, and continues the existing Skill Space, Tool, metadata, and Runtime flow.

### Scenario B: retry or second MPA

Given the pool or identity already exists, the same command reuses exact-name resources. A concurrent create conflict is followed by a read and validation rather than treated as failure.

### Scenario C: insufficient permission

Given credentials without an Identity get/create action, provisioning stops before Tool creation, database writes, or Runtime creation and reports the failed resource and required action without printing credentials.

### Requirements

- **FR-1:** `generate_mpa_agent_id()` returns `mi-` plus twelve lowercase base36 characters. Explicit `--mpa-agent-id` values must match the same canonical form.
- **FR-2:** The workload pool name is the constant `agentkit-studio-workload`; the identity name is `{MPA_AGENT_ID}-studio`.
- **FR-3:** Workload provisioning is get-or-create and exact-name idempotent. `AlreadyExists` is resolved by re-reading the resource. Other errors fail closed.
- **FR-4:** Identity resources are ensured after local input validation and before Skill Space, Tool, PostgreSQL, VeFaaS, or Runtime mutations.
- **FR-5:** `--dry-run` displays the MPA id, pool, identity, and masked Runtime environment without cloud or database calls.
- **FR-6:** Runtime environments contain `MPA_WORKLOAD_POOL_NAME` and `MPA_WORKLOAD_IDENTITY_NAME`. Existing `IDENTITY_STARTUP_ENABLED=false` and `A2A_TIP_VERIFY_ENABLED=false` remain unchanged.
- **FR-7:** The management identity requires `id:GetWorkloadPool`, `id:CreateWorkloadPool`, `id:GetWorkloadIdentity`, and `id:CreateWorkloadIdentity`; authorization failures identify the required action.
- **FR-8:** The companion mpa-agent change uses both explicit names when both are configured, uses the existing ArkClaw derivation when neither is configured, and rejects a partial pair.

## 4. Design and contract impact

### 4.1 VeADK ownership

A focused `veadk.integrations.mpa.mpa_identity` module owns naming and get-or-create orchestration. It reuses additive, pool-aware methods on the existing `veadk.integrations.ve_identity.IdentityClient`, the installed Volcano Engine Identity SDK, and the same management credentials already used by `veadk mpa create`. Existing IdentityClient signatures remain compatible.

The orchestration becomes:

`validate id/input -> ensure pool -> ensure identity -> ensure Skill Space -> ensure Tool -> pre-seed mpa_meta -> provision Runtime -> finalize metadata -> verify`.

Created identity resources are intentionally retained after a later failure so an identical retry converges. The fixed shared pool is never deleted by this command.

### 4.2 Runtime consumer contract

VeADK injects:

```text
MPA_WORKLOAD_POOL_NAME=agentkit-studio-workload
MPA_WORKLOAD_IDENTITY_NAME=mi-xxxxxxxxxxxx-studio
```

The independently versioned mpa-agent must consume the pair. This change is not complete for live TIP exchange until its companion commit is present in the deployed image.

### 4.3 Permissions and security

Management AK/SK remain local control-plane inputs and are never injected into Runtime env. Identity API failures expose action and resource names only. Pool and identity names are non-secret. Runtime workload-token permission remains an execution-role concern and is not broadened by management provisioning.

### 4.4 Compatibility

Generated ids keep their existing twelve-character suffix. Explicit non-canonical ids are rejected for new `veadk mpa create` invocations; existing deployments are unaffected until reprovisioned. Non-Studio mpa-agent deployments retain the legacy derived names when the two new variables are absent.

No HTTP, SSE, database schema, frontend, session, or event contract changes. No additional dependency is required.

## 5. Implementation tasks

- **T-1:** Add canonical id validation and workload naming helpers in `mpa_provision.py`.
- **T-2:** Add the minimal Identity SDK get-or-create module and error mapping.
- **T-3:** Wire identity provisioning and dry-run output into `cli_mpa.py`; report the required action on authorization failure.
- **T-4:** Update Runtime env assembly and the bilingual component spec.
- **T-5:** Add the companion mpa-agent configuration and resolution change.
- **T-6:** Add tests first, run targeted regression, pre-commit, and the required broader Python gate.

## 6. Verification and acceptance

| Requirement | Task | Acceptance criterion | Command | Result |
| --- | --- | --- | --- | --- |
| FR-1, FR-2 | T-1 | AC-1: generated and explicit ids plus derived identity names are canonical | `uv run --extra dev pytest tests/integrations/test_mpa_provision_env.py` | pass; included in the 39-test targeted run |
| FR-3, FR-4, FR-7 | T-2, T-3 | AC-2: create, reuse, race, and authorization failure paths are deterministic and side-effect ordered | `uv run --extra dev pytest tests/integrations/test_mpa_identity.py tests/cli/test_cli_mpa.py` | pass; included in the 39-test targeted run |
| FR-5, FR-6 | T-3, T-4 | AC-3: dry-run is side-effect free and Runtime receives the explicit pair | `uv run --extra dev pytest tests/integrations/test_mpa_provision_env.py tests/cli/test_cli_mpa.py` | pass; included in the 39-test targeted run |
| FR-8 | T-5 | AC-4: the mpa-agent resolves explicit, legacy, and partial-pair cases | companion repository targeted pytest | pass; 47 tests and 100% diff coverage |
| all | T-6 | AC-5: repository pre-commit and affected regression pass | `uv run --extra dev pre-commit run --all-files`; `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | pass for targeted tests and changed-line coverage (39 tests, 100%); broad run reached 4563 passed, 12 skipped, 2 xfailed, then reported 8 optional-dependency failures; after installing `extensions` and `sandbox`, all 13 affected tests passed |
| all | T-6 | AC-6: an authorized isolated account can obtain a workload token using the new names | manual cloud smoke with redacted output | not_run; requires explicit live credentials and deployed companion image |

## 7. Risks and recovery

- Fixed pool creation requires account-level Identity permission. Missing permissions stop before other provisioning mutations.
- A later failure can leave an unused identity. Re-running the same id reuses it; manual cleanup remains an operator action.
- A VeADK Runtime using the new env pair with an old mpa-agent image continues using the legacy names. Release notes and live verification must identify the companion image revision.
- A shared pool concentrates identities in one namespace. Exact canonical MPA ids prevent accidental aliasing; pool capacity monitoring remains an operational concern outside this change.

## 8. Review and delivery record

- User approval: 2026-09-20, approved the two-repository plan and retained the twelve-character suffix.
- Design review: 2026-09-20 direct review against repository requirements; no blocking ambiguity remains. The identity side effect, permission set, idempotency, failure ordering, compatibility, and companion consumer contract are explicit.
- Implementation review: two passes covered naming and API contracts, ordering/idempotency/error handling, secret boundaries, compatibility, and test quality; no open findings remain.
- Verification: VeADK targeted tests passed (39), changed-line coverage is 100%, and the initially missing optional-dependency cases passed after installing the declared `extensions` and `sandbox` extras. The companion mpa-agent targeted tests passed (47), its full coverage gate passed (2818 passed, 21 skipped, 95.05% total), and changed-line coverage is 100%.
- Residual verification gap: AC-6 remains `not_run` because it requires an authorized live account and a Runtime deployed with the companion image.
