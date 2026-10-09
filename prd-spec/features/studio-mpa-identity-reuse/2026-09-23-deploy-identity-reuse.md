# Reuse Studio Identity for managed MPA creation

[中文版](2026-09-23-deploy-identity-reuse.zh.md)

- Change ID: `studio-mpa-identity-reuse`; created/revised 2026-09-23; status: approved.
- Approved by the user in this task after reviewing the environment-backed approach.
- Components: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md).

## Background, goals, and scope

`veadk studio deploy` persists Studio UserPool/client UIDs and later its OAuth callback in VeFaaS. The legacy MPA creation path resolves their names, but managed creation loads Identity names and callback only from YAML. The new shared PostgreSQL Workspace is prepared during MPA creation, not Studio deployment, so it cannot store deployment-time Identity metadata. The goal is for later managed MPA creations to use the Studio login resources automatically. No new PostgreSQL table, browser input, UserPool/client creation, or update of existing Runtimes is in scope.

## Scenarios and requirements

- `FR-1`: After Studio deployment identifies its UserPool/client, resolve their names with deploy credentials and persist names, Identity region, and `https://<studio-host>/oauth/callback` as non-secret VeFaaS environment values in the second release. Existing UID and Studio login callback behavior is preserved.
- `FR-2`: Managed MPA creation merges those server-owned values into the profile before the child process performs cloud writes. The child loads the same values from inherited environment after restart. It injects `MPA_USER_POOL_NAME`, `MPA_USER_POOL_CLIENT_NAME`, `IDENTITY_CALLBACK_URL`, and `IDENTITY_REGION` into the new Runtime.
- `FR-3`: A partial deployment identity set, or an explicitly different YAML Identity value, fails locally with a safe configuration error. A complete matching YAML set is accepted. When no deployment identity exists, standalone CLI/YAML behavior is unchanged. Identity values never enter the browser request or task database.

## Design and impact

Use four `VEADK_STUDIO_MPA_*` environment keys; reuse existing `IdentityClient.get_user_pool_resource_names` and the managed profile/Runtime environment path. The VeFaaS second release owns the public callback URL. The profile loader is the shared boundary for Studio inspection, task admission, and the fixed runner; it performs all-or-none and conflict checks before provisioning. Studio env wins only where YAML is absent. An explicit mismatch is rejected, including `managed.runtime.env`. Identity region is required because it may differ from deployment region. No schema, frontend API, task payload, or dependency changes. UserPool and callback names are not credentials; AK/SK and client secret remain server-only.

Failure to resolve resource names stops deployment with a redacted operator error. Callback registration retains its current warning behavior. Existing deployed Studio functions need a redeploy to receive the new values; existing MPA Runtimes are not modified. Live Identity/VeFaaS/Runtime E2E is not performed in local tests.

## Tasks, acceptance, and review

- `T-1` (`FR-1`, `AC-1`): Save the four values on the second VeFaaS release; test external UIDs and non-Beijing Identity region.
- `T-2` (`FR-2`, `FR-3`, `AC-2`): Merge and validate server environment in `load_profile`, then inject the resolved region in managed Runtime settings; test missing, matching, conflicting, partial, and standalone cases.
- `T-3` (`AC-3`): Update bilingual contract/operator docs and run affected Python tests, pre-commit, and broader regression as feasible. Record actual results below.

Review: no new PG table because that PG does not exist at Studio deployment; no browser Identity fields or secrets; validation occurs before cloud writes. The user approved the environment-backed design. Risks: cloud callback registration can still warn and live provider permissions/Runtime startup remain unverified.

## Verification record

On 2026-09-23, the implementation passed `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_studio_deploy_target.py tests/cli/test_cli_mpa.py -q` (427 tests). Isolated changed-line coverage is 19/19 executable lines (100%): 13/13 in managed configuration, 2/2 in Runtime identity application, and 4/4 in Studio deploy. A combined pytest-cov run failed due Pydantic/SDK collection behavior under instrumentation; the identical affected suite passed without instrumentation. The broad suite reported 5,189 passed, 9 failed, and 2 collection errors: 6 Harness failures require the absent optional `llama_index`, 2 Skill version failures have an unrelated source-region mismatch, 1 Workspace Editor failure lacks `node` on PATH, and 2 Sandbox test modules require the absent optional `anthropic`. Pre-commit passed. Pyright with the project interpreter reported 36 existing errors, none in added lines. No frontend source/assets changed, so frontend build is not applicable. Real cloud Identity/VeFaaS/Runtime E2E: not run; deployment permissions and callback behavior remain operational verification items.
