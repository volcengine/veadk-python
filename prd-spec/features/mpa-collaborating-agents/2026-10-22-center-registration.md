# AgentKit A2A Center registration and legacy retirement

Status: accepted design; implementation and verification tracked separately. Date: 2026-10-22. Feature and configuration retirement, risk L3. The user approved both official registration sources, one MPA-to-space association, and deletion of historical manual configurations. This supplements the 2026-10-21 space design and replaces its decision to preserve manual registration. Existing dispatch contracts remain valid.

## Evidence and scenarios

Administrators select a space and register an existing service in Studio. Registration writes to AgentKit, while MPA discovers members dynamically. Registration alone does not prove remote execution, compatibility, or permissions in another account/region.

| ID | Kind | Finding | Evidence | Impact | Verification |
|---|---|---|---|---|---|
| FACT-1 | Verified | Runtime already discovers by space | agentkit-mpa-agent/app/services/a2a_space.py A2ASpaceService | Preserve dispatch and association | Existing space tests |
| FACT-2 | Verified | Studio already signs controlled OpenAPI requests | veadk/cli/cli_frontend.py _agentkit_openapi_post and _require_agent_management | Register server-side | Authorization tests |
| FACT-3 | Official API | CreateA2aAgent supports Runtime and Standard; Standard supports json/url | https://docs.volcengine.com/docs/agentkit/CreateA2aAgent_-_Creates_an_A2A_agent?lang=zh | Use official request fields | Payload tests; separate live acceptance |

## Requirements and scope

| ID | Source | Priority | Trigger | Required behavior | Observable result |
|---|---|---|---|---|---|
| FR-1 | User request | Required | Admin registration | RuntimeId/NetworkType for Runtime; Card JSON or URL for Standard | Center returns an Agent ID |
| FR-2 | User request, FACT-1 | Required | MPA selects space | Store one space association including future members | No local per-Agent copy |
| FR-3 | User request | Required | Runtime upgrade | Delete current MPA legacy configurations, retire CRUD, preserve other MPAs/history | Idempotent cleanup and 410 |
| NFR-1 | Studio AGENTS.md, FACT-2 | Required | Registration API | Admin/Runtime authorization, bounded input, no credential reflection, no automatic retry | Authorization/error/double-click tests |

Non-goals: deploying Runtimes, creating spaces, updating/deleting registered center agents, proxy/VPC wizard, OAuth adaptation, or changing dispatch_a2a_task/Harness terminal semantics. Runtime input accepts an accessible existing Runtime ID; Studio-managed tags must not restrict all account resources. Existing Runtime lists can assist selection, with manual ID entry for other visible resources.

## Design and interfaces

DEC-1: POST /web/a2a-agents?region=... accepts targetRuntimeId, spaceId, and source-specific configuration. Existing Studio server credentials sign CreateA2aAgent; response contains only id. Cards/secrets never enter responses, logs, or browser persistence. Runtime-source registration additionally authorizes the source Runtime. AgentKit checks space access. JSON Card must be an object with nonempty name/url/version. URLs require HTTPS without userinfo; AgentKit fetches them, not Studio. ProjectName follows the selected space and defaults to default when absent; SetDefaultVersion=true. Network public/private is an explicit choice. No new dependencies.

DEC-2: Keep space selection/pagination and add a registration form with progressive source/import fields. Prevent concurrent submission. Cancellation aborts the browser request but may leave a cloud operation submitted. Network/5xx/cancel uncertainty prevents blind retries: refresh the center to reconcile, then let the user explicitly start another registration. Success closes/clears the form and refreshes members; a refresh failure is distinguished from registration failure. Changing space/Runtime cancels stale results and clears form data.

DEC-3: After schema migration, Runtime startup performs scoped idempotent DELETE from mpa_collaborating_agents for configured mpa_id only. Never DROP tables, touch space associations or execution ledgers, or run cleanup in model read tools. A missing table is a no-op; missing identity never deletes. Preserve the shared collaborator_credential_key to avoid orphaning in-flight writes from older replicas during rolling upgrades. Delete legacy business records, not shared keys. Authenticated retired endpoints return 410 legacy_registration_retired and cannot write. Published migrations remain unchanged.

## Failure, security, migration and rollback

Invalid bodies return 422; access denial 401/403/404. Cloud/network errors are sanitized. A successful create means accepted registration, not verified execution. Double clicks issue one request. Timeouts never switch identity, retry automatically, or bind another space. Deleted legacy data cannot be automatically restored: operators should use existing DB backups before upgrade. Binary rollback does not restore rows, and old configuration requires re-entry. Keep table structure for migration compatibility. Studio server and Runtime cloud identities should use the same account; mismatches fail through space/permission checks rather than silent fallback.

## Acceptance, tasks and traceability

| ID | Given | When | Then | Method | Environment |
|---|---|---|---|---|---|
| AC-1 | Accessible space and Runtime | Runtime source | Exact source-specific CreateA2aAgent fields | Backend tests | Mocked cloud |
| AC-2 | Card JSON or HTTPS URL | Standard source | Correct ImportType; reject invalid/oversized input | Backend tests | Local |
| AC-3 | Non-admin or inaccessible Runtime | Create | No cloud write | Backend tests | Local |
| AC-4 | Current/foreign legacy rows, spaces and ledger | Repeated cleanup | Delete current legacy data only; preserve shared key while needed | Runtime tests | SQLite; separate real PG |
| AC-5 | Form, timeout/cancel | Submit/switch/retry | No stale state, automatic duplicates, or IME submit | React tests/browser | Local |
| AC-6 | Retired endpoint | Old client request | Authenticate then 410; no writes | Runtime tests | Local |

| Requirement | Design | Acceptance | Verification | Document coverage |
|---|---|---|---|---|
| FR-1 | DEC-1/2 | AC-1/2/5 | Python/React/browser | Covered |
| FR-2 | DEC-1 | Existing space regression | test_a2a_registry_collaborators.py | Covered |
| FR-3 | DEC-3 | AC-4/6 | Cleanup/API tests | Covered |
| NFR-1 | DEC-1/2/3 | AC-2/3/5/6 | Boundary tests | Covered |

Sequence: contract and cleanup/API tests, registration route/UI, regression/build, two-pass review and delivery. Risk: official AgentCard field wording is ambiguous; use serialized JSON aligned with GetA2aAgent. Actual cloud creation needs separate acceptance; mocked payload tests do not prove it. Browser verification uses deterministic service responses without live writes. No deployment or real cloud creation is authorized by this request.

## Design review

Feasible after resolving global deletion to current-MPA scope, preserving published migrations, keeping cleanup out of reads, preventing automatic create retries, and reusing administration boundaries. Space bindings remain intact. No remaining user scope decision; live cloud creation, real PG cleanup and release must be reported separately and remain unexecuted.

## Alternatives, release and risks

DEC-4: Compare retaining local per-Agent registration, creating center records from Runtime, and signing center creation in Studio. Choose Studio to reuse control-plane credentials and the administration boundary without adding create permissions to every Runtime. Existing Runtime discovery/dispatch permissions remain unchanged. Reassess account consistency if cloud identity becomes per-user.

| ID | Trigger | Probability/impact | Mitigation | Signal | Recovery |
|---|---|---|---|---|---|
| RISK-1 | Create times out after acceptance | Medium/duplicates | No automatic retry; refresh first | UI uncertain | Admin reconciles center IDs |
| RISK-2 | Rollback after deleting legacy data | Medium/no automatic restore | Existing backup before rollout; current MPA only | deleted_count | Restore backup or register again |
| RISK-3 | Official API differs from documentation | Medium/create rejection | Payload tests and separate cloud acceptance | Sanitized error type | Existing console registration remains |

Release order: operators back up legacy configuration, upgrade Runtime and verify scoped cleanup, then publish Studio assets. Canary one Runtime, validate all three inputs, center ID readback and existing dispatch before expanding. Roll back binaries on failure; restore data only from backups, never create replacement resources automatically. Logs contain error type, region/space ID and deletion count, not bodies or exception text. No new mandatory performance threshold.

## Implementation and local verification (2026-10-22)

Implemented both sources, source-specific validation, same-space refresh, credential masking, unknown-outcome handling, and removal of the legacy UI. Runtime retirement is implemented in agentkit-mpa-agent; live data is not deleted until that Runtime upgrades and starts. The selected space ProjectName is forwarded; absent metadata defaults to default. Existing user package-lock.json changes remain untouched.

| Check | Result | Scope/limitations |
|---|---|---|
| Registration and authorization tests | 23 passed | Mocked cloud; no actual CreateA2aAgent |
| Runtime API/cleanup/space tests | 40 passed | SQLite; real PG lock path not run |
| Runtime affected module line coverage | 83/86 (96.51%) | Combined line/branch display 94%; not whole-app coverage |
| Proxy single-file regression | 129 passed | Mixed run has two provider/region cases failing; tracked separately |
| npm test | Node suite plus 156 Vitest cases passed | Success/failure/empty/cancel/IME/keyboard/focus and refresh failure |
| Build / assets | pass; 114 files, 351 references | Generated veadk/webui updated, not deployed |
| i18n | 2 locales, 22 namespaces consistent | Both languages |
| TypeScript | pass | tsc --noEmit |
| New backend module/tests Pyright | 0 errors | Existing Studio environment |
| CLI whole-file Pyright | 37 errors | Removing the new mount gives identical 37 diagnostic messages |
| Ruff | pass | Changed Python files |
| Browser | pass with simulated API | Registration success refresh, JSON error/masking, denied/unknown outcome, menu Escape/focus; no overflow at 390px |
| Secret scan | Project rules pass; one baseline vendor false positive with default rules | 21.73 MB including assets; Lexical anchor/focus.key expression matches in old HEAD artifact too; no rule bypass |

Two-pass self-review fixed shared-key retirement concurrency, Select Escape propagation and React initialization order. The JSON review evidence ledger validator passes. No independent review agent was used. Runtime full frozen-source verification is recorded in the paired Runtime repository report; deployment readiness is separate from these local checks. No cloud creation, live PG cleanup, image release or deployment occurred. Update both Studio and Runtime before live acceptance.

### Final Runtime and mixed-regression evidence

Frozen Runtime make test: 10366 passed, 304 skipped, one scheduled Worker baseline failure; source fingerprints before/after match. All 475 production/script Python files match the delivery tree; three additional management-route tests passed separately without production changes. Studio mixed regression: 150 passed, two provider/region assertions failed; removing only the new CLI registration mount reproduces the same two failures in the same mixed run. Both current and counterfactual proxy-only runs pass 129 cases. Whole-file CLI Pyright also has the same 37 messages with/without the mount. These are explicitly retained verification limits, not green full gates. No release or live data cleanup occurred.
