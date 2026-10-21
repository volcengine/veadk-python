# Studio latest image snapshots

[中文版](2026-10-20-latest-image-snapshots.zh.md)

- Change ID: `studio-latest-image-refresh`
- Created: 2026-10-20; revised: 2026-10-21
- Status: approved; user approved digest snapshots, Studio implementation/deployment and new-MPA validation on 2026-10-21.
- Component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md).
- Baseline: `86c93529969e6dde86890b30f7e407bfc32ff5ea`, matching the deployed Studio source archive.

## Evidence and cause

The registry's current Worker `latest` manifest matches the recently published release. A local pull and three source-file hashes confirm the new code. AgentKit CreateTool receives the correct latest URL. CloudTrail confirms its downstream CreateFunction request also contains that URL, without an old image ID. Nevertheless, the resulting veFaaS revision and a new session use an earlier internal image ID. A successful image precache does not update that published binding. Updating the function source and releasing another revision fixed individual test functions, but did not fix subsequent CreateTool calls.

The proven failure boundary is veFaaS source synchronization/resolution during creation; the service's cache key, TTL, and internal selection algorithm remain unverified. Studio currently accepts platform Ready without establishing image freshness. The current API rejects digest-form precache URLs and rejects using a prewarmed internal registry URL as a new source. Thus neither digest URLs nor internal image-ID URLs are established supported deployment mechanisms.

A separate Studio task failed although its Runtime later became Ready V1. The exact exception remains unverified. Do not claim an image fix resolves this completion failure; investigate it separately before changing retry behavior.

## Goals and non-goals

Keep `latest` as the operator's configured input and publication workflow. Each new Studio MPA must bind the contents selected for that creation, while a retry must retain its original selection. Verify an entirely new MPA through Studio and inspect its actual Worker contents. Do not change old MPA sessions, calendar authorization, Agent/Worker business code, cloud cache settings, or delete failed resources. Standalone CLI provisioning remains compatible.

## Scenarios and requirements

- **FR-1:** Given Studio latest inputs, when a new deployment identity is prepared, resolve each supported CR image's current manifest and create a deterministic content snapshot tag in the same repository. Preserve the original latest tag.
- **FR-2:** Given a recorded image selection, when the same creation is retried, reuse that selection even if latest has moved. Reject changed requested inputs. Do not silently rewrite pre-upgrade unfinished Worker/Runtime request hashes.
- **FR-3:** Given denied registry access, missing manifests, invalid digests, conflicting snapshot tags, or unsupported latest registries, fail with bounded redacted diagnostics before Worker/Runtime creation. Never fall back to an unverified latest deployment.
- **FR-4:** Given a new MPA, completion requires the normal Runtime deployment finalization and application readiness. E2E additionally inspects a newly allocated Worker session's actual release markers/hashes; platform Ready is insufficient.
- **FR-5:** Given a partial deployment failure, retain resources and original intent. Diagnose the failure without forwarding child stderr, secrets, or arbitrary exception text.

## Design and contracts

For Studio-owned fresh deployments only, add a focused internal image-resolution helper beside managed provisioning. Use existing provider-aware AgentKit CR authentication and HTTP dependencies. Restrict trusted registry hosts to the configured provider's supported CR domains; validate repository/tag/digest syntax, use HTTPS with redirects disabled and bounded timeouts, and never accept an authentication challenge pointing at an arbitrary host.

Read the latest manifest with explicit supported OCI/Docker media types, verify its SHA-256 against its declared digest, and publish exactly those bytes as `mpa-sha256-<64 lowercase hex digits>` in the same repository through the registry distribution API. If the snapshot tag exists, verify its digest rather than overwriting conflicting content. Re-read the snapshot tag before use. The source latest tag is never deleted, replaced, or moved by this operation. Snapshot tags are durable release references; automatic garbage collection is outside scope.

Persist requested reference, selected digest, and deployment reference in the existing native per-agent registry record under its deployment lock before CreateTool/CreateRuntime. No table/schema migration is needed. Both Runtime and Worker use their selected snapshot references. Subsequent retries validate requested references and reuse persisted deployment references. Fail closed for ambiguous legacy pending state; do not repair old creations implicitly. Registry record state is the selection authority; Studio task/browser inputs continue to show latest. A snapshot selects latest at creation time, not continuously for an already running MPA.

This is a deliberate distinction: the user-facing input remains latest, while the underlying Tool/Runtime image URL will be the content snapshot tag. It does not satisfy a requirement that the underlying platform URL itself must literally end in `:latest`; that alternative requires a platform-supported cache invalidation/fresh-source contract that has not been established.

Cloud writes are scoped to the selected repository and newly created deployment identity. Registry pull and push permissions are required; do not modify IAM automatically. There are no new dependencies or public HTTP request fields. No frontend behavior change is planned. Cancellation, existing request tokens, network/DB ownership validation, and unknown-outcome recovery remain intact. API/transport errors remain explicit; only safe operation/category/code/request ID may reach Studio.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification | Current result |
| --- | --- | --- | --- | --- |
| FR-1/FR-3 | T-1: implement trusted CR manifest snapshot helper | AC-1: same bytes/digest, latest untouched; negative access/format/conflict cases fail | Regression tests first; helper tests with mocked CR/HTTP | pass; local evidence below |
| FR-2 | T-2: wire selection into Studio-owned provisioning and native record | AC-2: retry after latest moves uses original snapshot; independent MPA resolves new snapshot; legacy pending state preserved | Managed service/Worker/Runtime integration regressions | pass; local evidence below |
| FR-4/FR-5 | T-3: isolate actual Studio completion exception and fix only a proven cause | AC-3: failing regression reproduces confirmed cause; normal final update and readiness complete | Targeted creation/deployment tests and safe live diagnostics | not_run; cause not established |
| All | T-4: validate and publish corrected Studio | AC-4: changed-line coverage above 95%, required gates honestly reported, original Studio auth/env retained | pytest coverage, Ruff, changed-file Pyright, pre-commit all-files, broader regression as affected; supported Studio update | not_run |
| FR-4 | T-5: create a new MPA in the existing authorized Chrome session | AC-5: Studio task succeeds; Runtime readiness succeeds; selected manifest maps to actual new Worker code; safe functional execution reaches terminal result | Browser evidence plus official cloud API/source probes; no human IM message | not_run |

## Risks and recovery

Snapshot publication requires registry write permission and consumes tag metadata. Multi-platform media types must remain intact; do not rewrite a manifest or silently select a different architecture. Verify that AgentKit accepts the snapshot tag in a bounded new resource experiment before making the feature available. Registry tag immutability is not presumed: detect conflicting existing content and validate on retry before further deployment writes. Keep existing failed resources, and roll Studio back through its supported release mechanism if acceptance fails. Do not claim a change to the platform's internal cache implementation.

## Review and delivery record

Direct design review performed because no review-spec skill is available: checked provider boundaries, secret handling, manifest integrity, cancellation/timeouts, retry identity, legacy pending compatibility, latest input semantics, and bilingual equivalence. Resolved: the user approved latest-as-input with content snapshots as deployment URLs on 2026-10-21. The exact separate deployment-finalization exception remains a diagnosis task, not a presumed fix. Implementation and local verification are recorded below; deployment and live MPA validation remain separate. The user authorized implementation, deployment and new-MPA validation on 2026-10-21.

## 2026-10-21 approval and implementation scope

User instruction: “修改一下studio 部署一下试试”. Both a unique tag and an automatically computed `mpa-sha256-<digest>` tag were live-tested against published Worker source, establishing feasibility. The source baseline is synchronized to `5e5deb6a`. Scope covers snapshot resolution, durable image selection in the native deployment record, paired component contracts and tests, BP Studio update and new creation validation. The separate creation-finalization failure remains unexplained; no speculative fix is included. Preserve resources and report any live failure. Security and bilingual equivalence were reviewed directly because review-spec is unavailable.

## 2026-10-21 local implementation and verification

Implemented `managed/image_snapshot.py`, invoked under the existing deployment lock in `service.provision`. Native JSON persists requested/resolved images; initial preparation pins both images, while retries only verify the saved snapshots. Non-Studio CLI and fixed tags are unchanged. Parse the CR instance name from the region-qualified host, retain STS authentication, and verify exact manifest bytes, digest and media type. Tests cover the registry protocol, provider/redirect boundaries, authentication, conflicts/corrupt state, failure/cancellation, retry and Worker/Runtime payload integration.

Environment: Python 3.12.12; `uv sync --frozen --extra dev --python 3.12`; dependencies and lock file unchanged.

- pass: `pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q`: 1220 passed.
- pass: 47 snapshot/integration cases; module line/branch coverage 100%; incremental production lines 130/130 (100%). Coverage preloads `pydantic_settings` and SDK Runtime types before pytest to avoid dependency import-identity errors. The same errors reproduce on unmodified main and parallel coverage runs; no business-code workaround was added.
- pass: `npm --prefix frontend test`: 8 files, 118 cases; `npm --prefix frontend run build`.
- pass: changed-file Ruff/Pyright; `pre-commit run --all-files` including secret scanning; `git diff --check`.
- pass: the same implementation resolved and reread Agent/Worker snapshots in the authorized real BP account, preserving latest.
- not_run: Studio update and browser MPA creation, application readiness/A2A; append deployment evidence afterward. Independent Codex/Pi/Harness, domestic live deployment, calendar and human IM are outside this validation.

Direct review covered dependencies/public fields, credential host boundaries, native locking/durable selection, fixed-tag side effects after cancellation, legacy pending rejection, CLI compatibility and bilingual equivalence. Snapshot tags are retained without automatic garbage collection.
