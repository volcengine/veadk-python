# Studio MPA TOS IAM mount

[中文版](2026-10-12-bucket-only.zh.md)

- Change ID: `studio-mpa-tos-iam`
- Date: 2026-10-12
- Status: implemented; upstream targeted checks verified; historical V42 live evidence retained; upstream port not deployed; baseline-wide gates blocked
- Base: official `origin/main`, `812faadf`; initial implementation/verification base: `superops/main`, `035387d1`
- Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), session output storage.

## Lifecycle integration plan (2026-10-14)

The user approved an independent branch targeting
`superops-team/veadk-python:feat/mpa-lifecycle-upstream-20261013` at `2ffe6e14`.
Replace fork PR #25 only after the replacement exists; preserve the shared
source branch and official PR #1163 unchanged. Resolve the request/API/dialog
conflicts by retaining automatic OpenViking, per-agent PostgreSQL, dedicated
`aidb` name preflight/reservations and maximum-instance selection, while using
bucket-only IAM Role TOS configuration. Preserve both README release notes and
regenerate packaged WebUI assets with the normal build. No new interface
semantics, cloud deployment or existing-resource migration are intended.

Manual design review confirms the combination preserves each branch's approved
behavior, name reservations, request identity and transient TOS configuration.
No component semantics change beyond the existing Role design. Remove the
ported TOS section's conflicting CON-17 label; retain the target's BytePlus
CON-17 and all other lifecycle identifiers.

Verification on 2026-10-14 (base `2ffe6e14`, integration working diff):

- Added four combined lifecycle/TOS cases (two Python, two Vitest). Python
  request-module tests pass 18/18; dialog tests pass 67/67. The manual-mode test's
  initial incorrect expectation was corrected to the existing omitted-field
  contract; automatic mode retains `openvikingMode=auto`. No independent defect
  was confirmed.
- Managed MPA/Tool/resource-list pytest passes 1,038/1,038. Coverage run passes
  the same cases. Executable diff coverage against the target is 100%: Python
  102/102 and TypeScript 10/10, using utree with coverage.py XML / Clover XML
  and the user's 95% threshold (not an invented CI rule).
- Full frontend passes 1,389 Node tests and 105 Vitest cases; build,
  packaged-asset checks, i18n and all-file pre-commit pass. Python is 3.12.12.
- Full Python regression: 7,150 passed, 16 failed, 2 collection errors,
  59 skipped, 4 xfailed and 6 subtests passed (469.04 s, two workers).
  The target's clean archive reproduces all 16 failures / 2 errors
  (99 other cases pass): missing optional llama_index, openai_codex and anthropic
  dependencies. Changed-source Pyright reports the same 15 SDK constructor
  errors reproduced on target `mpa_tool.py`. These gates remain blocked/failing;
  no smoke execution or Python 3.10 result is claimed.
- Isolated local browser verifies combined automatic-OV/dedicated-PG/bucket
  submission without TOS keys, normal/empty/loading/error/retry states,
  keyboard bucket selection, task cancellation/retry, step navigation and a
  390px viewport. The wording-only change is visibly verified. APIs are mocked;
  this does not prove real cloud creation. Temporary harness files were removed.

This integration is implemented and targeted checks verified, not deployed.
Historical V42 cloud evidence below does not validate this new integration.

The user requested a wording-only amendment on 2026-10-14: the Studio hint now
states that without a selected bucket files remain in the sandbox's local
directory. Translate the hint consistently; the built-in no-mount default and
CLI/profile compatibility remain unchanged.

## Background and scope

Studio currently requires `tosAccessKey`, `tosSecretKey`, and `tosBucket` together.
`mpa_tool.build_tos_mount_config` always emits access-key authentication. The
AgentKit SDK supports `TOS_CREDENTIAL_TYPE_IAM_ROLE` without Credentials. The
existing managed IAM reconciler preserves extra bindings and rejects conflicting
policy documents. Its platform TOS policy does not grant business-bucket writes.

The user approved bucket-only Studio creation and automatic, additive bucket
authorization on 2026-10-12. This changes TOS mount authentication, not Studio
login, Runtime KeyAuth/JWT, or the Worker protocol. The initial implementation
scope excluded publication. The subsequent user request on 2026-10-12 authorizes
commit/push, updating the existing cloud Studio and creating a test MPA. Bucket
creation/public-policy changes and existing-Session migration remain out of scope.

## Requirements and scenarios

### Approved prefix amendment

On 2026-10-12 the user narrowed Studio selection to bucket names beginning with
`agentkit-platform-`. The selector requests an optional `namePrefix` on the
existing deployment-resource API; apply exact, case-sensitive prefix filtering
before search, counts and pagination. Unfiltered/general deployment queries keep
their behavior. Studio creation rejects other buckets, including stale drafts,
before cloud calls; standalone CLI/Worker bucket validation remains unchanged.
No role policies, public-bucket policies or Session paths are changed by this
amendment. Test allowed/excluded/lookalike names, empty selection, stale drafts,
query transport and pagination. Manual design review confirms these boundaries.
The earlier version was deployed as V41 with unchanged environment and matching
frontend asset hash. No MPA was submitted or bucket policy attached before the
user requested this amendment; cloud creation/E2E is on hold.

Prefix amendment verification: added 8 Python cases and 3 Vitest cases. The
related Python suite passes 754/754; dialog tests pass 46/46; full frontend tests
pass 1,377 Node tests plus 73 Vitest cases. Build, packaged assets (113 files/350
references), i18n, Ruff, changed-file Pyright and pre-commit pass. Executable diff
coverage for the four scoped files against HEAD is 100% (Python 22/22, frontend
10/10), parsed with utree using coverage.py XML and Istanbul Clover XML. The
initial tests failed on missing prefix behavior; related Studio fixtures were
updated without relaxing authorization ordering/failure assertions. Full Python
regression ran again: 6,495 passed, 6 failed, 2 collection errors, 19 skipped,
2 xfailed and 6 subtests passed. The failing Harness cases and missing optional
dependencies are the previously reproduced baseline blockers. The local browser
shows only matching buckets using simulated responses; temporary harness files
and Vite were removed. No existing defect was reported: this is an approved scope
change. This is the pre-publication evidence snapshot; the subsequent authorized
publication and live Role mount verification are pending and will be recorded
separately from these local results.

- FR-1: Show one optional bucket selector using the existing resource-list hook
  and DeploymentSelect; retain loading/error/empty/search/pagination/retry,
  disabled state, keyboard behavior, and cancellation. No TOS AK/SK input.
- FR-2: A nonempty Studio bucket chooses IAM Role using the actual Worker Tool
  role. Reject malformed names and legacy nonempty credential submissions safely.
  Remove credentials from recovered browser drafts. Empty selection retains the
  server profile (the built-in profile has no mount). CLI/YAML access-key mode remains compatible;
  explicit `tos-credential-type: iam_role` enables bucket-only managed profiles.
- FR-3: Before workload-identity/database/network mutations, verify the selected bucket belongs
  to the deployment account and region, then ensure one stable bucket-specific
  custom policy and its Global binding on the Worker role. Verify account/trust,
  policy content, and readback. Preserve unrelated policies/trust. Reject
  conflicts; recover missing-policy/create/attach races with a bounded timeout.
- FR-4: Grant `tos:HeadBucket` and `tos:ListBucket` only on the selected bucket;
  grant `tos:GetObject`, `tos:PutObject`, `tos:AbortMultipartUpload`, and
  `tos:DeleteObject` only on its `sandbox-session/*` objects. No other buckets,
  CreateBucket, bucket-policy/ACL changes, KMS grants, or wildcard object scope.
- FR-5: Emit IAM Role Tool mount without Credentials. Keep `/data/output`, the
  canonical per-session TOS path, and nonsecret Runtime mount flag/bucket.
  Reuse validation must reject authentication-mode/role mismatches, not just
  matching mount paths. Existing Tools and Sessions are never silently mutated.
- FR-6: Permission, ownership, configuration, and policy conflicts stop creation
  at the IAM stage with safe localized errors. Cancellation keeps durable IAM
  objects for retry. Cloud operations use fresh verified deployment credentials.

## Design and compatibility

Add an optional managed Worker credential mode while retaining the historical
access-key default for CLI. Studio's request contains only `tosBucket` and its
fixed runner applies IAM Role. Existing task identity/locking/cancellation remain
unchanged. Reuse existing IAM SDK boundary, canonical document comparison, and
error allowlist for an independently named bucket policy; do not edit
`VeADKMPARuntimeAccessV1`. Stable policy names avoid read/merge/write races
between different buckets. Identical concurrent operations converge.

The policy exposes bucket metadata through ListBucket but object access is
restricted to session outputs. The shared role grants all of its consumers that
same prefix access: per-session directories are not tenant authorization.
SSE-KMS buckets require separately approved key permissions. Old Studio clients
sending credential fields must refresh; they receive a safe validation error.
Legacy CLI access-key requests and general-agent deployment remain unchanged.

## Tasks and acceptance

| Requirement | Task | Acceptance | Evidence |
| --- | --- | --- | --- |
| FR-1, FR-2 | T-1: UI/API/config | AC-1: bucket-only payload, stale-secret stripping, selection states | config/routes tests and 43 dialog cases pass; isolated browser pass |
| FR-3, FR-4, FR-6 | T-2: IAM ensure and service wiring | AC-2: exact scoped policy, repeated/concurrent retry, failure/cancel boundaries | IAM/service tests pass |
| FR-5 | T-3: Tool payload/reuse checks | AC-3: no Credentials and strict mode/role validation; legacy mode unchanged | Tool/worker tests pass |
| All | T-4: docs/assets/gates | AC-4: targeted/full tests, build/assets, browser states, executable diff coverage >95% | targeted/build/assets/browser/coverage pass; full regression and Pyright have reproduced baseline blockers |

Run affected pytest modules first; then
`uv run --extra dev pytest -n 2 -m 'not codex_smoke and not piagent_smoke'`,
`npm --prefix frontend test`, build, asset verification, changed-file
Ruff/Pyright, i18n, secret scan, and diff whitespace. Coverage is executable
changed lines, not whole-module coverage. Browser checks use isolated mocked
provider responses; real IAM/mount E2E is not_run without separate authorization.

## Review and delivery

Manual design review substitutes for the unavailable review-spec skill. It
confirmed role ownership, additive policy scope, legacy CLI compatibility,
retry/cancel behavior, localization, and bilingual equivalence. The unavailable
ui-ux-pro-max skill is replaced by the repository SPEC/Foundation and existing
selector behavior. Test-skill production-edit restrictions do not apply to the
user's explicitly authorized feature implementation; tests retain strict
expected-behavior assertions.

## Verification and change record — 2026-10-12

Changed the Studio request/dialog, managed Worker configuration, IAM reconciliation,
service ordering and Tool metadata validation; updated both component specs and
operator guides. No MPA Agent/Worker source changes are needed: existing Session
mount paths remain unchanged. Reused resource selectors and their existing stylesheet
instead of creating a new UI system. Temporary browser harness/source files were
deleted and its local Vite process stopped; production assets were rebuilt.

- **pass:** Python 3.12.12, `tests/integrations/mpa_managed` plus
  `tests/integrations/test_mpa_tool.py`: 719/719, including 42 net-new cases versus
  the 677-case baseline. Initial contract tests failed before implementation.
  With coverage enabled, Pydantic lazy import fails during collection in the
  plugin environment; explicitly importing `pydantic.RootModel` before
  `pytest.main([...])` enables the same 719 tests with coverage, without product
  or dependency changes. The baseline's service collection reproduces this
  coverage import error too. Python 3.13 was not used as final verification.
- **pass:** executable changed-line coverage 100%: Python 97/97 from
  `utree coverage parse` using diff hunks and coverage XML; frontend 9/9 using
  Istanbul statement-start locations intersected with changed lines. Unchanged
  source, type-only lines, tests, docs and generated bundles are excluded. This
  is incremental line coverage, not whole-file or branch coverage.
- **pass:** `npm --prefix frontend test`: 1,377 Node tests and 70 Vitest cases;
  `npm --prefix frontend run build`, `check:i18n`, `test:webui-assets` (113 files,
  350 internal references), Ruff, pre-commit all files and `git diff --check`.
  Vite reports its existing large-chunk warning.
- **pass:** real local browser with simulated API responses: normal selection,
  no TOS key inputs, loading, empty, error/retry, search, pagination, keyboard
  selection, Chinese search input, close and 390px viewport. This is not live
  cloud IAM/mount verification or a real OS IME composition test.
- **fail, baseline reproduced:** full parallel regression: 6,485 passed,
  6 failed, 2 collection errors, 19 skipped, 2 xfailed, 6 subtests passed. The
  exact six Harness cases and two self-host Sandbox collection errors recur in
  an isolated archive of `035387d1` using the same interpreter (60 passed);
  optional `llama_index`/`anthropic` dependencies are absent. These unrelated
  dependencies/implementations were not changed or installed to mask the gate.
- **fail, baseline reproduced:** Pyright with `.venv/bin/python`: 15 SDK
  call-signature errors in unchanged legacy `mpa_tool.py` calls. A temporary
  copy of the exact baseline file reports the same 15 errors and was deleted.
  The other changed production Python files have no Pyright diagnostics.
- **not_run:** cloud IAM writes, live Role-mounted Session E2E, deployment,
  image publication, commit and push. Existing Tools/Sessions remain untouched.
  Shared-role access, existing denies, public bucket policy and KMS restrictions
  remain operator-visible limitations; a granted policy is not proof of cloud
  filesystem access.

Implementation review covered fixed bucket-derived names, account/region/trust
verification, exact resource prefixes, additive idempotency/races, safe failures,
timeouts/cancellation and legacy CLI compatibility. No existing-policy rewrite or
global object permission was introduced. Full-suite/typing gates cannot be called
passing; live acceptance remains separate from this local implementation.

### Authorized publication and live acceptance

On 2026-10-12, rebased against unchanged `superops/main` and pushed implementation
commit `267705ef` to `polaris/czh/studio-mpa-tos-iam-role`. After synchronization,
754 related Python cases and 1,377 Node plus 73 Vitest cases passed again;
pre-commit, i18n and packaged assets also passed. The baseline-wide blockers
recorded above remain unchanged.

Updated only the existing Studio code bundle to V42, preserving its environment
hash and branding. The packaged wheel's seven production source files and all
WebUI assets matched the checkout; remote entry JS/CSS/logo hashes matched the
local package. Wheel SHA256:
`023bf085371cdc7c285b5e60bfcb2dd08e390c1935b7a995475c82c47b925a14`.
No new Runtime/Worker image was built for this Studio-only publication.

Remote Studio showed four platform-prefix buckets instead of eighteen unfiltered
buckets and rejected the old `agentkit-demo` draft. Created the test MPA
`role-tos-e2e-20261012-a` using `agentkit-platform-2112682748`, with no TOS AK/SK.
Runtime `r-yex3bbopvkwqejues1lc` became Ready and `/readiness` returned 200.
Worker `t-yex3bb51xcwqejuen9oc` was Ready with Role
`IDRoleForArkClawShareAgent`, `TOS_CREDENTIAL_TYPE_IAM_ROLE`, no Credentials,
read/write `/data/output`, and the expected base mount path. IAM readback confirmed
the exact bucket/session-prefix custom policy was attached. The role already had
the platform-bucket system policy; additive reconciliation does not narrow those
pre-existing permissions. The selected bucket had no public bucket policy.

Two conversations submitted through remote Studio executed actual Sandbox
commands. GetSession readback confirmed separate
`/sandbox-session/tool-{tool_id}/session-{user_session_id}/` mounts. Both wrote
`role-tos-e2e.txt` with different A/B markers; the second initially found no file.
Independent owner-side TOS reads (no owner-side writes) verified both objects and
that A remained unchanged after B. A's Sandbox result, TOS object and browser
download shared SHA256
`e762fa20c53dd7394b3f89af8e084e42d486a8e241fa37d68acbd695a17b82a7`;
B's Sandbox result and TOS object shared SHA256
`0d797e5173d581880100a21f25a7e00f4990d82b440c4f01f01d78e8776b1e6e`.
The browser download event waiter expired after 45 seconds, but the download
subsequently completed and its local bytes were verified; this was not an
endpoint failure. The image does not expose `/ready?scope=execution` (404), so
execution proof comes from commands and object reads, not that readiness route.

The test MPA and its two output objects are retained for inspection. Existing
Tools/Sessions were not mutated. No repository exploration files remain. This
acceptance does not test role permission subtraction, KMS-encrypted buckets,
explicit Deny policies, independent principals or real business-channel delivery.

### Official upstream PR preparation

The user subsequently requested a PR to `volcengine/veadk-python:main`. The fork
branch's merge-base would include unrelated history, so the two feature/evidence
commits were transferred onto official main `812faadf` in a separate branch,
`czh/studio-mpa-tos-iam-role-upstream`. The sole production-source conflict was an
import: preserve official `resolve_model_key` together with the TOS IAM ensure.
Generated WebUI conflicts were resolved by rebuilding from the upstream source,
not by choosing either old asset set. No unrelated fork commits were imported.

The two TOS ordering cases initially failed because their fake cloud did not
provide official main's new Ark key discovery dependency. Only these cases were
updated to mock that dependency, assert it was awaited with the correct profile
and cloud, and retain all grant-before-identity/error propagation assertions.
Both cases then passed. No production logic was changed to accommodate the tests.

Upstream verification with Python 3.12.12: 872 related Python tests passed;
1,377 Node tests and 75 Vitest cases passed; frontend build, i18n, assets,
Ruff 0.11.12 (repository-pinned version) and pre-commit passed. Incremental
executable-line coverage against official main was 100% (Python 102/102, TS
10/10), parsed with coverage.py XML and Istanbul Clover XML. The focused test
repair followed bits-unit-test-gen Steps 1-7; TOS orchestration coverage was 5/5
changed executable lines and utree flush completed.

Full upstream regression completed: 6,950 passed, 16 failed, 2 collection errors,
59 skipped, 4 xfailed, 6 subtests passed. Six Harness failures and two self-host
collection errors were reproduced on an isolated official-main archive with the
same interpreter (64 passed): missing optional `llama_index`/`anthropic`.
The ten Codex runtime failures were also reproduced on that archive: missing
optional `openai_codex`. The 15 legacy SDK call-signature Pyright errors were
reproduced from official main's original `mpa_tool.py`. These gates are not green.

The V42 cloud evidence above belongs to the original fork implementation. The
official-base port was not redeployed or browser/cloud E2E-tested in this PR
preparation task; its official model-key behavior is retained, not inferred to
have run in V42. The original fork PR and cloud resources remain unchanged.
