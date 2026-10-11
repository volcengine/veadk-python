# Studio MPA Profile Error Handling Bugfix

[中文版](2026-09-20-studio-mpa-profile-errors.zh.md)

## Metadata

- Change ID: `studio-mpa-profile-errors`
- Created: 2026-09-20
- Revised: 2026-09-20
- Status: `implemented`
- Related component specs: [Studio MPA Control Plane](../../../specs/studio-mpa-control-plane/README.md), [MPA Runtime Control](../../../specs/mpa-runtime-control/README.md)

## Background and Evidence

Local Studio Profile validation exposed three distinct failures:

- `GET /web/mpa/agent-operations?status=active` returned `503 mpa_operation_service_unavailable` when Studio was launched without `--dev` and no Studio TOS storage was configured.
- The selected Runtime `r-yev5cmzp4wzn6n5iodgd` in `cn-beijing` is `Ready` but still runs an older MPA image, version 14. Its native session API returns `401 {"detail":"X-Jwt-Token header is required"}` through `/web/runtime-proxy/.../api/v1/sessions`.
- The same Runtime's Profile status endpoint returns a plain `404 {"detail":"Not Found"}`, which previously surfaced as a raw safe error instead of the existing `profile_not_found`/orphan Runtime state.
- Current MPA Runtime images may expose Agent metadata only through the A2A virtual app. For example, Runtime `r-yeuujrrcowb21078p9jh` returns `200` for `/web/agent-info/a2a-default`, while `/web/agent-info/default` returns `404`, which previously surfaced as "Unable to load Agent details".

The first issue is a local launch-mode problem. The latter two are compatibility and presentation problems for old Runtime images that predate the AgentKit `Authorization` adapter and Profile status contract.

## Goals

- Start the local Studio in a configuration where the MPA operation service is available without production TOS.
- Preserve fail-closed Runtime authentication behavior; do not synthesize or forward `X-Jwt-Token`.
- Show actionable, localized UI errors for old Runtime images and keep the Profile page usable enough to show Runtime identity and capability state.
- Keep Profile writes, Session configuration, and Debug disabled when the Runtime contract is not compatible.

## Non-Goals

- No cloud Runtime mutation, image rollout, or automatic Runtime upgrade.
- No change to the Runtime authentication contract: current AgentKit-mode Runtime images must keep using `Authorization`.
- No submission of local browser evidence or other test artifacts.

## Requirements

| ID | Requirement |
| --- | --- |
| `FR-1` | Local `veadk studio --dev --vite` without Studio TOS must expose the process-local MPA operation repository so active operation recovery returns `200`. |
| `FR-2` | An upstream `401` whose detail requires `X-Jwt-Token` must be classified as `runtime_legacy_auth_unsupported`, not a generic session-list or runtime request failure. |
| `FR-3` | `GET /web/mpa/agents/{mpaInstanceId}/view` must return a normal `MpaAgentView` with Runtime metadata and a safe error for old or missing Profile endpoints instead of failing the whole page. |
| `FR-4` | The Profile page must display localized guidance and disable Profile write, Session config, and Debug controls when the Runtime image is not compatible. |
| `FR-5` | Runtime-backed Agent details must fall back to the A2A virtual app metadata when `default` agent metadata is absent. |

## Design

`frontend/server/mpa/runtime_client.py` now classifies upstream string error details:

- `X-Jwt-Token header is required` becomes `runtime_legacy_auth_unsupported`.
- plain 404 text from `GET .../profile-status` becomes `profile_not_found`.

`frontend/server/mpa/routes.py` treats `runtime_legacy_auth_unsupported` as a safe Profile-view error. The response keeps `bindingStatus=bound`, includes the Runtime metadata, omits Profile status, and returns `canWrite=false` plus `canDebug=false`.

`frontend/src/adk/client.ts` uses structured error parsing for Session list failures. For MPA Runtime sessions, the old `X-Jwt-Token` 401 becomes a localized upgrade message that preserves the raw detail for diagnosis.

`frontend/src/ui/AgentWorkspace.tsx` maps `safeError.code` to localized MPA control-plane messages and uses `capabilities.canWrite` to decide whether the Profile apply button is enabled.

`frontend/src/adk/client.ts` now falls back from `/web/agent-info/{app}` to `/web/agent-info/a2a-default` when the original agent-info request returns 404. It still propagates non-404, authentication, and server failures.

Local validation uses:

```bash
APP_ENV=development VEADK_MPA_TEST_SCENARIOS=0 uv run veadk studio --dev --host 127.0.0.1 --port 18179 --vite --no-open
VEADK_API_TARGET=http://127.0.0.1:18179 npm --prefix frontend run dev -- --host 127.0.0.1 --port 5179
```

## Affected Files

- `frontend/server/mpa/runtime_client.py`
- `frontend/server/mpa/routes.py`
- `frontend/src/adk/client.ts`
- `frontend/src/ui/AgentWorkspace.tsx`
- `frontend/src/i18n/resources/en-US/adk.json`
- `frontend/src/i18n/resources/zh-CN/adk.json`
- `frontend/src/i18n/resources/en-US/ui.json`
- `frontend/src/i18n/resources/zh-CN/ui.json`
- `tests/frontend/server/mpa/test_runtime_profile_routes.py`
- `frontend/tests/runSseAbort.test.mjs`
- `frontend/tests/agentWorkspace.test.mjs`

## Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Backend Profile routes | pass | `uv run --extra dev pytest tests/frontend/server/mpa/test_runtime_profile_routes.py -q` returned 28 passed. |
| Frontend source-contract tests | pass | `npm --prefix frontend test -- agentWorkspace.test.mjs runSseAbort.test.mjs` returned 1244 passed because the script still runs the repository frontend test set. |
| i18n parity | pass | `npm --prefix frontend run check:i18n` returned pass for 2 locales and 21 namespaces. |
| Local operation recovery endpoint | pass | With `--dev`, `GET /web/mpa/agent-operations?status=active` through Vite returned `200 {"operations":[]}`. |
| Old Runtime profile view | pass | `GET /web/mpa/agents/r-yev5cmzp4wzn6n5iodgd/view?...` returned `200`, Runtime metadata, `bindingStatus=orphan_runtime`, `canDebug=false`, and `safeError.code=profile_not_found`. |
| Old Runtime session list | expected limited | `GET /web/runtime-proxy/r-yev5cmzp4wzn6n5iodgd/api/v1/sessions?...` still returns upstream `401 X-Jwt-Token header is required`; the client now presents this as an old Runtime image compatibility message. |
| A2A agent metadata fallback | pass | `GET /web/runtime-proxy/r-yeuujrrcowb21078p9jh/web/agent-info/default?...` returned `404`, while `/web/agent-info/a2a-default?...` returned `200`; `getAgentInfo` now retries the A2A path and the frontend regression is covered by `runSseAbort.test.mjs`. |

## Risks and Follow-Up

The selected Runtime version 14 cannot be made fully compatible from Studio without updating the deployed Runtime image. The user should validate against a current Runtime image such as the already verified version 62 path for full Session list and chat behavior.
