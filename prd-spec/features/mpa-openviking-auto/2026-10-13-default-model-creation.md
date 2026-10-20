# Automatic OpenViking preparation for Studio MPA

[中文版](2026-10-13-default-model-creation.zh.md)

Change ID: `mpa-openviking-auto`. Date: 2026-10-13. Status: implemented; live acceptance pending.
Contracts: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), [Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md).

## Evidence, goals and non-goals
Studio currently collects an optional OV URL/resource ID/API Key. The MPA image already registers per-user OV identities using its runtime STS role. A read-only reference inspection shows enterprise READY, model identities/versions but no model API Key/Key ID; the console reports no custom model credentials and enabled limited-time content understanding. This does not prove a new API-created library can use default models. Official Create/Get/Access documentation defines async INIT/READY/FAILED and default-user key retrieval.
Goal: new Beijing Studio MPA requests prepare an independent enterprise OV library without manual connection inputs, using default VLM/Embedding configuration first. BytePlus, general agents, existing tasks, manual CLI configuration and existing Runtimes keep their behavior. No Ark endpoint/key creation, default-key copying, data migration or OV deletion is included. New OV is a retained paid resource; no live creation is implied by implementation approval.

## Requirements and scenarios
- FR-1: Beijing built-in configuration advertises automatic OV. New UI requests persist `openvikingMode: auto`; absence/manual preserves old request semantics. Reject auto outside Volcengine Beijing and combinations of auto/manual connection values before mutation. CLI remains opt-in via managed configuration.
- FR-2: Under the existing authorized deployment lock create one enterprise library using legal hash-derived Name and scoped Description, default project, VLM `doubao-seed-2.0-lite`/`260428`, Embedding `doubao-embedding-vision`/`251215`, and explicit Source/EndpointID Credentials; the resolved Ark key is attached only to the copied wire request. Persist nonsecret intent before dispatch and ResourceID immediately after response. Registered IDs require matching name/description/project/version/models before reuse; deleting/deleted agents cannot create.
- FR-3: Poll INIT to READY within a bounded deadline, fail explicitly on FAILED/invalid status/missing ID/permissions. Obtain default-user key through AccessOpenVikingApiKey, inject URL/resource ID/key/user into Runtime before deployment. No key enters SQLite, registry, results, logs or fixtures. Runtime per-user registration remains the MPA image responsibility.
- FR-4: A failed later deployment reuses the registered library. A proven rejected create permits same-intent retry. Ambiguous create outcome remains blocked rather than blindly creating another library; operator reconciliation of the registered ResourceID is required. Cancellation retains known/unknown resources and stops subsequent operations. Key reads retry only transient failures; creates never automatically retry.
- FR-5: Third step shows automatic preparation and enterprise billing information; no manual fields for new auto requests. Old submitted manual tasks and BytePlus retain fields/validation. Safe localized errors/stages remain visible and retry uses the original mode/identity. Existing layout, TOS controls, keyboard/IME, cancellation and focus behavior are preserved.

## Design and affected files
Add OpenViking options, a signed control-plane adapter and locked resource preparation. Reuse current refreshed account-verified deployment credentials, existing signing helper and diagnostic sink. Only documented CreateOpenVikingCollection/GetOpenVikingCollection/AccessOpenVikingApiKey are used; no undocumented name-discovery API or idempotency token is assumed. Collection and Runtime key lifetimes remain independent. Default model acceptance is an explicitly unverified provider capability; rejection must not silently provision paid Ark endpoints or omit OV.
Affected: managed config/profile/service/runner/tasks/diagnostics; new openviking module; Studio request/client/dialog/locales; focused tests, existing frontend release assets and operator docs. No general generation/chat/deletion or MPA image modification.
The Studio profile advertises availability separately from the execution mode: reading config or calling provision directly does not opt an old request into OV. Only an explicit new request mode or explicit CLI managed setting enables creation. Runtime provisioning keeps its existing environment, ownership and request-hash contracts; the four OV variables are already supported, so no separate Runtime contract change is required.
Deployment credentials require vikingdb CreateOpenVikingCollection/GetOpenVikingCollection/AccessOpenVikingApiKey. Runtime role already includes VikingdbFullAccess for per-user management. Only credentials of the verified deployment account may provision OV. Library bindings remain in mpa_admin_db; no library or memory cleanup is added to Agent deletion.

## Tasks, verification and acceptance
| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1/5 | T-1 mode propagation and UI | AC-1 new auto requests, old/manual/BytePlus unchanged | config/route/task and React tests, browser |
| FR-2/4 | T-2 locked intent and binding | AC-2 same-agent reuse, conflict/unknown/cancel safe | offline adapter/provisioner tests |
| FR-3 | T-3 readiness/key injection | AC-3 four env values, no secret persistence, explicit failures | service/runner/security tests |
| All | T-4 reconcile | AC-4 paired docs, build and required gates | affected Python regression, frontend test/build, Ruff/Pyright, i18n/assets, secret scan |
Actual verification is recorded below. Live smoke requires a separately authorized isolated library and cleanup decision; without it report default-model creation availability as unverified.

## Risks, review and approval
The optional-model-credential API behavior and default-model entitlement may differ from an old console-created library; default-path rejection remains an actionable failure. Enterprise hourly billing starts when ready; provider resources are retained after failure/cancellation/deletion. No published discovery/idempotency contract is available for recovering a lost create response, so safety takes priority over blind retry. External registry/resource edits cannot be transactionally serialized with cloud calls.
Direct review performed because review-spec is unavailable: assessed boundaries, credentials, ownership, timeout/cancellation, ambiguous outcomes, compatibility, testability and language equivalence. User approved default-model-first Beijing implementation on 2026-10-13; BytePlus preservation was explicitly confirmed. No further scope expansion is authorized. The two frontend skills referenced by SPEC were not found at their paths or local skill roots; reuse existing ModalLayout/fields and directly verify Foundation S1-S8 instead of inventing a new design system.

## Implementation review and verification (2026-10-13)

Tested scope: uncommitted OV change on `71175c68636dc5b951e9804eb292d85402511e68`; no user state or cloud resource mutation. Test-first evidence: missing adapter module failed collection; auto-mode UI regression failed while manual fields were present. The implementation now covers mode propagation, account/region rejection, registry locking and ownership, INIT/READY/FAILED, cancellation, create ambiguity, safe errors, secret exclusion, and pre-Runtime environment injection. Review found and corrected two compatibility issues: account verification must precede constructing the OV adapter, and capability advertising must not enable OV for legacy/direct requests.

| Gate | Outcome | Evidence / scope |
| --- | --- | --- |
| `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/frontend/server/mpa/test_runtime_profile_routes.py tests/cli/test_studio_rbac.py` | pass | 1,074 passed; two workers chosen for local resources. |
| `npm --prefix frontend test` | pass | 1,379 Node tests and 79 Vitest tests. |
| `npm --prefix frontend run build` | pass | Matching main/widget release assets regenerated. |
| `npm --prefix frontend run check:i18n` | pass | 2 locales / 21 namespaces. |
| `npm --prefix frontend run test:webui-assets` | pass | 113 packaged files / 350 references. |
| `uvx ruff==0.11.12 check <changed-python-files>` and `format --check` | pass | All 12 changed production/test Python files; pinned repository hook version. |
| `uvx pyright --pythonpath .venv/bin/python <changed-python-files>` | pass | All 12 changed Python files, 0 errors/warnings. |
| `uv run --extra dev pre-commit run gitleaks --files <changed-files>` | pass | Changed source, tests, docs and built assets; no credential findings. |
| Browser fixture | pass | Actual dialog, simulated server only: three steps, no auto OV inputs, localized model rejection, same-request retry, BytePlus manual fields, legacy submitted manual recovery, Escape/focus return, 390×844 layout. Temporary fixture removed; no cloud create calls. Existing interaction tests cover loading/keyboard/IME and terminal-state behavior. |
| Isolated `test_runner_scope_covers_async_worker_events` | fail (pre-existing) | When run alone, existing `.env` initialization logs enter captured stdout and break the test JSON parsing. Reproduced the identical failure against a temporary read-only HEAD source snapshot. Broad suite passes; no unrelated logging/test changes made. |
| Real OV create/key/readiness smoke | not_run | Needs separately authorized paid isolated resource. Old-library reads are not proof of new-library default-model entitlement. |
| Codex/sidecar smoke and coverage gates | not_applicable | No worker/image/harness protocol change. |
| Full repository pre-commit / commit / push | not_run | No commit requested; affected lint, type, secret and runtime-independent checks executed. |

AC-1–AC-4 implementation and offline verification complete. Cloud acceptance remains explicitly pending: if default models are rejected, the task reports an actionable error without creating Ark endpoints or silently omitting OV. Enterprise OV is retained after failure, cancellation or MPA deletion.

### Live finding and source correction

The first user-triggered live request was explicitly rejected with InvalidParameter because its model source was empty. This disproves that omitting Credentials is sufficient. The [approved source correction](../../../prd-spec/bugfixes/mpa-openviking-source/2026-10-13-model-source.md) adds Source/EndpointID and uses the existing resolved Ark key only in the wire payload, with safe recovery for the matching rejected intent. Earlier offline results remain evidence of the initial implementation; current verification is recorded in the correction. No successful corrected live creation has yet been claimed.
