# Public registry defaults for Studio MPA creation

[中文版](2026-10-09-public-registry-images.zh.md)

- Change ID: `mpa-latest-images`
- Created/revised: 2026-10-09
- Status: approved
- Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-9

## Background and evidence

Studio currently prefills fixed historical tags from `studio_profile.py`. The requested repositories are public: `agentkit-platform-2112682748-cn-beijing.cr.volces.com/agentkit/agentkit_mpa_agent_studio` and `agentkit-platform-2112682748-cn-beijing.cr.volces.com/agentkit/agentkit_mpa_codex_worker_studio`. Anonymous OCI reads succeeded on 2026-10-09; a different deployment account cannot list this source registry through its own CR management API. MPA uses an OCI index including an attestation entry; Worker uses a single Docker manifest. Public metadata exposes build time, not push time. Each repository currently has one historical tag; discovery alone cannot produce a newer build.

## Goals and non-goals

Automatically select the newest Linux/amd64 build for new Studio requests, preserve manual input and stable retry images. No cloud resource creation, credential changes, existing Runtime upgrades, general registry browser, or CLI YAML discovery. Source account is independent of verified deployment account. Existing CLI configuration remains explicit.

## Scenarios and requirements

- FR-1: Opening a fresh dialog obtains concrete defaults from the two public repositories. Rank eligible tags by UTC image-config `created`, with tag name as deterministic tie breaker. Ignore non-Linux/amd64 platforms and attestations; reject missing/malformed timestamps on otherwise eligible images.
- FR-2: Preserve editable image inputs. Explicit inputs bypass discovery for that image. Blank inputs resolve at first submission. Default selections use verified SHA256 manifest digests to prevent mutable-tag drift.
- FR-3: Store first effective selections using the existing task `images` snapshot. Owner/request-scoped retries and duplicate submissions reuse it without registry access. Different request inputs remain conflicts. Legacy snapshots remain unchanged, including empty snapshots.
- FR-4: Discovery is anonymous, server-side, GET-only, bounded and cancellable. No target-account CR permissions or registry secrets are needed. Return safe ConfigurationError messages on network/auth/metadata/limits/no-compatible-image failures; never silently select a historical fallback.

## Design and boundaries

Add an internal async HTTPX OCI resolver; reuse the existing dependency. Fixed repository constants belong to the Studio profile. Read tags, manifest/index, Linux/amd64 manifest, then image configuration. Check manifest/config digest integrity. Authorization challenges must point to the same HTTPS registry origin and expected repository scope. Pagination stays on the same tags endpoint. Only blob redirects may target HTTPS Volcengine object-storage domains; never forward bearer tokens across origins. Cap JSON bodies at 1 MiB, 100 tags/repository, 10 tag pages, 5 blob redirects, 4 concurrent tag reads, 15 seconds/request and 60 seconds/discovery. Client lifetime encloses each resolution; timeout/cancellation closes requests.

Config GET returns `runtimeImage`/`workerImage` digest references through the existing contract. POST resolves only missing defaults after reading any existing owner/request snapshot. SQLite `start` remains the transaction authority for first-writer pinning and conflicts. No persistent schema change or cache; fresh config inspections see new builds. The CLI retains fixed non-discovered image defaults, with the requested repository names. Existing requests keep persisted selections. General agent conversations, resource orchestration, IAM and deployment-account verification are unaffected.

## Tasks and affected files

- T-1 / FR-1, FR-4: Regression tests and resolver in `tests/integrations/mpa_managed/test_studio_images.py` and `frontend/server/mpa_creation_images.py`.
- T-2 / FR-2, FR-3: Route integration and owner-scoped snapshot lookup in `frontend/server/mpa_creation.py`, `managed/tasks.py`; route/task tests.
- T-3 / FR-1, FR-2: Repository constants in `managed/studio_profile.py`; update bilingual CON-9 and operator guide. Existing form/types already accept digest references; no layout or interaction change.
- T-4: Run affected Python tests, Ruff/Pyright, frontend tests/build and read-only browser checks; review bilingual equivalence, redaction and whitespace.

## Verification and acceptance

| Requirement | Task | Acceptance | Verification | Result |
| --- | --- | --- | --- | --- |
| FR-1, FR-4 | T-1 | AC-1: correct newest eligible build; bounded safe failure | MockTransport tests plus anonymous public read | not_run |
| FR-2, FR-3 | T-2 | AC-2: blank/manual/retry/owner behavior | creation image/task regressions | not_run |
| FR-1, FR-2 | T-3, T-4 | AC-3: defaults reach existing inputs; no UI contract break | frontend tests/build; read-only dialog check | not_run |

Commands: `uv run --extra dev pytest tests/integrations/mpa_managed`, scoped Ruff/Pyright, `npm --prefix frontend test`, `npm --prefix frontend run build`, `git diff --check`. Tests use fake transport/tasks; real validation is GET-only. No live deployment is authorized. Test scope is this working diff on `feat/test-main`; unrelated preexisting changes remain intact.

## Risks and recovery

Discovery adds latency and depends on public repository availability. Build time can differ from push order by design. More than 100 tags requires an explicit raised limit rather than silent partial selection. Platform acceptance of digest references is not proven by a new cloud deployment; existing image validation supports them. Manual images retain existing tag semantics. Rollback server discovery for new tasks only; do not change persisted task images.

## Design review and approval

`review-spec` is unavailable; direct review completed on 2026-10-09 covering ownership, errors, security, retry races, compatibility, testability and bilingual equivalence. No blockers. User approved the proposed public-registry/manual/pinned-retry plan with “帮我改”. Approval does not authorize commit, push, deployment or cloud writes. Implementation and verification records will be reconciled below.

Config GET accepts optional UUID `requestId`; an owner-scoped existing snapshot bypasses discovery even when reopening a failed task. The existing UI passes its request identity; this is API wiring, without a visual/interaction redesign. Direct review confirms this completes FR-3 rather than expanding scope.

Client config/task requests allow 75 seconds so the 60-second resolver can return a clear error. Build timestamps preserve nanosecond order (RFC3339, at most 9 fractional digits).
