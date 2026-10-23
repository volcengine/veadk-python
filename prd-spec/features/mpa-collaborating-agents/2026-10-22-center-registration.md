# AgentKit A2A Center registration and legacy retirement

[中文版](2026-10-22-center-registration.zh.md)

Status: accepted design; implementation and verification tracked separately. Date: 2026-10-22; documentation reconciled 2026-10-23. Feature and configuration retirement, risk L3. The user approved both official registration sources and one MPA-to-space association. The original startup-cleanup proposal was cancelled: retire manual registration APIs and UI while retaining historical records. This supplements the 2026-10-21 space design and replaces its decision to preserve manual registration. Existing dispatch contracts remain valid.

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
| FR-3 | Confirmed scope correction | Required | Runtime upgrade | Retire legacy CRUD without startup deletion or migration; preserve existing records, other MPAs and history | Authenticated 410; retained data unused for discovery/dispatch |
| NFR-1 | Studio AGENTS.md, FACT-2 | Required | Registration API | Admin/Runtime authorization, bounded input, no credential reflection, no automatic retry | Authorization/error/double-click tests |

Non-goals: deploying Runtimes, creating spaces, updating/deleting registered center agents, proxy/VPC wizard, OAuth adaptation, or changing dispatch_a2a_task/Harness terminal semantics. Runtime input accepts an accessible existing Runtime ID; Studio-managed tags must not restrict all account resources. Existing Runtime lists can assist selection, with manual ID entry for other visible resources.

## Design and interfaces

DEC-1: POST /web/a2a-agents?region=... accepts targetRuntimeId, spaceId, and source-specific configuration. Existing Studio server credentials sign CreateA2aAgent; response contains only id. Cards/secrets never enter responses, logs, or browser persistence. Runtime-source registration additionally authorizes the source Runtime. AgentKit checks space access. JSON Card must be an object with nonempty name/url/version. URLs require HTTPS without userinfo; AgentKit fetches them, not Studio. ProjectName follows the selected space and defaults to default when absent; SetDefaultVersion=true. Network public/private is an explicit choice. No new dependencies.

DEC-2: Keep space selection/pagination and add a registration form with progressive source/import fields. Prevent concurrent submission. Cancellation aborts the browser request but may leave a cloud operation submitted. Network/5xx/cancel uncertainty prevents blind retries: refresh the center to reconcile, then let the user explicitly start another registration. Success closes/clears the form and refreshes members; a refresh failure is distinguished from registration failure. Changing space/Runtime cancels stale results and clears form data.

DEC-3: Runtime startup does not delete or migrate legacy records in mpa_collaborating_agents. Retained records are not used for discovery or dispatch. Preserve table structure, published migrations, space associations, execution ledgers and the shared collaborator_credential_key. Authenticated retired endpoints return 410 legacy_registration_retired and cannot write. The original startup-cleanup proposal is superseded; any future data cleanup requires separate approval.

## Failure, security, migration and rollback

Invalid bodies return 422; access denial 401/403/404. Cloud/network errors are sanitized. A successful create means accepted registration, not verified execution. Double clicks issue one request. Timeouts never switch identity, retry automatically, or bind another space. Upgrade and binary rollback do not themselves delete legacy records; retention does not restore legacy registration support in the upgraded Runtime. Keep table structure for migration compatibility. Studio server and Runtime cloud identities should use the same account; mismatches fail through space/permission checks rather than silent fallback.

## Acceptance, tasks and traceability

| ID | Given | When | Then | Method | Environment |
|---|---|---|---|---|---|
| AC-1 | Accessible space and Runtime | Runtime source | Exact source-specific CreateA2aAgent fields | Backend tests | Mocked cloud |
| AC-2 | Card JSON or HTTPS URL | Standard source | Correct ImportType; reject invalid/oversized input | Backend tests | Local |
| AC-3 | Non-admin or inaccessible Runtime | Create | No cloud write | Backend tests | Local |
| AC-4 | Current/foreign legacy rows, spaces and ledger | Runtime startup | No legacy-data cleanup or migration; preserve records and shared key; discovery/dispatch use the bound space | Startup/source inspection and existing space tests | Local; no live data writes |
| AC-5 | Form, timeout/cancel | Submit/switch/retry | No stale state, automatic duplicates, or IME submit | React tests/browser | Local |
| AC-6 | Retired endpoint | Old client request | Authenticate then 410; no writes | Runtime tests | Local |

| Requirement | Design | Acceptance | Verification | Document coverage |
|---|---|---|---|---|
| FR-1 | DEC-1/2 | AC-1/2/5 | Python/React/browser | Covered |
| FR-2 | DEC-1 | Existing space regression | test_a2a_registry_collaborators.py | Covered |
| FR-3 | DEC-3 | AC-4/6 | Startup/source inspection and retired-endpoint tests | Covered |
| NFR-1 | DEC-1/2/3 | AC-2/3/5/6 | Boundary tests | Covered |

Sequence: contract and retired-endpoint tests, registration route/UI, regression/build, two-pass review and delivery. Risk: official AgentCard field wording is ambiguous; use serialized JSON aligned with GetA2aAgent. Actual cloud creation needs separate acceptance; mocked payload tests do not prove it. Browser verification uses deterministic service responses without live writes. No deployment or real cloud creation is authorized by this request.

## Design review

The original review assessed scoped startup cleanup; that proposal was subsequently cancelled. The reconciled design preserves legacy records and published migrations, prevents automatic create retries, and reuses administration boundaries. Space bindings remain intact. No remaining user scope decision; live cloud creation and release must be reported separately and remain unexecuted. Legacy-data cleanup is outside this design.

## Alternatives, release and risks

DEC-4: Compare retaining local per-Agent registration, creating center records from Runtime, and signing center creation in Studio. Choose Studio to reuse control-plane credentials and the administration boundary without adding create permissions to every Runtime. Existing Runtime discovery/dispatch permissions remain unchanged. Reassess account consistency if cloud identity becomes per-user.

| ID | Trigger | Probability/impact | Mitigation | Signal | Recovery |
|---|---|---|---|---|---|
| RISK-1 | Create times out after acceptance | Medium/duplicates | No automatic retry; refresh first | UI uncertain | Admin reconciles center IDs |
| RISK-2 | Retained legacy records mistaken for active registrations | Medium/stale configuration confusion | Document retirement and bound-space discovery | Authenticated 410; center member list | Register the intended service in AgentKit Center |
| RISK-3 | Official API differs from documentation | Medium/create rejection | Payload tests and separate cloud acceptance | Sanitized error type | Existing console registration remains |

Release order: upgrade Runtime and verify retired endpoints and bound-space discovery, then publish Studio assets. Canary one Runtime, validate all three inputs, center ID readback and existing dispatch before expanding. Roll back binaries on failure; never delete legacy data or create replacement resources automatically. Logs contain error type and region/space ID, not bodies or exception text. No new mandatory performance threshold.

## Implementation and local verification (2026-10-22)

Implemented both sources, source-specific validation, same-space refresh, credential masking, unknown-outcome handling, and removal of the legacy UI. Runtime endpoint retirement is implemented in agentkit-mpa-agent; upgrading and starting it does not delete legacy data. The selected space ProjectName is forwarded; absent metadata defaults to default. Existing user package-lock.json changes remain untouched. The following results are historical evidence from 2026-10-22; the cleanup-related result predates cancellation and does not verify current startup behavior.

| Check | Result | Scope/limitations |
|---|---|---|
| Registration and authorization tests | 23 passed | Mocked cloud; no actual CreateA2aAgent |
| Runtime API/cleanup/space tests (superseded cleanup proposal) | 40 passed historically | SQLite; real PG lock path not run; not current cleanup acceptance |
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

### Documentation reconciliation (2026-10-23)

The user approved correcting the stale cleanup description and committing/pushing this documentation-only change to PR #1182. Direct review reconciled FR-3, DEC-3, AC-4, release guidance and both component-spec languages with the current Runtime startup and retired-endpoint implementation. No runtime behavior or public interface changes; no new PRD is required for this correction. Current verification is recorded below; historical results above are not rerun evidence.

Scope: the four documentation files in this correction, based on PR head `846c4005` after fetching both remotes and rebasing with merge preservation onto `upstream/main` (no base changes required).

- pass: paired-language review, requirement/acceptance identifiers, relative links and `git diff --check`.
- pass: `uv run --extra dev pre-commit run --all-files`, including Ruff and secret scanning.
- pass: `uv run --extra dev pytest -q tests/cli/test_a2a_center_registration.py tests/cli/test_a2a_center_actions.py tests/test_mpa_collaborator_proxy_policy.py` — 95 passed, two dependency deprecation warnings.
- not_run: full regression suite, frontend build/browser and live cloud checks; documentation-only correction, no production code, tests or assets changed. Runtime startup was inspected as source evidence; it was not exercised in a live deployment.
