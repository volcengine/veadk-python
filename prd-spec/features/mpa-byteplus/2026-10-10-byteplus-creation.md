# BytePlus managed MPA creation

[中文版](2026-10-10-byteplus-creation.zh.md)

- Change ID: `mpa-byteplus-creation`
- Created/revised: 2026-10-10
- Status: approved
- Contracts: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md)

## Background and evidence

Studio already selects BytePlus region `ap-southeast-1`, but MyAgents hides the MPA create action for BytePlus and the creation route rejects that provider. The managed profile, credential loader and VPC/APIG/AIDAP/model-key adapters still select domestic endpoints. AgentKit's installed SDK supports provider-scoped Runtime, Skills and Tools clients. The repository's Identity client already accepts a provider. The domestic workflow works and must remain compatible.

## Goals and non-goals

Enable the same three-step creation flow under BytePlus with isolated provider selection, credentials, configuration and endpoints. Preserve domestic defaults, permissions, resource sharing and retry behavior. No general-agent chat changes, credential persistence, automatic fallback to domestic services, existing-resource migration, image publication, or changes to sibling repositories.

## Scenarios and requirements

- **FR-1:** BytePlus Studio exposes MPA creation in its configured region; reject domestic regions and browser-supplied provider/account/endpoint overrides.
- **FR-2:** Keep the zero-argument domestic profile byte-for-byte equivalent in its values. BytePlus defaults to `ap-southeast-1`, the existing BytePlus ModelArk model/base, and `CLOUD_PROVIDER=byteplus` / `AGENTKIT_CLOUD_PROVIDER=byteplus`. Existing public images remain defaults because the user has no overseas images. Trusted server image overrides are permitted; image transport is separately verified.
- **FR-3:** Use only the selected provider's AK/SK/token or the explicit rotating IAM file. Verify account through that provider's STS on each call. Select the provider context inside SDK worker threads; use provider-specific VPC/ECS/APIG/AIDAP/Ark/IAM/Identity endpoints. Unsupported services or policies must report failure, never silently skip preparation or call domestic services.
- **FR-4:** Carry trusted provider identity into the fixed child runner and durable request fingerprint. Provider changes cannot resume the same task. Use separate default task/bootstrap SQLite files for BytePlus; unchanged domestic task inputs and defaults remain compatible.
- **FR-5:** Preserve shared admin/business workspaces and database isolation, locks, bounded retries, unknown-create recovery, cancellation and readiness semantics. BytePlus uses the same required IAM policy contract initially: unavailable policy names are explicit failures, not silently omitted permissions.
- **FR-6:** Runtime receives provider/model/region/APIG endpoint configuration. Optional OpenViking remains all-or-none. The dialog reuses current components and displays provider-specific console links without foreign account/resource IDs.

## Design and affected files

Add provider as a server-owned profile property with a domestic default. Reuse existing cloud-provider and ModelArk utilities. Introduce scoped managed-provider endpoint helpers for services not covered by those utilities. Make adapters accept an optional provider retaining existing signatures and defaults. The server selects the provider; browser inputs do not. BytePlus stored tasks add a nonsecret provider marker, passed through stdin to the runner; domestic payloads remain unchanged. Provider context is applied when Runtime/Skills/Tools clients are constructed, not as a machine-global mutation. The IAM singleton bypass remains intact. Apply the overseas APIG override recognized by the MPA image.

Affected modules: `managed/{studio_profile,config,credentials,runtime,worker,network,network_cloud,gateway_cloud,pg_cloud,model_key,iam,service,tasks,runner}.py`, new managed provider helper, paired managed READMEs, `frontend/server/mpa_creation.py`, `veadk/cli/cli_frontend.py`, `MyAgents.tsx`, `MpaCreateDialog.tsx`, targeted tests and release assets. Component contract changes are limited to provider/configuration/isolation and creation availability.

Overseas zone validation accepts the provider's `ap-southeast-1a` and `ap-southeast-1-a` formats without rewriting resource IDs. Domestic validation stays intact. `VEADK_MPA_BYTEPLUS_CREDENTIAL_FILE` explicitly selects a rotating file; an absent BytePlus environment key pair does not load the domestic default mounted file. Server image overrides and the optional AIDAP hostname are inspected locally; invalid AIDAP URLs, paths and user information fail before resource mutations. TOS mount endpoints are provider-specific.

Live preflight correction: the initial regional BytePlus STS host timed out or disconnected. With the same process credentials, the exact AgentKit STS SDK successfully returned a nonempty identity from `open.byteplusapi.com`; use this host only for BytePlus. Domestic STS behavior is unchanged. Direct design review confirms this corrects FR-3 without expanding scope. The user submitted the real creation; diagnostic probes are read-only.

Live IAM correction: the user retry passed account/model-key checks and failed in `iam_role`. A read-only `GetRole` through `iam.byteplusapi.com` times out; the same SDK, credentials, signing region and request through `open.byteplusapi.com` return `RoleNotExist`. Managed BytePlus IAM selects this working host while preserving the existing trusted `IAM_OPENAPI_HOST` override. Do not change the shared IAM helper or domestic host, permissions and reconciliation. Direct review confirms FR-3 scope and failure semantics are preserved.

Live PG diagnosis: the user retry passed runtime-role preparation and failed at `admin_workspace`. Read-only DescribeWorkspaces times out through the regional AIDAP host; the same SDK/credentials/region succeed through `open.byteplusapi.com`. Managed BytePlus AIDAP defaults to that host, retaining validation of the trusted server override; domestic behavior is unchanged. The same-name admin Workspace is `CreateFailed` and has no ownership tags in the response. This correction neither deletes/adopts that resource nor clears uncertain creation state. Recovery of the failed resource needs separate evidence and authorization. Direct review confirms the endpoint correction is within FR-3.

## Tasks and acceptance

- **T-1 / AC-1:** Add failing provider/region/credentials/default-regression tests; domestic snapshot values and task behavior remain unchanged (FR-1–FR-4).
- **T-2 / AC-2:** Wire profile, credential and SDK/transport propagation; simulated calls assert hosts, signing region and provider without real secrets (FR-2–FR-3).
- **T-3 / AC-3:** Wire route/runner/UI; tests prove overseas entry, requests and links plus rejection, retry and isolation cases (FR-1, FR-4–FR-6).
- **T-4 / AC-4:** Run affected Python tests, Ruff/Pyright, frontend test/build/type/i18n/assets and browser flow/error/cancel/narrow-window checks. Retain domestic regressions (all FR).
- **T-5 / AC-5:** Record separate real-cloud evidence for images, service activation/quotas, IAM policies, AIDAP Workspace and IM Gateway APIs, readiness and chat. An isolated real creation needs explicit authorization. Simulations are not proof that the user's overseas account supports those services.

## Risks and open questions

Public BytePlus AgentKit documentation and installed SDK establish Runtime support. AIDAP documents exist, but full overseas Workspace and IM Gateway API availability, IAM policy catalog, model activation and image reachability remain unverified. Regional service adapters require live confirmation and may expose platform restrictions. The sibling MPA/Worker images may have additional domestic assumptions; inspection and explicit limitation reporting are required before claiming end-to-end success. No credentials, raw keys, production logs or private account IDs belong in evidence.

## Review, approval and verification

User approval: 2026-10-10, “国内流程是好的了，不要改坏了；帮我适配BytePlus”. User confirms no overseas image addresses. Direct design review performed because `review-spec` is unavailable: provider boundaries, domestic compatibility, trusted child propagation, cancellation, secrets and tests assessed. No new visual design; reuse the existing dialog/layout controls. Referenced frontend-design/ui-ux skills are unavailable locally, so no speculative layout redesign is included. Production changes followed failing regression tests. Final direct review checked configuration/transport/runner/UI consistency, rotating credentials, singleton avoidance, provider-context threading, existing resource hashes, terminal-state races and bilingual equivalence.

Verification date: 2026-10-10. Scope: working diff against `5644e146c9dfff6d2e290b1663cb2ea41dbb6b91`; no commit or cloud mutation performed. Ruff/Pyright were invoked in temporary `uv --with` environments because they are not installed in the project environment. Ruff is pinned to the repository hook's `0.11.12`.

| Check | Outcome | Evidence / limitation |
| --- | --- | --- |
| `uv run --extra dev pytest tests/integrations/mpa_managed -q` | pass | 752 tests, including 24 BytePlus cases; existing domestic creation, retry and resource tests retained. |
| `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | fail | 6,951 passed, 1 failed, 53 skipped, 4 xfailed. Existing artifact writer MIME test expects `text/markdown`; local MIME detection yields `application/octet-stream`. Reproduced the same failure in an isolated unmodified HEAD checkout. Two workers were used as the repository default. |
| `npm --prefix frontend test` | pass | 1,377 Node tests and 67 Vitest tests. |
| `npm --prefix frontend run build` | pass | TypeScript compilation and production/main/website bundles; matching `veadk/webui` assets regenerated. |
| `npm --prefix frontend run check:i18n` | pass | 2 locales, 21 namespaces. |
| `npm --prefix frontend run test:webui-assets` | pass | 113 packaged files, 350 internal references. |
| `uv run --with ruff==0.11.12 ruff check <changed-python-files>` | pass | All changed Python source and new regression tests. |
| `uv run --with pyright pyright <changed-python-files>` | fail | Managed modules, creation route and new BytePlus tests have 0 errors. The CLI file has 37 errors also present in the unmodified HEAD file; no new diagnostics. |
| Isolated real-browser validation | pass | Actual dialog/routes with a fake child and disposable task DB; three steps, links, disabled fields, failure/retry, cancellation/terminal race, new request, successful close, Chinese/keyboard input and 420px layout checked. No cloud API used. Preview files and servers removed. |
| Codex smoke / harness coverage | not_applicable | No Codex runtime implementation or harness/sidecar event contract changed. |
| Pre-commit all-files and commit synchronization | not_run | No commit authorized or attempted; targeted lint, asset and secret checks are separate. |
| Actual BytePlus creation / account preflight | fail / pass | User-submitted creation stopped at `checking` before PG/VPC/APIG mutations because the regional STS transport failed. After the BytePlus-only host correction, the actual `RuntimeCloud.account_id()` path succeeds using the running Studio process credentials; identity values are not recorded. No automatic task retry was submitted. |
| Actual BytePlus IAM read-only diagnosis | fail / pass | User retry passed account/model-key checks then failed at `iam_role`. The original IAM endpoint timed out. After the managed-only host correction, actual `IamCloud.call("get_role")` returns recognized `RoleNotExist`; all 12 required system policies are present through read-only GetPolicy. Role/policy creation and attachment permissions are not yet verified; no cloud IAM write was submitted by the assistant. |
| Image pull, remaining APIs/policies, ready/chat | not_run | Awaiting user retry and live service preparation. Local simulations cannot satisfy AC-5. |
| Redacted secret scan of changed/new files | pass | Gitleaks scanned 1.43 MB in an isolated copy; no leaks found. |

AC-1–AC-3 are implemented and verified in isolated tests. AC-4 is qualified by the unchanged full-regression and CLI baseline failures above. Two regression assertions failed against the regional STS host before the correction and passed afterwards; all 752 managed tests were rerun. AC-5 remains open; do not describe the overseas end-to-end path as verified.

IAM follow-up verification (2026-10-10): two endpoint regression tests failed before the fix; 752 managed tests pass after the fix, including 24 BytePlus cases and trusted override preservation. Ruff check/format, Pyright for the changed helper/tests and diff whitespace pass. No frontend behavior changed in this follow-up, so existing browser/build evidence remains applicable.

PG follow-up verification (2026-10-10): two regression assertions failed before the endpoint correction; afterwards 752 managed tests pass, as do Ruff check/format, Pyright for the changed helper/tests and diff whitespace. Live audit confirms the user-submitted CreateWorkspace returned outer InternalError with inner 40016:Forbidden because the caller lacks purchasing permission for the configuration; this is not a confirmed quota error. The Workspace is CreateFailed, its detail has no failure summary, and ownership tags are absent. AIDAP read connectivity is verified but actual PG creation remains blocked by purchasing permission. No deletion, bootstrap-state clearing or recreation was performed. Permission enablement and failed-resource recovery are required to continue AC-5; unaffected frontend checks do not need to be repeated.


## Commit preparation verification (2026-10-10)

The user authorized committing and pushing the local changes. Fetched `origin` and `upstream`, then ran `git rebase --autostash upstream/main` on `feat/mpa-account-fixes-upstream-clean-20261010`. The branch was already current; all 159 pre-existing changed file states matched after synchronization. The baseline remains `5644e146c9dfff6d2e290b1663cb2ea41dbb6b91`. The only subsequent production adjustment is Ruff formatting of the creation-route registration in the CLI.

- **pass:** `uv run --extra dev pre-commit run --all-files`: Ruff check/format and both secret scanners. The first run reformatted the CLI call; the repeat passed.
- **pass:** post-synchronization `uv run --extra dev pytest tests/integrations/mpa_managed -q --tb=short`: 782 passed, 5 existing warnings.
- **pass:** post-synchronization `npm --prefix frontend test`: 1,377 Node tests and 67 Vitest tests.
- **pass:** post-synchronization `npm --prefix frontend run check:i18n` and `npm --prefix frontend run test:webui-assets`: 2 locales / 21 namespaces and 113 files / 350 references.
- **not_run:** repeated full Python regression, frontend build/browser and Pyright. Synchronization preserved their previously tested source; the CLI adjustment changes formatting only. Existing full-regression MIME and CLI Pyright baseline failures remain documented above. No new cloud creation, publication or deployment is part of this commit request; overseas end-to-end readiness remains unverified.

The commit includes BytePlus adaptation, terminal PG creation-failure recovery, paired documents, tests and matching generated frontend assets. No credentials, local state databases or production logs are included.
