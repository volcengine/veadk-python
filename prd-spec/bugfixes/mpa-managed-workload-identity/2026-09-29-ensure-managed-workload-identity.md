# Ensure Workload Identity for Managed MPA Provisioning

- **Change ID:** `mpa-managed-workload-identity`
- **Created / revised:** 2026-09-29
- **Status:** implemented
- **Chinese:** [2026-09-29-ensure-managed-workload-identity.zh.md](2026-09-29-ensure-managed-workload-identity.zh.md)
- **Component:** [MPA Runtime Provisioning](../../../specs/mpa-runtime-provisioning/README.md)
- **Predecessor:** [MPA Studio Workload Identity Provisioning](../../features/mpa-studio-workload-identity/2026-09-20-mpa-studio-workload-identity.md)

## 1. Background and evidence

`veadk mpa create` ensures the shared Studio WorkloadPool and the per-agent
WorkloadIdentity before provisioning. Studio uses the managed `provision()`
path, which does not call that ensure operation. With `managed.from-runtime`,
the reference pool can be inherited while an empty YAML override removes the
identity, and mpa-agent then rejects the partial pair during startup.

## 2. Goals and non-goals

### Goals

1. Apply the existing idempotent Workload Identity ensure operation to managed provisioning.
2. Inject the ensured pool and identity as an inseparable pair for every managed source mode.
3. Prevent a reference Runtime from donating its agent-specific identity.
4. Fail before PostgreSQL, gateway, Worker, or Runtime mutations when identity preparation fails.

### Non-goals

- Changing naming, Identity permissions, UserPool injection, or mpa-agent consumption.
- Deleting identities after a later provisioning failure.
- Migrating existing Runtimes.

## 3. Scenarios and requirements

- **FR-1:** Managed provisioning ensures `agentkit-studio-workload` and
  `{MPA_AGENT_ID}-studio` after account validation and before other provisioning mutations.
- **FR-2:** The ensured pair overrides reference/template values and empty YAML values.
- **FR-3:** A non-empty explicit managed Runtime value that differs from the canonical name is rejected before cloud mutation.
- **FR-4:** Identity API failures preserve the existing redacted, actionable error and prevent downstream mutations.
- **FR-5:** Reference Runtime template extraction excludes both workload identity variables.

## 4. Design and contract impact

The managed service reuses `ensure_studio_workload_identity()` and constructs
`IdentityClient` from the same rotating deployment credentials already used by
the Runtime control plane. The synchronous SDK call runs in a worker thread.
No new dependency or public API is introduced. Empty explicit values mean
"unspecified"; conflicting non-empty values fail closed. Created identity
resources remain for idempotent retry.

## 5. Implementation tasks

- **T-1:** Add a failing managed-service regression for ensure ordering, injection, and downstream blocking.
- **T-2:** Wire the existing ensure helper into managed provisioning and exclude inherited workload identity fields.
- **T-3:** Update the bilingual component contract and run targeted, coverage, pre-commit, and regression checks.
- **T-4:** Create one live MPA from local Studio and verify Runtime, Worker, and TOS mount state.

## 6. Verification and acceptance

| Requirement | Task | Acceptance criterion | Command | Result |
| --- | --- | --- | --- | --- |
| FR-1–FR-5 | T-1, T-2 | AC-1: all managed source modes receive the ensured pair and failures stop downstream work | `uv run --extra dev pytest tests/integrations/mpa_managed` | pass; 390 tests |
| FR-1–FR-5 | T-3 | AC-2: changed Python lines meet at least 95% coverage and repository checks pass | targeted coverage, pre-commit, and affected regression | pass; changed executable lines 100%, full regression 5259 passed, 8 skipped, 2 xfailed |
| FR-1, FR-2 | T-4 | AC-3: a new live MPA has a Ready Runtime and Worker with `/data/output` TOS configuration | local Studio creation and cloud inspection | pass; `mi-6fc92ba155cc4bb28a733fb2`, Runtime `r-yew4qlw5c017agjttpcw`, Worker `t-yew4qkzu9smwrumgn11q` |

## 7. Risks and recovery

The Studio management identity needs the existing Identity get/create actions.
An ensure failure now blocks creation earlier, which is intentional. An identity
created before a later failure is retained and reused on retry. Rollback is the
code revert; no data migration is required.

## 8. Review and delivery record

- User approval: 2026-09-29, approved adding ensure to managed provisioning and requested a live retry.
- Design review: existing naming, helper, credentials, and error contracts are reused; no unresolved interface, security, or compatibility blocker remains.
- Implementation and verification: completed 2026-09-29. Managed provisioning
  ensures and injects the canonical pair before downstream mutation; reference
  identities are excluded. The live Studio task succeeded with a Ready Runtime
  and Worker. The Tool has `agentkit-demo` mounted read-write at `/data/output`.
