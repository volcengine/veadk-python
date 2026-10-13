# Preserve domain applications during Studio Skill/MCP updates

Status: implemented. Created: 2026-10-13. Verified: 2026-10-14.
[Chinese](2026-10-13-source-preserving-domain-updates.zh.md)
[Component contract](../../specs/studio-source-preserving-updates/README.md)

## Background and scope

The existing database domain application exposes Studio introspection but owns its
tool factories, dynamic core instruction and startup entrypoint. Mainline
`a7569a04` already supports source-preserving updates, but its generated MCP
replacement ignores the application's compatibility handler. Historical regressions
on `812faadf` failed for wrapper preservation, handler failure and invalid handlers.
Additional gaps affect deferred ADK loading, immutable overlay permissions,
application identity, repeated editing and the frontend MPA lifecycle.

The user requests the smallest complete change to update the existing V4 database
Skills and MCP through Studio. Preserve the existing application, Runtime identity,
scaling and model configuration. Real acceptance is limited to the explicitly
authorized V4 database Runtime; customer V4-2 resources are outside scope.

## Requirements and design

Live configuration review found generic-route injection of `MPA_AGENT_ID` and
`VEADK_STUDIO_ENVIRONMENT_ID` into a domain Runtime that has neither. Under the
existing preservation scope, source-preserving updates must not create MPA
identity/tags, reset environment-selection metadata, inherit Studio host settings,
or automatically resolve replacement model credentials. Existing values and
ordinary update behavior must remain unchanged. Extend the actual typed-route
regression with the UI MPA category and a host-only environment sentinel before
implementation. Existing strict disabled-Sidecar filtering remains separate.

1. Recover the deployed configuration using formal introspection and the exact OCI
   digest. Preserve private source and dynamic prompts; no Builder regeneration.
2. Build a small layer containing Skill selection/content, public MCP configuration
   and the compatibility bootstrap. Retain entrypoint and dependencies. Do not add
   a dependency on `veadk.aiops` or migrate to Managed shared.
3. Respect the application's MCP handler. For a supported single-root HTTP MCP
   application, populate its existing `MCP_SERVERS_JSON` bootstrap and validate the
   exact configuration before accepting the overlay. Handler errors fail closed;
   never replace domain wrappers with generic tools after an error.
4. Explicitly activate the overlay and retain application import paths and identity.
   Defer ADK import until the application selects its packages. Immutable revision
   directories must be readable by the existing non-root user.
5. Make final Skill selection authoritative across updates. Recover only the active
   overlay revision, honor OCI whiteouts and reject unsafe links/layouts.
6. Expose only validated public `sourceOverlay` metadata. Missing, malformed or
   mismatched metadata blocks editing; it cannot enable ordinary regeneration.
   Tokens are resolved in memory and passed only to the authorized control plane,
   never build context, browser storage, logs or evidence.
7. Source-preserving UI validation permits an unavailable runtime-owned prompt.
   Normal creation validation remains unchanged. Publishing this mode never calls
   MPA Profile operations. Reopening retains configured MCP credential references.

## Implementation and verification tasks

- [x] Reproduce affected regressions on current mainline before production edits.
- [x] Port only the source-preserving CLI, introspection and frontend fixes from
      `8fd2eff5`; exclude unrelated SDK plugins, updater and Harness features.
- [x] Add regressions to the required release workflow and default frontend suite.
- [x] Run targeted regressions, current dependency checks, Ruff, Pyright, frontend
      tests/build, the applicable release gate, pre-commit and unit regression.
- [x] Exercise the actual database domain factory offline; prove Skill replacement
      and MCP changes preserve SQL read-only/evidence wrappers.
- [x] Use real Studio editing and publishing against the authorized V4 database;
      verify subsequent recovery and real Skill/MCP tool execution.
- [x] Reconcile both document languages, customer instructions and evidence.

## Affected files and risks

Owned files are listed in the linked contract. Tests cover CLI recovery, generated
startup, metadata and frontend validation/lifecycle/storage. The current mainline
uses google-adk 2.7.x while the deployed image has its own pinned environment:
validate both layers; upgrading local Studio does not authorize replacing all
Runtime dependencies. Limited local disk space favors existing dependencies or
the authorized isolated Devbox build environment.

Cloud publication is not retry-safe: track candidate digest, Pipeline Run, Runtime
version and each write. Inspect an in-flight operation before any retry. Ready
status or an old successful Pipeline is insufficient acceptance evidence.

## Design review and authorization

Reviewed directly because `review-spec` is unavailable. Scope, ownership, error
handling, secret boundaries, compatibility, testability and bilingual parity agree
with the component contract. Implementation stays within the user's existing
authorization to minimally adapt and verify V4; no main-branch merge is implied.

## Verification record

2026-10-14; tested scope is `a7569a04` plus this patch. A fresh fetch confirms the remote base is unchanged.

| Check | Result and scope |
| --- | --- |
| Pre-change mechanism regressions | `pass`: reproduced 18 backend and 6 frontend failures; direct recovery also proves mainline enters ordinary regeneration incorrectly. |
| Related Python regression | `pass`: 325 tests on both the deployed dependency line and current-mainline dependencies (google-adk 2.7.1, agentkit-sdk-python 0.8.9). |
| Real database factory | `pass`: three offline tests cover MCP selection/removal, SQL write rejection before provider dispatch, and activation reading updated Skill content; the fixture blocks external network. |
| Frontend | `pass`: 1386 node tests, 72 Vitest tests and build; 22 Sidecar tests with statement/branch/function/line coverage 98.55/94.44/100/100%. |
| Mandatory backend release gate | `pass`: coverage 149 passed/1 skipped, 96% (required 91%); lifecycle 9, credentials 233, release 39. |
| pre-commit | `pass`: all-files Ruff 0.11.12 check/format, Gitleaks and YAML secret scans. After Go bootstrap stalled, an SHA-verified Gitleaks 8.24.2 binary ran the identical original entry; repository hooks and rules were unchanged. |
| Pyright | `fail`, existing baseline: candidate and mainline both have 37 diagnostics with older dependencies and 38 with latest dependencies; mapped messages/rules are identical, with no additions. An internal JS entry produced invalid stdlib diagnostics; the public `index.js` entry was used for the comparison. |
| Full Python | 7063 passed, 53 skipped, 4 xfailed and 3 setup errors in the Sidecar wheel build fixture. Offline build of the retained source succeeded; the original three tests passed separately without code/assertion changes (29.17 seconds). The first failure's specific cause is unconfirmed; this is not one green full-suite run. |
| Dependencies and resources | All 57 restored distributions match the lock; `uv pip check` passes. Initial missing-dependency 16 failures/2 collection errors and disk-exhaustion logs are retained; after removing reproducible ZIPs, the unchanged 325 tests pass. |
| Real Studio editing | `pass`: restored one Skill and six MCP entries, imported all seven files of the same-name Skill, and submitted five entries after removing vtrace through the real page. Passwords remain absent from browser storage. Discovery uses one explicit GetRuntime target; the account-list flow is not validated. |
| First publication | `pass`: V18 Ready, Release done, 100% traffic, scaling 0–10; 31,396-byte incremental archive, one Update and one Release, retaining the Runtime's pinned SDK/Core. |
| First live request | `pass`: 905.47 seconds, 22 calls/22 responses, nine successful business receipts; updated Skill marker observed, stream completed with zero error events, complete ordered seven-section report (8196 characters). Three tool error responses were returned and recovered; zero stream errors does not mean every tool attempt succeeded. |
| Repeated update | `pass`: V19 published entirely through the real Studio page, with one Update and one Release, a 6003-byte incremental archive, Ready/100% traffic/scaling 0–10 and unchanged protected environment. Reopening restores the retained Skill, six MCP entries and configured credential references. |
| Second live request | `pass`: 638.25 seconds, 11 calls/11 responses, three successful business receipts, retained Skill marker observed, stream completed with zero error events and a complete ordered seven-section report (6289 characters). No status-read failure or delivery interruption. Two tool error responses were recovered. |

Full logs and sanitized counters remain in the local task evidence directory; raw cloud responses and credentials are excluded from commits.

## Configuration overwrites found and fixed before publication

The live release request was stopped before cloud mutation, exposing two general defects:

1. Source-preserving updates inherited ordinary Description/APM writes. Under CON-1,
   omit `Description` and `ApmplusEnable` only in this mode; ordinary updates retain
   their behavior. Actual-route and SDK-serialization regression: four failing
   parameter combinations before the fix; five passing tests including the ordinary control.
2. The common route injected MPA/environment identity, inherited Studio host variables
   and automatically replaced model credentials. Preserve only the target Runtime's
   original values. Actual-route regression: four failures before the fix and five
   passing tests covering absent/existing credentials, retained identity, host isolation
   and ordinary MPA updates.

Both groups belong to the mandatory release gate. All 325 related tests, four backend
release stages and pre-commit pass after the fixes; Pyright retains the same 38 baseline
diagnostics. Configuration dry runs change only overlay/MCP and remove stale disabled
Sidecar fields. Core returns disabled before reading those fields; disable switches remain.

After the first Update, the task acceptance wrapper incorrectly expected the unpublished
version to have incremented and stopped Release. The platform instead keeps GetRuntime
on the published version; GetRuntimeVersion without a version returns VersionNumber=0
for the unpublished configuration. The wrapper was fixed with a mechanism regression.
After reconciling image digest, unpublished environment and protected fields, exactly one
Release resumed, without rebuilding or repeating Update. This was a local acceptance-wrapper
issue, not a product failure. The second round subsequently verified the full page publication flow without manual release continuation.

## Repeated MCP-only update when registry reads are denied

The second live publication failed before Runtime mutation. The same exact-image
manifest request fails with HTTP 401 after successful token issuance from both
local direct egress and authorized Devbox2. This is not evidence of a local-only
network fault. Studio therefore preserves opaque runtime Skill references; the
existing build validator correctly refuses to drop a previously selected overlay
Skill, but the user cannot finish an MCP-only update.

Within the existing CON-1/CON-3 preservation scope, prepare the next overlay in an
isolated build stage based on the digest-pinned source image. Copy only retained
Skills selected by the previous overlay manifest into the new overlay, merge their
names into selected.json, and keep explicitly uploaded replacements authoritative.
Use a fresh temporary output directory so a non-root base-image user can prepare
it. A final stage copies the prepared overlay with readable permissions and retains
the source image's entrypoint/user/dependencies. Bind the revision hash to source
digest as well as input files because retained content now depends on that source.

Reject symlinks, special files, missing manifests/files, selection mismatches and
combined Skill file/byte limits; never drop the validator or silently omit Skills.
Add red/green regressions through the generated build script and enforce them in
the existing source-overlay release gate. Verify unchanged, replaced, removed and
repeated inherited Skills, plus malformed and unsafe inputs. The same exact V4
Runtime must then pass real page publication and data-plane acceptance. No registry
permissions or unrelated resources are changed. This is an implementation review
of the already-authorized continuous-update requirement, not new product scope.

Continuous-rebuild verification: generated-script regressions reproduced four failures
before the fix, then 11 passed; three additional base/combined-limit checks joined
the mandatory gate. Focused regression: 119 passed. Actual database factory: three
passed. Mandatory backend gate: 149 passed/1 skipped, 96% coverage; lifecycle 9,
credentials 233, release 39 passed. Ruff/pre-commit and secret scans pass. Pyright
on the changed builder module is zero, unchanged from the prior check; the other
38 baseline diagnostics remain. The corrected live page submission created a new
Pipeline Run and completed V19 publication. Second-round data-plane acceptance and reopening both pass.

## Submission baseline and commands

A fresh fetch and `git rebase --autostash origin/main` retain the same `a7569a04`
base. Post-rebase affected unit regression passes: 339 tests in 196.89 seconds.
The exact local invocation was:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q tests/cli/source_overlay tests/cli/test_legacy_runtime_recovery.py tests/cli/test_runtime_update_recovery.py tests/cli/test_studio_rbac.py tests/integrations/agentkit/test_app.py
```

All-files pre-commit ran again after synchronization, using the existing locked
environment and the same SHA-verified offline Gitleaks entry described above.
Ruff checks/format and both credential scans pass. Bilingual identifier parity,
relative links and `git diff --check HEAD` pass. The full-suite setup errors and
pre-existing Pyright diagnostics recorded above remain visible limitations.

## Delivery and acceptance boundaries

Both live requests used the original customer host-IO alert and its historical
window through formal read-only APIs. The second prompt requested at most two
business queries; the agent actually performed three. This is recorded as a
remaining query-budget adherence issue, not evidence of strict model budgeting.
The update acceptance proves retained Skill execution, selected MCP configuration,
real business receipts, complete delivery and repeatable editing; it does not
prove every operation of all six MCP services or a separate SuperAgent/bot channel.

The candidate Studio ran locally against the exact authorized Runtime. The source
branch and regenerated assets are ready for integration; no official Studio
upgrade-channel release or mainline merge is claimed. Runtime SDK/Core remained
pinned to the existing deployment.
