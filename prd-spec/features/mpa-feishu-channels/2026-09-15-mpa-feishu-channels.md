# MPA Feishu channels

[中文](2026-09-15-mpa-feishu-channels.zh.md)

Change ID: mpa-feishu-channels. Date: 2026-09-15. Status: implementation and local verification complete; live deployment awaits test environment.

## Background and approval

The MPA Runtime already exposes `/api/v1/channels`, chat permissions and a two-step QR flow. Studio's Runtime proxy supplies the Runtime credential but MPA channel management previously required an administrator JWT. The user explicitly approved implementation of the staged Feishu plan, including Studio adaptation, on 2026-09-15. Real deployment target and test tenant remain unspecified.

## Goals, scenarios and scope

FR-1: Administrators configure one Feishu bot per isolated MPA channel database from Agent integrations. Given a compatible Runtime, scanning authorizes the app, then MPA registers and stores it; only BOUND means complete. FR-2: Manage allowed group IDs and session scopes; default new permissions to group_sender. FR-3: Show truthful configuration and delivery diagnostics, pending, failure and retry states. FR-4: Keep secrets server-side and deny channel management to non-admins even when they own a Runtime. Existing JWT and legacy QR contracts remain compatible. General channel registries, media, MCP and Skill management are outside this change.

## Design and affected files

Follow [component contract](../../../specs/mpa-channels/README.md). Reuse `frontend/src/adk/client.ts` and the AgentWorkspace integrations layout; create RuntimeChannels using existing Button/form styling, translations and cancellation. The Python proxy uses a small channel-policy helper for both proxy routes. MPA deployment accepts persistent CHANNEL_STATE_ENCRYPTION_KEY through existing extra_env; never generates a new key on update. Add CHANNEL_ADMIN_AUTH_MODE=runtime_key for newly provisioned MPA deployments. No credentials enter browser storage.

## Tasks and tests

T-1: Write proxy-policy and API client tests before implementation. T-2: Implement proxy header filtering and admin checks. T-3: Implement capability discovery, QR polling, diagnostics and group permissions UI. T-4: Verify targeted Python tests, Ruff/Pyright, frontend tests/build and browser interaction. Synchronize generated webui assets and frontend README. T-5: Record live smoke results only against an explicitly selected test Runtime/Bot/group.

## Acceptance and risks

AC-1: Unauthorized calls cannot cause channel mutations or inject a management header. AC-2: Switching Runtime or leaving cancels polling and ignores stale responses. AC-3: Failed/expired QR can be retried or replaced; missing capability/configuration has actionable feedback. AC-4: Allowed group CRUD and scope values match MPA contracts; errors preserve user input. AC-5: No appSecret returned by the new binding API. AC-6: Simulated tests and live Feishu verification are reported separately. MPA requires persistent DB and persistent encryption key; old images return unsupported. Gateway reachability and delivery are unknown until observed, not implied by configuration. Runtime API key mode is explicit administrator capability; browser access remains protected by Studio admin authorization.

## Design review

Manual review performed because review-spec skill is unavailable: checked ownership, security, compatibility, cancellation, error handling, testability and bilingual equivalence. No design blockers. User approval recorded above precedes implementation. Verification (2026-09-15): proxy-policy, MPA provisioning environment and Runtime proxy targeted tests passed; `npm --prefix frontend test` passed 1205 tests; added Vitest contract/interaction tests passed 5 tests; frontend TypeScript and production build passed and webui assets were synchronized. Browser checks used simulated APIs for unbound, QR to BOUND, group save, keyboard scope selection and 390px layout; the observed overflow was fixed. Live delivery/deployment: blocked, no test Runtime/Bot/group selected. Full-file Ruff: fail, cli_frontend.py has 86 findings both at HEAD and after the change; new files and mpa_provision.py pass. Pyright with the repository .venv reports 33 errors in cli_frontend.py both at HEAD and after the change; new proxy and provisioning modules have no type errors. Default whole-repository parallel Python regression and pre-commit: not_run; this change is not committed and affected-path targeted regressions were run.

Additional verification: the final Studio backend targeted suite passed 88 tests. Automatic approval rejected mounting private source into a third-party Gitleaks container, so Gitleaks did not run. A local Python credential-pattern check of added text across both repositories scanned 83 text inputs with 0 potential matches; it is not a full Gitleaks scan. Source diff whitespace checks pass; generated bundles retain trailing whitespace in upstream template strings without manual alteration.
