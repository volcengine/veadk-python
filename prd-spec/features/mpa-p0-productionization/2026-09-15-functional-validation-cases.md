# MPA AgentKit P0 Functional Verification Cases

- Change ID: `mpa-p0-productionization`
- Status: `designed`; Step 2 upfront design, not executed
- Date: 2026-09-15
- Chinese: [2026-09-15-functional-validation-cases.zh.md](2026-09-15-functional-validation-cases.zh.md)
- PRD: [MPA AgentKit P0 Functional Migration](2026-09-15-mpa-p0-productionization-design.md)
- Browser runbook: [browser-cases.md](browser-cases.md)

## 1. Common execution and evidence rules

The evidence root is `evidence/{automated,postgres,browser,contract,live}/<run-id>/`. Run `mkdir -p` for the applicable directory before execution. Each item records `caseId/timestamp/repositorySHA/runtimeImageDigest/agentkitOpenAPIVersion/workerProtocol/environment/command/status/expected/actual/artifactPaths/cleanupResult`; status must be one of `pass|fail|blocked|not_run|not_applicable`. Logs, JSON, screenshots, and manifests must be redacted.

Commands/files marked "to add" below are deliverables of the corresponding slice. Their paths must be verified before execution; they are not capabilities that already exist. Mock, in-memory, PostgreSQL, browser, and live-cloud evidence cannot replace one another.

## 2. Coverage matrix

| AC | Case | Slice |
| --- | --- | --- |
| `AC-1` | `VC-06`, `VC-20A`, `VC-20B` | S1/live |
| `AC-2` | `VC-04`, `VC-05`, `VC-07`, `VC-20B` | M0/S1/live |
| `AC-3` | `VC-08`, `VC-09`, `VC-17`, `VC-18B` | S2/browser/PG |
| `AC-4` | `VC-10`, `VC-11`, `VC-18C` | S3/PG |
| `AC-5` | `VC-12`, `VC-13`, `VC-18D` | S4/PG |
| `AC-6` | `VC-02`, `VC-15`, `VC-18E`, `VC-20B` | M0/continuous/live/PG |
| `AC-7` | `VC-14`, `VC-17`, `VC-18C` | S3/browser/PG |
| `AC-8` | `VC-16`, `VC-17` | S1-S5/browser |
| `AC-9` | `VC-19`, `VC-21` | S5/live |
| `AC-10` | `VC-16`, `VC-19`, `VC-22` | S5 |
| `AC-11` | `VC-02` local subset, `VC-03`, `VC-01`, `VC-20B` | M0 local / S5 live |
| `AC-12` | `VC-18A`, `VC-18B`, `VC-18C`, `VC-18D`, `VC-18E`, `VC-19` | M0-S5/PG |

## 3. Case details

### VC-01: Studio-to-Runtime Profile write path

- Preconditions: an isolated deployed mpa-agent accepts the validated Studio principal; resource prefix is `mpa-p0-e2e-*`; the live manifest is redacted.
- Command: `scripts/verify-mpa-p0-e2e.sh --manifest <redacted-json> --case VC-01` (runner exists; the `VC-01` live driver stage is added with S1).
- Input: two Studio Agent draft/Profile apply requests carrying `sourceProfileId + digest` and no caller-assigned revision.
- Expected: Runtime prepare -> Profile apply/status -> update/replay -> delete succeeds; Runtime returns revisions 1 and 2; no Managed Agent API is called and cleanup leaves no residue.
- Evidence: `evidence/live/<run-id>/VC-01.json`, request IDs, version sequence, and cleanup report.
- Failure handling: a deployed failure blocks release and returns to the owning S1/S5 task; it does not invalidate the completed local M0 gate. Do not substitute an arkcli subprocess.

### VC-02: unified RuntimePrincipal

- Preconditions: live Studio OAuth/gateway, custom-JWT Runtime, A2A TIP, and a revocable test principal.
- Command: live runner `--case VC-02`; Runtime `uv run pytest -q tests/test_runtime_principal.py` (to add).
- Input: valid bearer/TIP, wrong issuer/audience/kid, expired or missing-claim token, cross-scope principal, and revoked principal.
- Expected: bearer and TIP map to the same principal; every invalid request returns 401/403 before side effects; JWKS rotation converges.
- Evidence: `evidence/live/<run-id>/VC-02.json` and JUnit; record only issuer, audience, TTL, and kid hash.
- Failure handling: a local contract failure blocks S1; a deployed issuer/JWKS/revocation failure blocks release. Do not bypass by disabling JWT, using a Runtime key, or trusting a user header.

### VC-03: Studio Profile mapping and Runtime client contract

- Preconditions: fixed Studio AgentDraft and Runtime Profile DTO/error fixtures.
- Command: `uv run --extra dev pytest tests/frontend/server/mpa/test_runtime_profile_client.py tests/frontend/server/mpa/test_profile_mapping.py -q` (`test_runtime_profile_client.py` exists; `test_profile_mapping.py` is added with S1).
- Input: deterministic AgentDraft normalization, supported/unknown fields, create/update preconditions, Runtime timeout, HTTP error, and non-JSON response.
- Expected: Profile DTO/digest are stable; bearer, idempotency key, and exactly one of `If-None-Match`/`If-Match` are forwarded; conflicts map to `409 profile_version_conflict`; request ID is retained; Managed Agent/OpenTOP call count is zero.
- Evidence: `evidence/contract/<run-id>/VC-03.xml` and fixture diff.
- Failure handling: return to Step 1 to fix the contract or adapter; do not loosen the schema or swallow errors.

### VC-04: Profile preconditions and versions

- Preconditions: Runtime local backend with empty-Profile and existing-Profile fixtures.
- Command: `PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_profile_apply.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-04.xml` (to add).
- Input: `If-None-Match`, `If-Match`, both headers, neither header, stale ETag, same operation key with same/different digest.
- Expected: respectively success, success, 400, 428, 412, idempotent replay/`409 idempotency_mismatch`; Runtime allocates exactly one new revision only on successful CAS and returns a strong ETag.
- Evidence: JUnit plus revision-count/current-row assertions.
- Failure handling: fix precondition/service/store and rerun; do not weaken conflict assertions.

### VC-05: Runtime operation ledger

- Preconditions: an in-memory store with an injectable clock and a 24-hour TTL fixture.
- Command: `PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_runtime_operations.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-05.xml` (to add).
- Input: same key with same/different hash for Profile/run/upgrade/continue, cross-principal access, and TTL boundaries.
- Expected: unique ledger, same-request replay, different-request 409, unauthorized records hidden, queryable state, and a pending Profile never becomes current.
- Evidence: JUnit, operation state sequence, and secret-free snapshots.
- Failure handling: fix ledger uniqueness/authorization/expiry logic; PostgreSQL races are revalidated by VC-18B/C.

### VC-06: durable MPA lifecycle operation

- Preconditions: a TOS fake supporting forbid-overwrite/ETag; Runtime/Profile/smoke adapters with injectable failpoints.
- Command: `uv run --extra dev pytest tests/frontend/server/mpa/test_agent_operations_repository.py tests/frontend/server/mpa/test_agent_operations_service.py tests/frontend/server/mpa/test_agent_routes.py -q` (to add).
- Input: create/update idempotency keys; lost first response; crashes before/after Runtime, Profile, and smoke; cleanup failure.
- Expected: both writes return `202 + operationId`; the same key restores the original operation; active list finds it; retry resumes from a safe stage; each side-effect count is at most one.
- Evidence: `evidence/automated/<run-id>/VC-06.xml`, TOS ETag, attempt/effect counts, and stage sequence.
- Failure handling: any duplicate Runtime/Profile effect or lost refresh state blocks S1.

### VC-07: Profile field mapping

- Preconditions: fixed Studio AgentDraft/Profile fixture and runtime Profile DTO.
- Command: VeADK `uv run --extra dev pytest tests/frontend/server/mpa/test_profile_mapping.py -q --junitxml=prd-spec/features/mpa-p0-productionization/evidence/contract/<run-id>/VC-07-veadk.xml`; Runtime `uv run pytest -q tests/test_profile_apply.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/contract/<run-id>/VC-07-runtime.xml` (targets to add).
- Input: all supported fields, Skill without version, unsupported Tool/Multiagent, Secret, and signed URL.
- Expected: map `sourceProfileId`, name, description, System, Model, Tools, Skills, MCP, Multiagent, and allowlisted Metadata; Runtime allocates `profileRevision`; resolve resource versions first; unsupported fields return 422; only Secret references cross the boundary.
- Evidence: `evidence/contract/<run-id>/VC-07.json` and JUnit from both repositories.
- Failure handling: fix mapping/allowlist; do not silently drop unknown fields and then claim applied.

### VC-08: execution-config CAS

- Preconditions: Runtime local backend, Session revision 1, and resource-resolver fixture.
- Command: Runtime `uv run pytest -q tests/test_session_execution_config.py tests/test_session_execution_config_service.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-08.xml`.
- Input: missing/stale/correct ETag, replace/clear/inherit, unavailable/revoked resources, and an active Turn.
- Expected: missing ETag returns 428 and stale ETag returns 412; configuration semantics are exact; failure creates no revision; the active Turn is unchanged and the next Turn uses the change.
- Evidence: JUnit plus revision/effective-reference/Turn-record snapshots.
- Failure handling: fix CAS/resolver/transaction; revalidate with two connections in VC-18B.

### VC-09: explicit Profile-revision upgrade

- Preconditions: Session pinned to N, N+1 Profile applied, and an invalid-target fixture available.
- Command: Runtime `uv run pytest -q tests/test_session_execution_config_service.py -k profile_upgrade --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-09.xml`.
- Input: valid/repeated/old-ETag/unapplied/missing/downgrade version and override/clear/inherit.
- Expected: target Profile becomes the new base, override/clear are retained, and inherit follows the new defaults; an invalid target is rejected atomically; the active Turn uses N and the next Turn uses N+1.
- Evidence: JUnit and before/after revision and Turn comparison.
- Failure handling: immediately block S2 if a failed upgrade changes the old revision.

### VC-10: strong Run idempotency

- Preconditions: Session/config fixture and a countable dispatcher.
- Command: `PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_run_acceptance.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-10.xml` (to add).
- Input: missing key/version, stale config, same key with same/different payload, and concurrent requests for the same Session.
- Expected: explicit 4xx; stale config fails before a side effect; same request returns the same invocation; different content returns 409; only one active Turn exists.
- Evidence: JUnit, operation/Turn/inbox rows, and effect count.
- Failure handling: any duplicate effect blocks S3.

### VC-11: Outbox crash recovery

- Preconditions: injectable dispatcher and commit/dispatch/writeback/terminal failpoints.
- Command: `PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_turn_dispatcher.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-11.xml` (to add).
- Input: each failpoint and Runtime restart.
- Expected: unique dispatch key; dispatcher attempts may retry, but the external A2A Task/Turn/side-effect count is exactly one; operation/Turn/inbox converge.
- Evidence: JUnit, attempt count, effect count, and recovery-state logs.
- Failure handling: duplicate external effects or a lost intent blocks S3; deleting duplicate records afterward is not an acceptable pass.

### VC-12: Pause barrier

- Preconditions: fake clock and a participant fixture with a primary executor plus two workers.
- Command: `PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_turn_participants.py tests/test_turn_control_api.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-12.xml` (first file to add).
- Input: all/partial ACKs, stale-generation ACK, lease expiry, pause/spawn race, and repeated/conflicting control key.
- Expected: paused only after all participants ACK the same generation; other cases remain pausing or become a classified failure; stale ACK is ignored; idempotent results remain stable.
- Evidence: JUnit and participant generation/ACK/lease timeline.
- Failure handling: an incorrect paused state or a stale ACK changing state blocks S4.

### VC-13: Resume and continuation

- Preconditions: fake clock, outbox dispatcher, and recoverable/unrecoverable owner fixtures.
- Command: `PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_turn_continuation.py tests/test_turn_safe_point_spike.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-13.xml` (first file to add).
- Input: paused for 299/300/301 seconds, viable/lost lease, restart, and repeated/concurrent continue.
- Expected: resume the original Turn at <=300 seconds; otherwise return only new-turn-required; explicit continue creates one linked Turn; outbox is recoverable.
- Evidence: JUnit, fake-clock timeline, old/new Turn, and dispatch intent.
- Failure handling: real sleeps, automatic new-Turn creation, or duplicate effects block S4.

### VC-14: persistent SSE replay

- Preconditions: persistent ADK events, inbox-terminal fixture, and rebuildable StreamHub.
- Command: `PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_session_sse_persistent_replay.py tests/test_session_sse_edges.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-14.xml` (first file to add).
- Input: valid/unknown cursor, cross-Pod/restart, persistent/live overlap, queued/running/error/aborted states, and different invocations.
- Expected: replay only events after the cursor; unknown cursor returns 410; text/usage/artifact/terminal each appears once; error/aborted are accurate; no terminal means no success; invocations do not mix.
- Evidence: JUnit and SSE `id/event/data` sequence JSONL.
- Failure handling: never replay everything for an unknown cursor; duplicate or incorrect terminal state blocks S3.

### VC-15: Secret migration and leakage

- Preconditions: schema 0 containing a canary secret and a fake secret provider that can succeed or fail.
- Command: `PYTHONPATH=. SESSION_BACKEND=local uv run pytest -q tests/test_secret_reference_migration.py tests/test_session_redaction.py tests/test_runtime_console_api.py --junitxml=<veadk-worktree>/prd-spec/features/mpa-p0-productionization/evidence/automated/<run-id>/VC-15.xml` (first file to add).
- Input: new plaintext write in AgentKit mode, interrupted/retried migration of an old value, legacy read-only path, and old-image rollback.
- Expected: reject new plaintext writes; clear only after successful conversion to a reference; retain on failure; retry without duplication; no canary in API/log/trace; fence incompatible rollback.
- Evidence: JUnit, before/after DB snapshots showing only empty/ref-type values, and secret scan.
- Failure handling: any leak or data loss blocks release.

### VC-16: MpaAgentView and page isolation

- Preconditions: BFF fixtures covering 0/1/N bindings, orphan, applied/target, and old Runtime.
- Command: `uv run --extra dev pytest tests/frontend/server/mpa/test_agent_view.py -q && npm --prefix frontend test` (first file plus `mpaAgents.test.mjs`/`mpaAgentDetail.test.mjs` to add).
- Input: every view state, same ID in different scopes, and a slow response during scope switching.
- Expected: the view model merges correctly; write gates are correct; MPA does not enter GitHub/generic-draft/evaluation paths; caches do not cross scopes; no Secret is exposed.
- Evidence: `evidence/automated/<run-id>/VC-16.json` and pytest/npm output.
- Failure handling: state misclassification or entry into a generic flow blocks S5.

### VC-17: real browser

- Preconditions: test-only scenario harness and gstack/Chromium available.
- Command: S1 runs BC-01/02 plus the BC-07 create-busy/IME subset; S2 runs BC-04/05; S3 runs BC-06; S4 runs BC-09; S5 strictly runs the complete BC-01 through BC-09 regression in [browser-cases.md](browser-cases.md).
- Input: creation/failure/refresh/two-client/upgrade/cursor/IME/narrow-viewport scenarios.
- Expected: slice subsets gate only their slice; `VC-17=pass` only after every S5 BC passes with no unhandled console error.
- Evidence: `evidence/browser/<run-id>/<case-id>/`.
- Failure handling: unavailable environment is `blocked`; Node tests do not substitute.

### VC-18A: PostgreSQL foundation

- Preconditions: Docker available; Runtime `docker-compose.test.yml`, schema-0 fixture, PG integration test, and Make target to add.
- Command: `make test-postgres TEST_SELECT='foundation or migration_harness'`.
- Input: PostgreSQL 16, schema 0, two connections, and restart/failpoint harness.
- Expected: container, migration runner, two connections, restart, and failpoint infrastructure work; base schema migration is reentrant; finally cleans up container/volume.
- Evidence: `evidence/postgres/<run-id>/VC-18A.xml`, image digest, schema dump, and cleanup.
- Failure handling: block S1; do not substitute in-memory tests.

### VC-18B: PostgreSQL Profile/Session CAS

- Preconditions: VC-18A and S2 implementation complete.
- Command: `make test-postgres TEST_SELECT='profile_cas or execution_config_cas or upgrade_cas'`.
- Input: two connections concurrently using the same ETag/Profile revision.
- Expected: one succeeds and one conflicts; no lost update; one current Profile/config revision.
- Evidence: `evidence/postgres/<run-id>/VC-18B.xml` and rows.
- Failure handling: block S2.

### VC-18C: PostgreSQL Outbox/SSE

- Preconditions: VC-18A and S3 implementation complete.
- Command: `make test-postgres TEST_SELECT='active_turn or ledger or outbox or sse_restart'`.
- Input: concurrent run, three failpoints, restart, and persistent cursor.
- Expected: one active Turn/effect; outbox converges; cursor replay is correct after restart.
- Evidence: `evidence/postgres/<run-id>/VC-18C.xml`.
- Failure handling: block S3.

### VC-18D: PostgreSQL Participants/Continuation

- Preconditions: VC-18A and S4 implementation complete.
- Command: `make test-postgres TEST_SELECT='participant or continuation'`.
- Input: concurrent ACK/lease/generation/continue.
- Expected: row lock/CAS are correct; full barrier; one linked Turn/effect.
- Evidence: `evidence/postgres/<run-id>/VC-18D.xml`.
- Failure handling: block S4.

### VC-18E: PostgreSQL Secret migration

- Preconditions: VC-18A and S5 Secret-reference implementation complete; schema 0 contains a canary plaintext value; the fake secret provider can succeed or fail.
- Command: `make test-postgres TEST_SELECT='secret_migration'`.
- Input: successful reference creation, provider failure, process interruption before clearing, restart/retry, and old-image rollback.
- Expected: clear only after reference success; retain on failure/interruption; no duplicate reference on retry; no canary in final DB/log/evidence; incompatible rollback is rejected.
- Evidence: `evidence/postgres/<run-id>/VC-18E.xml`, DB snapshots containing only empty/ref-type data, and secret scan.
- Failure handling: block S5 and release; local/fake results cannot substitute.

### VC-19: compatibility, regression, and performance

- Preconditions: S1 through S5 implementation and non-live Cases are complete, but `VC-21` has not run; M0 has recorded both SHAs/image digest/protocol versions. Run the compatibility preflight first, then VC-21, then rerun this Case's full regression/performance section as the final gate.
- Command: `scripts/verify-mpa-p0-contract.sh --manifest <redacted-compatibility-json> --matrix contracts/mpa-p0/compatibility-matrix.json`, followed by Runtime `make test && make coverage && make test-postgres`, VeADK `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" && npm --prefix frontend test && npm --prefix frontend run build && uv run --extra dev pre-commit run --all-files`. Performance runner: `scripts/benchmark-mpa-p0.py --warmup 5 --requests 100 --concurrency 10 --list-size 20`.
- Input: every PRD compatibility combination and fixed fixtures.
- Expected: matrix results match; MPA update/release/rollback write routes reject incompatible manifests before mutation; Runtime coverage >=95%; no regressions; performance report includes p50/p95/max/error rate.
- Evidence: `evidence/contract/<run-id>/VC-19.json` and test/build/coverage/benchmark output.
- Failure handling: a permitted combination failure or exceeded target blocks S5; a requirement outside the matrix returns to Step 1 first.

### VC-20A: S1 live creation to first chat

- Preconditions: M0 is green; S1 implementation is complete; isolated account/region/project, write/delete permissions, quota, cost cap, image digest, DB, and cleanup owner are in the manifest; ArkClaw endpoint is blocked.
- Command: `scripts/verify-mpa-p0-e2e.sh --manifest <redacted-json> --case VC-20A` (to add).
- Input: fresh Agent, minimal Profile, and valid model.
- Expected: creation operation, Runtime, Profile, deterministic smoke, mpa-agent Session, and first A2A/worker/result succeed; Session create/read, A2A acceptance, and worker/tool dispatch use the shared authorizer with zero effects after revocation; S2-S4 upgrade/cursor/continue is not required.
- Evidence: manifest, operation, HTTP/SSE, trace, and cleanup under `evidence/live/<run-id>/VC-20A/`.
- Failure handling: insufficient permission/quota is blocked; functional failure is fail; EXIT trap cleans up and cleanup failure blocks S1 separately.

### VC-20B: complete live creation, identity, and Profile regression

- Preconditions: M0 all green; isolated account/region/project, write/delete permissions, quota, cost cap, image digest, DB, and cleanup owner recorded in the manifest; ArkClaw endpoint blocked.
- Command: `scripts/verify-mpa-p0-e2e.sh --manifest <redacted-json> --case VC-20B --cases AC-11,AC-1,AC-2,AC-6` (to add).
- Input: fresh Agent, minimal Profile, valid model, and valid/invalid/revoked identities.
- Expected: creation through first A2A/worker/result; Profile update/replay/conflict; safe rejection; interruption recovery; final zero-residue cleanup.
- Evidence: manifest, operation, HTTP/SSE, trace, and cleanup under `evidence/live/<run-id>/VC-20B/`.
- Failure handling: insufficient permission/quota is blocked; functional failure is fail; an EXIT trap cleans up, and cleanup failure blocks separately.

### VC-21: Runtime lifecycle, rollback, and deletion

- Preconditions: VC-19 permits the target/rollback combination; live manifest contains current/target/rollback image digests; active-Session/shared-resource fixtures exist.
- Command: `scripts/verify-mpa-p0-e2e.sh --manifest <redacted-json> --case VC-21` (to add).
- Input: valid update/release, controlled failure, compatible rollback, incompatible downgrade, malformed compatibility manifest, delete preview with an active MPA operation, delete preview with an active Runtime Session, delete with idle visible Runtime Sessions, and final delete.
- Expected: every step has an operation ID/request ID/version timeline; controlled failure is recoverable; incompatible downgrade or manifest fails before mutation; compatible rollback passes smoke; delete preview reports blockers and cleanup stages before mutation; active operations or active Sessions prevent deletion with `409`; idle visible Sessions are deleted through Runtime `DELETE /api/v1/sessions/{sessionId}` before AgentKit Runtime deletion; final deletion leaves no residue.
- Evidence: version timeline, platform responses, smoke trace, and cleanup report under `evidence/live/<run-id>/VC-21/`.
- Failure handling: any unsafe mutation, false success, or residual resource makes `AC-9=fail`.

### VC-22: CLI parity

- Preconditions: shared `MpaControlPlaneClient` and CLI commands implemented; controlled BFF fixture available.
- Command: `uv run --extra dev pytest tests/integrations/test_mpa_control_plane_client.py tests/cli/test_cli_mpa_control.py -q` (to add).
- Input: create/update, operation list/get/retry, MPA Profile revisions, Session profile-upgrade, 409/412/428, old Runtime, and timeout/replay; no Managed Agent endpoint is called.
- Expected: CLI does not import a FastAPI route; it shares schema/client with UI; writes carry a key and handle 202; JSON is parseable, exit codes are stable, and no Secret is exposed; retry after timeout uses the same key and does not repeat a write.
- Evidence: `evidence/automated/<run-id>/VC-22.xml`, UI/CLI response comparison, and secret scan.
- Failure handling: any semantic divergence, duplicate write, or leak blocks S5.

## 4. Exit rules

1. M0 requires the local subset of `VC-02`, `VC-03`, `VC-18A`, and the live-runner dry-run. Deployed `VC-01/02` execute at `S5-14`; `VC-04/05` run after S1 implements them. These Cases cannot form an M0 dependency cycle.
2. Each slice's own Cases and continuous security Cases must pass before the next slice begins.
3. Live Cases require explicit authorization; missing permission is `blocked` and cannot be replaced by a mock.
4. Any P0/P1 Case failure returns to the corresponding SDD/TDD Task for repair and rerun.
5. Step 7 may proceed to two-round Review only after all P0/P1 Cases pass; Step 10 must pass E2E before commit preparation.
