# MPA A2A discovery defaults

[中文版](2026-09-23-mpa-a2a-discovery-default.zh.md)

- Change: mpa-a2a-discovery-default; date: 2026-09-23; status: implemented.
- Contract: [MPA provisioning](../../specs/mpa-runtime-provisioning/README.md).

## Evidence and scope

Live read-only comparison confirmed that the old Runtime leaves DISABLE_JWT_AUTH unset, returns 404 from list-apps and 200 from the A2A agent card, and Studio uses a2a-default. The new Runtime receives DISABLE_JWT_AUTH=true from build_runtime_env, advertises default, and fails REST profile-status with 500 because no JWT public key is configured. Both support A2A discovery. Images differ, but this fix does not change the image.

## Requirements, design and acceptance

- FR-1 / T-1 / AC-1: Default creation to DISABLE_JWT_AUTH=false and ENABLE_A2A=true, retaining A2A_TIP_VERIFY_ENABLED=false and outer Runtime key-auth. First reproduce with tests, then verify CLI environment and managed flat creation payloads.
- FR-2 / T-2 / AC-2: Preserve explicit extra_env and managed.runtime.env precedence; referenced Runtime/template environments retain existing behavior. General-agent behavior is unchanged; the Studio MPA proxy path compatibility follows the additional design below. Non-goals: enabling MPA_AGENTKIT_MODE, JWT provisioning, identity architecture migration, database changes.
- FR-3 / T-3 / AC-3: Update only the affected new Runtime's discovery configuration, release a new version on that Runtime, wait for Ready and application readiness, then verify list-apps 404, agent card 200, Studio a2a-default and an isolated test conversation. Never print credentials. Report failures without reverting unrelated resources.

## Files, risks and recovery

Affected: mpa_provision.py, test_mpa_provision_env.py, mpa_managed/test_service.py, bilingual provisioning specs and module READMEs. The user explicitly authorized restoring old A2A behavior and fixing the template. Code does not automatically migrate existing Runtimes; only the identified new Runtime is repaired here. Release can briefly interrupt that Runtime; preserve all other environment and image settings. Pending creation payload hashes remain strictly checked, with no configuration-drift bypass; old tasks reporting drift need their original configuration or a new creation. Operators remain responsible for explicit JWT bypass overrides.

## Design review

review-spec is unavailable; requirements, interfaces, security, compatibility, errors, testability and bilingual equivalence were reviewed directly. No blockers; the current user instruction approves this approach. Session state, streaming and cancellation logic remain unchanged; this selects the existing A2A protocol. Outer key-auth and REST JWT validation remain intact.

## Verification record

2026-09-23, current uncommitted diff. Detailed results are recorded below. Frontend build: not_applicable (no frontend changes). Full repository tests and pre-commit: not_run (no commit requested; run affected regressions first).

## Additional design review: shared public path

The live V4 send exposed a second cause: the shared public endpoint has a /runtime/<ID> prefix, but its agent card drops that prefix from /a2a/jsonrpc. FR-4 / T-4 / AC-4: only for a verified MPA Runtime, the Studio backend restores a /runtime/[a-z0-9-]+ prefix from the control-plane endpoint when the card is same-origin and its path is exactly /a2a/jsonrpc. Already-prefixed, cross-origin, custom RPC paths and URLs with query, fragment or userinfo remain unchanged; general agents are unchanged. Apply consistently to sending, stream fallback and history restoration. Add frontend/server/mpa_a2a.py, wire cli_frontend.py and add unit tests plus proxy integration coverage. Preserve failure/cancellation behavior without extra retries. Direct design re-review passed; this is necessary compatibility work within the user's approved A2A chat repair. Restart local Studio to load backend code; no frontend build required.

## Implementation and final verification

2026-09-23, current uncommitted branch diff: FR-1 through FR-4, T-1 through T-4 and AC-1 through AC-4 completed.

- `pass`: test-first reproduction produced 5 default-related failures; before path repair the expanded integration matrix produced 6 expected failures and 12 passes.
- `pass`: `UV_CACHE_DIR=/private/tmp/veadk-uv-cache uv run --extra dev pytest -q tests/integrations/test_mpa_provision_env.py tests/integrations/mpa_managed tests/integrations/test_mpa_runtime.py`, 366 passed. After correcting the test-helper typing, reran the environment and service targets: 37 passed.
- `pass`: `uv run --extra dev pytest -q tests/cli/test_cli_mpa.py tests/cli/test_frontend_runtime_proxy.py -k 'a2a or mpa'`, 32 passed; after path repair, `uv run --extra dev pytest -q tests/cli/test_mpa_a2a_url.py tests/cli/test_frontend_runtime_proxy.py --tb=short`, 106 passed, covering unchanged general-agent URLs, streaming/non-streaming/fallback and history restoration.
- `pass`: Ruff check/format for the 7 affected Python files, gitleaks and diff whitespace.
- `pass`: Pyright reports no errors for the template, environment/service tests and new URL helper/test. `fail`: whole-file Pyright for cli_frontend.py and the existing proxy tests reports 56 pre-existing errors; comparing diagnostic messages and filenames against HEAD copies yields identical results and no new diagnostics. Unrelated typing errors were not changed.
- `pass`: updated only 2 discovery variables on the new live Runtime, released V4, verified platform Ready and application readiness; the old Runtime remains V7 with unchanged configuration. New list-apps returns 404 and agent card returns 200.
- `pass`: after restarting local Studio, the real browser selected the new Runtime as a2a-default; an isolated test conversation returned final answer 2 to simple arithmetic, with reasoning and footer and no JWT/404 error. The test conversation is retained; no additional cloud resources were created. REST profile-status still requires JWT and is not an A2A acceptance condition.
- `not_run`: full repository regression and all-files pre-commit (large scope and unrelated uncommitted work; no commit requested); frontend build/layout scenarios `not_applicable` (no TS/CSS/generated asset changes). Live sandbox skills, cancellation and cross-process history restoration were not exercised; their protocols are unchanged.
- Restricted network prevented online uvx pre-commit resolution; the identical gitleaks hook passed from the existing offline cache. No global configuration change or gate bypass. No commit or push.

Final review added an empty-userinfo URL boundary regression: failed before the guard correction, then all 15 URL unit tests passed.
