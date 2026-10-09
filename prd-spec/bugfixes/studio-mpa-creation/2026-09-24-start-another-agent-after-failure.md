# Start another MPA agent after a failed creation

[中文版](2026-09-24-start-another-agent-after-failure.zh.md)

- Change ID: `studio-mpa-new-after-failure`
- Date: 2026-09-24
- Status: approved by the user's request to start a different agent after failure
- Component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md)

## Background and evidence

The creation dialog persists a submitted `requestId`, `agentId`, and `taskId` in `sessionStorage` and restores them on reopen. It clears that entry only after success. After a failed or cancelled task, closing and opening the create card therefore returns to the old task with only a retry action. The generated agent ID is read-only, so the user cannot begin a different agent in the UI.

## Goals, non-goals and scenarios

Offer an explicit way to start a different MPA agent after a **known terminal failure or cancellation**. Preserve same-ID retry and server-side task/resource records. Do not reset running tasks or an uncertain POST result, delete cloud resources, alter the task API, or persist OpenViking credentials.

- A failed or cancelled task shows both retry and a separate new-agent action.
- Choosing the new-agent action clears only the browser recovery entry, generates a fresh request ID and agent ID, resets the three-step form to basics, and restores server defaults for image and PG fields.
- Closing and reopening the new draft keeps the new identity; the old task is not submitted again.
- Running, cancelling and uncertain-submission states do not offer this action.

## Requirements and design

- **FR-1:** Show a localized new-agent action only for confirmed `failed` or `cancelled` task snapshots, alongside the existing retry path.
- **FR-2:** On selection, replace the old session entry and clear the in-memory task identity; generate a new UUID and `mi-` ID with the existing length and reset description, OpenViking inputs and wizard step. Prefill images and manual PG target from the current safe config.
- **FR-3:** Leave server tasks and registered cloud resources untouched. Keep pending/unknown responses on their original identity to preserve idempotent recovery. Never store the OpenViking API Key.

Affected files: creation dialog, localized UI text, dialog tests, Studio component contract, and frontend user documentation. No backend or cloud API change is required.

## Tasks, tests and risks

1. Add a failing dialog regression test for reopening a failed task and starting a different agent, including fresh IDs, cleared secret and persisted new draft. Cover cancellation and absence while running.
2. Implement the terminal-state action with existing buttons and form state; retain retry semantics.
3. Run focused frontend tests, the full frontend test/build/asset gates and a browser interaction check where available.

An accidental reset could abandon a recoverable task. Restrict the action to confirmed terminal states and keep the old server task and resources unchanged. Acceptance requires a user-visible new path, distinct request and agent IDs, no stale task status after reset, and unchanged same-ID retry.

## Review and verification

Design review: resetting only after a confirmed terminal task keeps the server's idempotency boundary intact. The explicit action makes abandoning the old recovery draft deliberate; no cleanup or deletion is implied. The existing session key and component buttons are reused. The English and Chinese contracts and instructions were checked for equivalent behavior.

Verification on 2026-09-24, working-tree diff on `feat/from-main-20260923`:

| Check | Result | Evidence |
| --- | --- | --- |
| Focused dialog regression | pass | `./node_modules/.bin/vitest run tests/mpaCreation.test.tsx`: 22 passed, including failed/cancelled task, fresh submission, secret reset, and running/uncertain guards. |
| Frontend tests | pass | `npm test`: 1305 Node tests and 39 Vitest tests passed. |
| Localization | pass | `npm run check:i18n`: two locales and 21 namespaces consistent. |
| Frontend build | pass | `npm run build`: both Vite bundles built; existing chunk-size and dynamic-import warnings remain. |
| Packaged assets | pass | `npm run test:webui-assets`: 104 files and 248 internal references verified. |
| Diff whitespace | pass | `git diff --check`. |
| Browser creation-dialog interaction | blocked | A local static server loaded the generated HTML/JS, but `/web/ui-config` and the login endpoints returned 404 without the Studio backend. No live cloud creation was attempted. |

The build refreshed hashed `veadk/webui` assets, including dependent Mermaid chunks. The asset check verifies that the updated references resolve. No backend, cloud resource or existing task was changed by the new action.
