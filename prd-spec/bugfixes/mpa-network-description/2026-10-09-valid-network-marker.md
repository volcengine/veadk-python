# Managed network description and rejected-intent recovery

[中文版](2026-10-09-valid-network-marker.zh.md)

Change ID: mpa-network-description. Created/revised: 2026-10-09. Status: implemented.

## Evidence, goals and scope

A fresh-account creation fails at `network`: CloudTrail confirms `CreateVpc` returned `InvalidDescription.Malformed`. The shared registry retains a VPC intent with `vpc_dispatched=false`, no VPC ID, and a colon-containing ownership description. VPC/subnet description rules do not allow colons: [CreateVpc](https://docs.volcengine.com/docs/VirtualPrivateCloud/CreateVpc-CreatingaVPC?lang=en), [CreateSubnet](https://docs.volcengine.com/docs/VirtualPrivateCloud/CreateSubnet-Creatingasubnet?lang=en). Preserve the verified account/region ownership hash and names. No credentials or raw audit payloads are recorded here.

The user requested correction after the diagnosis, approving this bounded fix. No frontend, IAM, PG, APIG, Runtime/chat or image changes; no live cloud creation or database maintenance performed by the coding agent. Deployment itself still requires an authorized create/retry request.

## Requirements and scenarios

- FR-1: New VPC/subnet requests use `mpa-account-network-v1-<scope hash>` as Description, preserving names, account/region hash and ownership validation.
- FR-2: A persisted old description-only intent can change to the new description only when the dispatch flag is explicitly false, no resource ID is recorded and name discovery has no matching resource. Other request fields must match exactly. Generate a new ClientToken because the body changes; persist before dispatch under the existing lock.
- FR-3: Uncertain/in-flight old intents cannot issue another Create. Matching discovered old resources may be recovered. Both exact old and new scope markers are accepted for ownership; unrelated descriptions, wrong accounts, CIDRs, VPCs or zones remain errors. Existing resources are not rewritten, deleted or recreated.
- FR-4: Same-body definite permission rejection retains its ClientToken as before. Cancellation/timeout retain intent and avoid duplicate creation.

Scenarios: fresh account passes provider description validation; a rejected old VPC/subnet intent resumes with corrected description and new token; changed CIDR/project/zone remains rejected; unknown outcome without a discovered resource fails closed; old resources are reused from registry or by exact scoped name/marker.

## Design and affected files

`managed/network.py` owns legal/legacy scope markers and exact-description-only compatibility in `_create`. Existing resource wait and ownership checks accept only the two scoped markers. The existing `NetworkCloudError` definite-rejection flag is the evidence for recovery; absence of the flag is not evidence of rejection. No new tables or APIs. No errors are converted into success.

Component contracts: [Studio creation](../../../specs/studio-mpa-creation/README.md), [Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md). Update both languages and managed READMEs. Tests live in `tests/integrations/mpa_managed/test_deployment_network.py` with isolated cloud/registry fakes.

## Tasks and acceptance

| Requirement | Task | Acceptance |
| --- | --- | --- |
| FR-1 | T-1: failing provider-format regression then legal marker | AC-1: both create payloads satisfy allowed description characters |
| FR-2 | T-2: exact rejected-intent recovery | AC-2: same agent retries successfully; only description/token change, saved before dispatch |
| FR-3, FR-4 | T-3: compatibility and safety tests | AC-3: old recovery/reuse, no duplicate unknown creates, changed-input rejection, same-body token preservation |
| FR-1–4 | T-4: bilingual reconciliation and checks | AC-4: managed regressions, Ruff/Pyright and secret/diff checks pass |

Commands: `uv run --extra dev pytest tests/integrations/mpa_managed`; changed-file Ruff/Pyright and pre-commit. Frontend/build/browser/sidecar checks are not_applicable: no frontend or sidecar changes. Full-repository checks and live smoke are reported separately; no commit or deployment requested.

## Review, approval and risks

Direct review (review-spec unavailable): exact scoped compatibility, false-versus-missing dispatch distinction, new token for changed body, locked durable save before cloud call, resource ownership and partial failure all reviewed. Bilingual equivalence reviewed; no blockers. Approval: user requested this fix after the proposed description/rejected-intent solution. Existing resources are retained. A legacy intent with unknown outcome may still need operator reconciliation; never reset it to claim success. Verification recorded below.

## Verification and delivery record

2026-10-09, working tree based on `ef0ad519`, scoped to network descriptions/recovery. Earlier IAM/account work and unrelated user changes are preserved.

- pass: test-first provider-format regressions produced 3 expected failures (`InvalidDescription.Malformed`) before the code change.
- pass: `uv run --extra dev pytest tests/integrations/mpa_managed/test_deployment_network.py tests/integrations/mpa_managed/test_deployment_network_cloud.py -q`: 62 passed, including VPC and subnet rejected-intent correction, unknown outcome discovery/blocking, legacy reuse, payload conflict and same-body token preservation.
- pass: final `uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py -q`: 508 passed; existing dependency deprecation warnings only.
- pass: `uvx --from ruff==0.11.12 ruff check` and `ruff format --check` for the two changed Python files. Final `uvx pyright --pythonpath .venv/bin/python veadk/integrations/mpa/managed/network.py tests/integrations/mpa_managed/test_deployment_network.py`: 0 errors, 0 warnings. An initial test-fixture dictionary inference error was fixed with an in-place update; no production typing bypass.
- pass: changed-file `uv run --extra dev pre-commit run --files` for Python and bilingual documents: Ruff/check/format and hardcoded-secret scan passed. YAML scan not_applicable (no YAML changes).
- pass: paired identifiers, relative design links and `git diff --check`. Reconciled the Studio configuration sentence with the preceding STS-account fix.
- not_applicable: frontend tests/build/browser, generated web assets and sidecar gates; no UI or sidecar change.
- not_run: full-repository regression/all-files pre-commit because no commit is requested and the change is limited to provisioning; live retry/cloud mutation because the user will submit the create/retry request. The diagnostic audit was read-only, not a successful creation smoke.

Review complete: other inputs remain immutable, exact old/new scope markers only, no reset of unknown dispatch, changed-body tokens are regenerated and persisted before the cloud call. AC-1–4 met by isolated checks; full live creation is not claimed. Existing resources and records are retained until an authorized retry performs the bounded intent correction.
