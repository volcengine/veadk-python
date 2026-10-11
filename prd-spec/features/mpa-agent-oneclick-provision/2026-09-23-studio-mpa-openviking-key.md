# Studio MPA OpenViking credentials

[中文版](2026-09-23-studio-mpa-openviking-key.zh.md)

- Change ID: `studio-mpa-openviking-key`
- Date: 2026-09-23
- Component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-11

## Background and evidence

The prior ArkClaw flow injects `OPENVIKING_USER=default` along with URL, API Key and resource ID. The current managed Studio profile has no user setting or API Key, while the wizard claims the deployment service always supplies one. Creation tasks persist their nonsecret request payload in SQLite and return it in task snapshots, so adding the key to that payload would expose it.

## Goals, non-goals and scenarios

Add a masked API Key input to the OpenViking step. Entering URL, resource ID and key together injects the four ArkClaw variables into the new Runtime. Leaving all three blank injects none and removes any values inherited from a template or reference Runtime. The key must reach the child provisioning process without entering browser storage, task SQLite, status responses, logs or error details. Creating an OpenViking resource, changing existing agents or changing the legacy CLI are outside scope.

## Requirements and design

- **FR-1:** The OpenViking step displays an optional password-type `openvikingApiKey` field (maximum 512 characters) with accurate guidance. It stays in component memory and is not included in session-storage drafts. Failed retries can re-enter it; after a browser restart the user must re-enter it.
- **FR-2:** Authorized POST accepts the key, removes it before nonsecret task persistence, and passes it separately to the fixed child through stdin. Task snapshots and the SQLite file never include it. Unknown sensitive fields are rejected.
- **FR-3:** The three inputs are all required together or all blank. When filled, the runner injects `OPENVIKING_URL`, `OPENVIKING_RESOURCE_ID`, `OPENVIKING_API_KEY` and `OPENVIKING_USER=default`. When blank, it removes all four from the new Runtime, including inherited values.
- **FR-4:** Preserve existing request identity, retry and cancellation behavior. Do not return credentials from the configuration endpoint.

Affected files: Studio creation UI/API/i18n, `frontend/server/mpa_creation.py`, managed task/configuration code, paired component contracts and operator docs. The trust boundary remains the authorized Studio server; the key is transient process data, including in the child Runtime deployment request. The task payload remains durable and nonsecret. A server restart cannot recover an unsent key, so the user supplies it again on retry.

## Tasks, tests and acceptance

1. Add failing frontend, route, task-store and Runtime-env tests for the key path and non-persistence.
2. Implement the masked field, separated secret transport, Runtime override and default user setting.
3. Update both contract languages and user/operator docs; run targeted Python tests, frontend tests/build, Ruff, Pyright, asset checks and browser validation.

Acceptance: a submitted test key reaches the child and Runtime env; the browser draft, task response and SQLite do not contain it; all-blank input omits all four variables even when inherited; partial input is rejected; the user is `default` when enabled. No live OV/Runtime operation is necessary for unit validation.

## Review and verification

Design review checked the API boundary, secret lifetime, retry after restart, bilingual fields, compatibility and cancellation. The existing task store cannot hold a key securely; this design explicitly keeps it outside the durable payload. On 2026-09-23, targeted managed-creation tests passed (348 before the final no-override regression), frontend tests passed (1,305 Node and 36 Vitest tests), TypeScript and Pyright passed, the production build and packaged-asset check passed, and `git diff --check` passed. The full Ruff check reports pre-existing import/line-length findings in the touched modules; the E/F check excluding pre-existing E501 passed. Browser inspection reached the local login page but did not proceed through its terms acceptance; live OV/Runtime provisioning was not run.

The all-or-none follow-up on 2026-09-23 passed 363 managed-creation tests, 1,305 Node and 36 Vitest frontend tests, TypeScript, Pyright, Ruff E/F excluding pre-existing E501, the production build, the packaged-asset check and `git diff --check`. Runtime-env tests cover blank and complete input across template, reference and flat sources. Live OV/Runtime provisioning was not run.

The broader parallel Python regression was not completed: an initial run showed failures whose causes remain unverified and was stopped for diagnosis; a fail-fast rerun stopped during collection because the optional self-host sandbox example requires the unavailable `anthropic` package. This does not change the passing managed-creation result.

After rebasing onto `17f392f7` on 2026-09-23, the final working-tree diff passed 371 managed-creation tests, 1,305 Node tests, 36 Vitest tests, the production frontend build, packaged-asset validation, pre-commit Ruff/format/secret checks and `git diff --check`. The default two-worker Python regression stopped during collection because the optional self-host sandbox example imports the unavailable `anthropic` package. Pyright was not run in this check because the command is not installed in the current environment; an earlier run before the rebase passed.
