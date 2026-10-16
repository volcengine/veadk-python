# BytePlus OpenViking preparation for MPA creation

[中文版](2026-10-14-automatic-creation.zh.md)

Change ID: `mpa-byteplus-openviking`. Created/revised: 2026-10-14. Status: implemented; live acceptance pending.

Related contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md).
Predecessor: [Beijing automatic OV](../mpa-openviking-auto/2026-10-13-default-model-creation.md).

## Background and evidence

The user requests automatic OV preparation in this VeADK repository for BytePlus MPA creation. Current `managed/openviking.py`, configuration validation and service orchestration explicitly reject automatic OV outside Volcengine Beijing. The Studio dialog additionally restricts automatic mode to Volcengine. BytePlus manual URL, resource ID and API Key injection already exists.

The supplied overseas SOP describes a personal library created with a Coding Plan model credential and the data-plane URL `https://api.vikingdb.ap-southeast-1.bytepluses.com/openviking`. It contains a Python attachment for collection management. Attachment retrieval on 2026-10-14 was rejected for missing `drive:file:download` scope. The local path mentioned in the SOP does not contain that script. The overseas control-plane host, signing region, model identifiers, credential Source/EndpointID semantics and enterprise availability have therefore not been verified. Do not infer these from the data-plane URL or domestic settings.

Current local `agentkit-mpa-agent` code separately uses Beijing OV administration for per-user registration/key lookup. Creating an overseas collection in VeADK alone does not prove that Runtime memory works. That repository requires its own adaptation and deployment verification.

## Goals and non-goals

Prepare and bind an overseas library before Runtime deployment, wait for readiness, obtain its data-plane key, and inject the existing four OV environment variables. Preserve Volcengine Beijing behavior and submitted manual requests. Initial candidate scope is BytePlus `ap-southeast-1`, subject to provider verification.

Exclude automatic changes to `agentkit-mpa-agent`, cloud deployment, paid resource creation during development, credential publication, unrelated local changes, general-agent creation and OV deletion. Do not silently replace per-user isolation with a shared default identity.

## Requirements and scenarios

- FR-1: Advertise automatic OV only for explicitly verified provider/region combinations. Configuration, API, orchestration and UI must agree. An unsupported region fails before resource mutation.
- FR-2: Use deployment-account BytePlus credentials, including refreshed STS credentials where applicable, to sign verified control-plane calls. Never reuse a domestic account credential or derive a control-plane hostname by guessing.
- FR-3: Verify library edition and model credential requirements before selecting defaults. Coding Plan credentials, ordinary model inference credentials and the resulting library API Key are distinct. A missing prerequisite produces an actionable, redacted error before creating resources; no undocumented fallback is allowed.
- FR-4: Reuse existing deployment locking and durable nonsecret intent/resource bindings. Persist a returned ResourceID immediately. A later failure reuses that ID after ownership/configuration validation. A create timeout with unknown outcome does not trigger blind duplicate creation. Cancellation retains the binding and prevents subsequent steps.
- FR-5: Poll using a bounded deadline and verified provider status values. After readiness, obtain the default-user library Key and inject `OPENVIKING_URL`, `OPENVIKING_RESOURCE_ID`, `OPENVIKING_API_KEY`, and `OPENVIKING_USER`. The URL is provider-specific. Keys stay out of registry records, logs, UI responses and browser persistence.
- FR-6: New eligible Studio requests use automatic mode. Existing submitted manual tasks retain their original mode and inputs on retries. Use the existing three-step dialog and localized status/error presentation. Explain required model credentials and resource retention where applicable.
- FR-7: Domestic requests, general agents and other existing BytePlus dependencies retain their contracts. Runtime per-user memory is a separate acceptance boundary and must not be claimed as verified by collection-creation tests.

## Proposed design and contract impact

Add explicit provider/region endpoint and model configuration selection to the existing OV adapter after confirming provider contracts. Keep the Beijing request semantics stable. Reuse the signing helper, deployment-account source, registry lock, safe errors and progress stages. Verify the overseas Create/Get/Access response shape rather than assuming it matches Beijing.

Extend the existing automatic availability flag and checks consistently through profile loading, request validation, service execution and the dialog. Persist each request's chosen mode. Resolve model credentials on the server with an explicit supported source; the final selection requires the overseas reference script. Any new secret setting must have validation, redaction and restart/retry semantics before implementation.

Update the bilingual Studio MPA creation contract with the verified provider matrix, model requirements and retained-resource semantics. Existing Runtime OV variable names remain unchanged. No component spec currently promises overseas automatic creation; do not mark a proposed capability active prematurely.

## Tasks and affected files

1. T-1 / FR-2–3: Read the SOP attachment or equivalent authoritative overseas contract. Resolve the blocking questions below. Finalize and review this bilingual design and component contract.
2. T-2 / FR-1–5: Add failing provider/configuration/adapter/retry tests; implement in `veadk/integrations/mpa/managed/openviking.py`, `config.py`, `service.py` and related profile/credential code only as needed.
3. T-3 / FR-1,6: Update `frontend/src/ui/mpa-create/MpaCreateDialog.tsx`, corresponding API/task handling and locales if required. Add UI regressions for new versus resumed requests and unavailable prerequisites.
4. T-4 / FR-7: Run domestic and overseas offline regressions, inspect browser behavior and regenerate release assets. Reconcile operator documentation and both design/spec languages.

## Acceptance and verification

- AC-1: An eligible new BytePlus request reaches the verified overseas control plane, obtains a bound library, and injects the four variables. No real credential enters test fixtures.
- AC-2: Timeout, cancellation, permission rejection, readiness failure, missing model credentials and same-request retry have explicit tested outcomes, without duplicate libraries or silent success.
- AC-3: Domestic wire payloads and existing manual retry semantics remain unchanged. General-agent creation is unaffected.
- AC-4: UI eligibility matches backend behavior; errors, loading, retry, keyboard and narrow-window states remain usable. Generated frontend assets match source.
- AC-5: Documentation distinguishes offline collection provisioning from live cloud acceptance and Runtime memory integration.

Planned commands: `uv run --extra dev pytest -n 2 tests/integrations/mpa_managed`; affected Studio server route/task tests; Ruff and Pyright on changed Python files; `npm --prefix frontend test`; `npm --prefix frontend run build`; `npm --prefix frontend run check:i18n`; `npm --prefix frontend run test:webui-assets`; scoped secret scanning. Use isolated mock services for tests. A real paid creation/read-memory smoke requires separate authorization and an explicit retention/cleanup decision.

## Risks and blocking questions

- What are the supported overseas control-plane host, signing region, API version and request/response fields?
- Does the overseas edition support MPA per-user registration and key retrieval? The SOP's personal-library OpenClaw example does not establish this.
- Which VLM/Embedding identifiers and credential sources are accepted? Can the existing resolved model key be used, or is a separate Coding Plan credential required?
- Which ready/failure statuses and billing/retention constraints apply? Do not copy domestic billing claims into overseas UI without evidence.
- Runtime readiness alone does not establish functional OV memory; an adapted Runtime image is required for the separate per-user path.

## Review, approval and verification record

The user requested this repository's implementation on 2026-10-14. Scope is authorized; unresolved provider details prevent design clearance and production/test edits. Direct review identifies edition compatibility, credential selection and provider endpoint verification as blockers. No `review-spec` skill is available; record a full direct review after resolving them.

2026-10-14, base `2ffe6e14` plus pre-existing uncommitted changes: source inspection completed; attachment access blocked (missing `drive:file:download`); cloud validation and runtime tests `not_run` (no implementation or cloud authorization); production changes `not_run` (provider contract unverified). Existing contract relocation, OpenSpec deletion and lockfile changes are outside this task and are preserved.


## Supplied-script review (2026-10-14)

The user supplied the attachment directly. It was inspected as source, not executed or copied into the repository. Confirmed script parameters:

- Control host `vikingdb.ap-southeast-1.byteplusapi.com`, signing region `ap-southeast-1`, service `vikingdb`, version `2025-06-09`, POST path `/api/openviking/{Action}`; headers `X-Top-Service` and `X-Top-Region` plus optional STS `X-Security-Token`.
- Collection `Version=developer`. Top-level `Source=codeplan` with Coding Plan credentials; model `seed-2-0-lite` and `skylark-embedding-vision`, no `ModelVersion` or `EndpointID` in coding mode. Endpoint mode instead uses `Source=volcengine` and separately supplied endpoints for each model.
- Create returns `ResourceID`; poll Get for `READY`/`FAILED`; Access key body contains `ResourceID` only (no `UserID`); default is the returned user. Response parsing accepts `Result` or `result`.
- The script explicitly states that developer libraries reject user registration. Data calls require `Authorization: Bearer` and `x-tt-env: pre`. Current Runtime code does not implement that contract.

This resolves the script-access and control-plane parameter blockers, but introduces a material edition/isolation decision: implement developer-library provisioning for later Runtime adaptation, or preserve enterprise per-user isolation and obtain a supported overseas enterprise contract first. The user was asked to choose; no default-identity fallback is authorized. Implementation and production tests remain pending that decision. Neither script inspection nor a successful collection create proves Runtime compatibility.

## Approved implementation decision

On 2026-10-14 the user approved developer-library provisioning in this repository and separate Runtime adaptation before live memory integration. This supersedes the pending edition decision above. Implement BytePlus ap-southeast-1 only, Source=codeplan and the supplied model names; obtain its dedicated Coding Plan key from server environment `OV_MODEL_API_KEY`, never from the ordinary MPA model key. Missing/invalid keys fail before any cloud resource mutation. New BytePlus Studio requests advertise auto mode; submitted manual requests remain manual. Reuse all current intent, ownership, timeout and cancellation guarantees. Default-user key access omits UserID. Preserve the four existing Runtime variables; do not invent unsupported Runtime settings. The UI explains personal edition/default user, the server credential prerequisite and the separate Runtime integration requirement. Do not claim overseas billing specifics. Retain libraries after cancellation/deletion.

Implement the exact reference signing headers/path in a BytePlus-only helper, without changing the shared signing utility or Beijing adapter. Cover canonical signing and STS with deterministic offline tests. Validate readback fields required by the selected request; BytePlus does not require ModelVersion or EndpointID, while Beijing still does. Accept the reference's Result/result envelopes for BytePlus only, and reject explicit failure/invalid resource IDs. No automatic retry of uncertain Create responses.

Direct design review: provider boundary, credential separation, personal-edition isolation, existing manual recovery, secret handling, startup lazy imports, error propagation, tests and bilingual parity reviewed. Blocking decisions resolved; status approved. No cloud operation, commit or push is authorized by this design.

## Implementation and verification (2026-10-14)

Implemented the approved developer-only scope. The adapter uses a separate lazy-imported BytePlus signing transport, the reference request path/headers and model names; Beijing still uses the existing signer and request schema. Profile capability and the existing dialog now support new BytePlus automatic requests. Model keys resolve only from the server environment, before cloud construction in direct provisioning and before task submission in Studio validation. No new browser secret field or shared-identity Runtime fallback was introduced. The four existing variables are prepared for the separately adapted Runtime.

Tested diff: this feature on `2ffe6e14`, preserving pre-existing local contracts relocation, OpenSpec deletion and lockfile edits. Review covered provider scope, exact canonical signing with/without STS, lowercase response envelopes, no explicit UserID for personal libraries, explicit failure handling, secret exclusion, ownership/readback, ambiguous create outcomes, cancellation/retry and old manual tasks. The underlying cloud calls were mocked throughout.

| Check | Result | Scope |
| --- | --- | --- |
| Test-first Python | pass | Seven new regressions failed before implementation; BytePlus adapter/config/retry. |
| Targeted Python | pass | 12 tests, including later-added STS signing, cancellation and no-mutation missing-key checks. |
| Managed creation + startup regression | pass | 987 tests with two workers. |
| Studio API/RBAC regression | pass | 205 tests: Runtime profile routes and Studio RBAC; two workers. |
| Frontend tests | pass | 1,389 Node tests and 96 React tests. The first UI attempt used the wrong working directory; the subsequent repository npm command passed all cases. The new automatic-mode case failed before the UI fix. |
| Ruff 0.11.12 check/format and Pyright | pass | Six changed Python source/test files; Pyright 0 errors/warnings. |
| Build, i18n and release references | pass | Both frontend targets built; 2 locales/21 namespaces; 113 packaged files/350 references. |
| Browser | pass | Actual dialog and mocked HTTP: overseas automatic mode, no manual fields, visible missing-key error, same-request retry, narrow viewport, Escape, old manual recovery and Beijing copy. Temporary fixture files/server removed. |
| Wheel | pass | Built locally; exact new adapter bytes present in wheel. No publication. |
| Scoped secret scan | pass | Changed/new source, docs, tests and generated assets; no findings. |
| Real cloud / Runtime OV memory | not_run | No paid resource creation authorized. Personal default-user/Bearer/pre routing remains another repository's work. |
| Full repository pytest/pre-commit | not_run | No commit requested. Targeted integration and full frontend gates cover this provider extension; no unrelated source changes. |
| Harness/sidecar smoke | not_applicable | No harness, worker or sidecar protocol changes. |

AC-1–AC-5 have offline implementation evidence; live collection response details, account entitlement and memory remain unverified. User accepted Runtime adaptation as separate scope. No commit or push performed.


Credential decision superseded by [API Key + endpoints](2026-10-14-inference-endpoints.md).
