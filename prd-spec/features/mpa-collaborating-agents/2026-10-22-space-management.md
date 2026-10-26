# Collaborator layout and A2A space creation

[中文版](2026-10-22-space-management.zh.md)

Change ID: mpa-space-management. Date: 2026-10-22. Status: implemented. Predecessor: [Center registration](2026-10-22-center-registration.md). Contract: [MPA collaborating Agents](../../../specs/mpa-collaborating-agents/README.md).

## Evidence, scope and scenarios

A2ACenter currently places binding, registration and member content in one vertical flow with identical 16px spacing. The user approved separate binding and member areas and requested AgentKit space creation. Existing local Center work is preserved. The official [CreateA2aSpace API](https://docs.volcengine.com/docs/86681/2249657), read on 2026-10-22, accepts Name, optional ProjectName and IntentEnabled and returns Result.Id. Cloud creation has not been tested live.

FR-1: Place space selection/binding/disconnection in “Space binding”; place registration, refresh and the member list in “Space members”. Use separate semantic sections, 32px between groups, shared left/right alignment, wrapping actions and existing theme tokens/fonts. Registration identifies its destination. Retain existing loading/error/empty/CAS and registration behavior.

FR-2: Add “New space” beside the space selector, including when there are no spaces. The inline form collects name, project (default default), and semantic search (default false). Creating a space selects it and refreshes its members, but requires a separate explicit bind. The selected new space remains visible even if omitted from a paginated/eventually consistent list. Success with failed refresh is still creation success.

FR-3: POST /web/a2a-spaces?region=... accepts targetRuntimeId, name, projectName (default default), intentEnabled (default false). Existing Studio admin and target Runtime authorization run before cloud writes. Studio invokes CreateA2aSpace with Name, ProjectName, IntentEnabled using existing signed cloud identity and returns only {id}. No Runtime API or deployment change. Name/project are trimmed nonempty strings up to 128 characters without control characters (Studio policy, not an asserted provider limit). Reject unknown fields and non-boolean intentEnabled. Body limit 4096 bytes. Provider denial is sanitized; ambiguous failures return 502 with an outcome-unknown code and never retry automatically.

FR-4: Prevent concurrent creates, respect IME, focus the form on open and return focus on close. Cancel/unmount abort the browser request, never claim cloud rollback; cancel during submission or unknown outcome locks mutations until refresh. Runtime/region changes discard stale responses. Read-only refresh never performs creation. No browser credential persistence or raw provider errors.

Non-goals: space editing/deletion, tags management, Runtime creation, automatic binding, dispatcher/Harness changes, cloud deployment, live cloud resource creation during verification. SDK, dependencies and generated projects are unaffected.

## Design and alternatives

Keep the existing AgentWorkspace detail shell and Button/Select/FormLabel/InputWithTailIcon/Checkbox primitives. CardLayout forces an unrelated icon/close action, so use two semantic sections within the existing shell rather than nesting another page layout. Reuse collaborators form styling, add only group/header/selector container spacing. Avoid additional tabs: selection and members need to remain visible together. No new dependency, icon, font or palette. Use the existing 14px text and studio text/border tokens.

Extend frontend/server/a2a_center.py with the space route; add the client/type/response parser to adk/client.ts and adk/a2aSpace.ts. A2ASpaceCreation owns submit/abort/uncertain state; A2ACenter owns selection, binding and list refresh. One shared mutation gate prevents space creation and registration/binding overlapping. Unknown creation outcomes do not auto-retry. New space identity/name/project are transient UI state; the cloud remains authoritative. Restore focus only after the form closes and the parent stops being busy. Unmounts cannot apply late responses.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1 | T-1 group Center and update both locales | AC-1 binding and registration have distinct accessible regions and actions | frontend/tests/collaboratingAgents.test.tsx; browser desktop/narrow |
| FR-2 | T-2 create form/client and selection refresh | AC-2 empty/paginated space lists permit creation; success never writes binding | UI tests and mocked browser |
| FR-3 | T-3 validated authorized server route | AC-3 exact payload, input bounds, auth denial, sanitized failures, no retries | tests/cli/test_a2a_center_registration.py |
| FR-4 | T-4 async and keyboard tests | AC-4 no duplicate creates/stale writes; cancel/unknown require reconciliation; focus/IME work | React tests and browser |
| All | T-5 reconcile bilingual docs/build/review | AC-5 tests/build/i18n/assets/Ruff/Pyright and diff checks recorded | commands below |

Test-first: add failing focused UI/API tests before production edits. Gates: uv run --extra dev pytest tests/cli/test_a2a_center_registration.py; npm --prefix frontend test; npm --prefix frontend run build; npm --prefix frontend run check:i18n; npm --prefix frontend run test:webui-assets; uv run ruff check frontend/server/a2a_center.py tests/cli/test_a2a_center_registration.py; repository-local Pyright for those Python files; real browser against mocked API without cloud writes. No commit requested; pre-commit and branch synchronization are not triggered by this task.

## Review, approval, risks and delivery

User approval: “帮我改下” accepts the proposed upper binding/lower member layout; “然后也加上agentkit这里新建空间的功能” authorizes the creation capability. Review-spec skill unavailable; direct review checks bilingual scope, API fields, authorization, bounds, no retry, cancel/late-response behavior, explicit binding, and testability. No design blockers. Component contract updated in both languages before implementation.

Risks: provider acceptance may precede a timeout; UI requires read reconciliation before another attempt. Lists may lag or paginate away a new item; keep the confirmed ID selectable without claiming listed status. Studio credentials and Runtime identity must have consistent account/region access; no fallback across providers/accounts. Rollback the UI/server change without deleting created spaces. Live provider integration remains an explicit unverified area; local tests simulate it.

Verification status: not_run before implementation. Date/scope: 2026-10-22, incremental space-management changes over the pre-existing dirty Center implementation. No commit, push or deployment authorized by this task.


## Final verification (2026-10-22)

All T-1 through T-5 and AC-1 through AC-5 are complete for the incremental local implementation. Test-first evidence: before implementation, 18 new Python cases failed because the route did not exist, and 6 UI cases failed because the new controls/regions did not exist. Additional tests cover explicit project/search selection, empty-list creation and permission correction. Review corrected closing-focus recovery: when an uncertain result disables the opener, focus moves to Refresh; mutually exclusive forms cannot steal focus. Selector container width matches the existing 372px Select primitive without overriding it. No new component style exception was introduced.

| Check | Result | Evidence and scope |
| --- | --- | --- |
| uv run --extra dev pytest tests/cli/test_a2a_center_registration.py tests/test_mpa_collaborator_proxy_policy.py -q | pass | 41 passed; mocked cloud, no live resources |
| npm --prefix frontend test | pass | 1389 Node tests and 164 Vitest cases, 11 files |
| focused collaboratingAgents.test.tsx | pass | 17 cases including final focus/IME/cancel/unknown/error and no automatic binding |
| npm --prefix frontend run build | pass | matching veadk/webui assets; existing chunk-size warning |
| npm --prefix frontend run check:i18n | pass | 2 locales, 22 namespaces |
| npm --prefix frontend run test:webui-assets | pass | 114 packaged files, 351 internal references |
| frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json | pass | no diagnostics |
| pre-commit ruff-check and ruff-format for a2a_center.py and test_a2a_center_registration.py | pass | used repository hook environments; standalone uv run ruff is unavailable in the project environment |
| Pyright with .venv/bin/python for the two Python files | pass | 0 errors/warnings; existing adjacent-repository Pyright executable, project interpreter |
| Browser | pass | isolated real browser with simulated API: desktop grouping, creation selects without binding, empty state, permission denial and uncertain-write lock; keyboard focus and 390px narrow view checked |
| git diff --check and paired-document checks | pass | scoped document paths, IDs and translated contracts aligned |
| Live local route discovery | pass | 127.0.0.1:8000/openapi.json includes POST /web/a2a-spaces; no create request sent |
| Secret scan | pass | gitleaks dir with repository .gitleaks.toml over scoped source/docs; existing allowlist excludes tests and generated web assets |
| Full Python regression / real cloud creation | not_run | route-only change covered by targeted API/policy tests; cloud writes outside isolated verification |

Implementation review checked authorization before cloud effects, strict fields and body bounds, result-ID validation, no raw provider errors, no retries, post-create refresh failure, cancellation/unmount and retained selection across pagination. Live AgentKit creation remains unverified. Existing unrelated local changes are retained. No commit/push/deployment was performed. Temporary browser fixtures are removed after verification.

Local activation: the running Studio cached its old HTML entry. Restarted the same `veadk studio` launch without opening another browser; verified the current built entry, referenced JS assets (HTTP 200), and POST /web/a2a-spaces in the live OpenAPI. Cloud Runtime was untouched.

Name-only display refinement approved by the user on 2026-10-22: space selectors, bound-space status, viewed-space context, creation confirmation and registration destination show the space name without its resource ID. IDs remain unchanged in requests and selection values. If metadata has no name, show a localized name-unavailable label instead of exposing the ID. This is a display-only change with no API, persistence or authorization contract impact; direct review found no blockers.

Approved follow-up FR-5 / T-6 / AC-6 (2026-10-22): unbinding applies only to the selected space when its ID equals the current bound space ID. An unbound selection must not offer an enabled unbind action. Changing selection, including after creation, clears any prior confirmation. Guard the mutation handler as well as the visible controls. API/CAS and permissions remain unchanged. Regression: bind A, open unbind confirmation, select unbound B, verify confirmation/action disappear and no write occurs; reselect A and explicitly confirm to send one null binding with the current revision. Direct review confirms this prevents an action on B from unbinding A without changing backend ownership. Verification pending.

Follow-up verification (2026-10-22): pass — npm test (1389 Node tests, 167 Vitest cases); build; i18n (2 locales/22 namespaces); tsc --noEmit; asset validation (114 files/351 references); git diff --check; scoped UI source secret scan. Name-only regressions first failed in 2 cases, then passed; the selected-space unbind regression first failed, then passed. Real browser with mocked API confirmed selecting unbound Other hides both unbind and the previous Default confirmation while names omit resource IDs. Studio restarted with its original command; after startup completed, the current entry and JS assets returned HTTP 200. No cloud binding was modified. Temporary fixtures removed. Python tests are not_applicable for this frontend-only refinement; prior backend evidence remains unchanged. FR-5 / T-6 / AC-6 complete.
