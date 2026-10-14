# Confirm MPA deletion after a client timeout

[中文版](2026-10-13-confirm-delete-outcome.zh.md)

- Change ID: `mpa-delete-timeout`
- Created/revised: 2026-10-13
- Status: implemented
- Contract: [Studio MPA control plane](../../../specs/studio-mpa-control-plane/README.md), CON-30a

## Evidence, goals and scope

MPA deletion uses `deleteRuntime` with the ordinary 30-second `apiFetch` deadline. The server rechecks sessions and resource references and deletes exclusive templates/Skill Spaces before Runtime. A browser timeout does not cancel these backend side effects. A reported timeout was followed by confirmed Runtime NotFound and absence of its Skill Space; the template was not independently queried. The exact stage/duration was not recovered from logs.

FR-1: Give only explicitly selected MPA deletion a 180-second request deadline. General-agent deletion retains its 30-second deadline and behavior.
FR-2: After a TimeoutError, issue one read-only, uncached 30-second confirmation of the same Runtime ID/region through an Agent-management-authorized BFF. Report success only for explicit cloud Runtime NotFound plus complete ListRuntimes absence. Do not equate an authorization 404, access denial, transport error, malformed response, repeated token or pagination budget exhaustion with deletion. A Runtime visible only through ListRuntimes is still present.
FR-3: If confirmation returns present or cannot confirm, keep a localized uncertain-result message and the existing error/retry UI. Never automatically repeat DELETE. Non-timeout deletion failures preserve their current error.

No creation changes, shared timeout changes, new async-job system, deletion-order changes, Profile query, resource purchase, migration, image changes or general-agent behavior changes are included. Runtime absence confirms the selected Runtime outcome, not independently inspected resource cleanup by an external actor.

## Design and affected files

Add a small read-only backend helper and endpoint `/web/mpa-runtime-deletion-status?runtimeId=...&region=...` returning `{deleted: boolean}` with `Cache-Control: no-store`. Require current Agent management rights. Existing authorization verifies a present Runtime; authorization-generated HTTP errors never reach the missing-resource branch. If GetRuntime reports a structured Runtime-specific NotFound, scan all pages under the same deployment credentials, provider and region, with bounded pagination. Do not return resource/environment data or raw exceptions. Endpoint timeouts and unconfirmed errors return a safe explicit error. Cloud GetRuntime hiding a still-listed Runtime must not produce success.

The client uses the existing requestSignal/apiFetch and existing confirmation UI. MPA-only catch handles TimeoutError, verifies the boolean result and resolves the original delete promise only on true. False/failed queries produce localized guidance to refresh/check later. Tests use fake deadlines and cloud responses, not live deletion.

Files: `frontend/src/adk/client.ts`, paired ADK locale resources, `frontend/server/mpa_deletion_status.py`, route mount in `veadk/cli/cli_frontend.py`, frontend executable client tests, backend route/ownership/pagination tests; paired PRD/spec, frontend README and generated WebUI assets. No layout/CSS/icon changes; existing confirmation loading/error/retry/keyboard behavior is the visual baseline.

## Tasks and acceptance

- T-1 / FR-1 / AC-1: regression first for MPA 180 seconds versus general 30 seconds; general requests never call confirmation.
- T-2 / FR-2 / AC-2: implement authorized bounded status, cover structured/wrapped NotFound, paginated absence/presence, query failure, invalid pagination, cancellation and no mutation.
- T-3 / FR-3 / AC-3: verify confirmed completion, uncertain/present outcomes, malformed payload, permission and non-timeout failures; complete existing deletion/UI regression, build and isolated browser checks.

## Review, authorization, risks and verification

The user approved the proposed MPA-only timeout/confirmation fix with “改下” on 2026-10-13. `review-spec` is unavailable; direct review confirmed bilingual equivalence, no general-agent or cleanup-order change, bounded reads and fail-closed errors. No review blocker remains. Security review adds a bounded private confirmation context: remember only server-authorized MPA delete attempts, keyed by Studio owner/Runtime/region, with a hash of the current deployment credentials. At most 1024 contexts live for one hour; neither credentials nor their hash reach clients. Missing context, server restart or credential rotation produces an unconfirmed result, never success. Recheck credentials after cloud reads to detect mid-query account changes. This is not a persistent deletion job or new mutation protocol. No real cloud deletion, commit, push, deployment or Studio restart is authorized.

Cloud listing is eventually consistent and cannot guarantee transaction-like cross-service cleanup. The read-only confirmation cannot infer details of resources deleted by external operators. Account changes/authorization failure cannot silently produce success. Known old-file static errors must be baseline-compared rather than hidden. Actual results are recorded below. Required gates: affected Python tests, Ruff/Pyright changed files, `npm --prefix frontend test`, build/i18n/assets, isolated browser and configured secret scan. No harness/process contract is affected.

## Delivery review and verification (2026-10-13)

T-1–T-3 / AC-1–AC-3 are implemented. Review confirmed MPA-only client gating, unchanged generic POST/deadline, no delete replay, structured-only absence checks, complete bounded pagination, credential/owner scoping and retained partial-cleanup behavior. Standard-library timeout is used on Python >=3.11 and the existing async-timeout dependency on older supported Python; no dependency was added. No creation, Profile, Runtime image, schema or deletion-order change was made. The new server module is included by the existing `frontend*` package discovery.

Tested scope: this deletion fix on `71175c68636dc5b951e9804eb292d85402511e68`, alongside pre-existing local PG/name/OV changes which were preserved. Initial executable frontend regressions failed before the fix; backend tests initially failed collection because the new status module did not exist. Fake cloud operations and isolated browser responses are separate from live verification.

| Check | Result | Evidence / limitations |
| --- | --- | --- |
| Python deletion/role regression | pass | `uv run --extra dev pytest tests/frontend/server/test_mpa_deletion_status.py tests/integrations/mpa_managed/test_deletion.py tests/cli/test_studio_rbac.py -q --no-cov`: 210 passed before final additional negative cases. |
| Final confirmation unit/route tests | pass | `uv run --extra dev pytest tests/frontend/server/test_mpa_deletion_status.py -q --no-cov`: 25 passed, including real Studio route mounting with simulated cloud deletion, actual-category general isolation, timeout, expiry/count bounds and wrapped provider errors. |
| Frontend client regressions | pass | `node --test frontend/tests/mpaDeletionTimeout.test.mjs`: 10 passed, including confirmation transport timeout and preserving non-timeout server diagnostics. |
| Frontend full regression | pass | `npm --prefix frontend test`: 1389 Node +84 React passed, including all 10 new client regression cases. |
| Build/i18n/assets | pass | `npm --prefix frontend run build`, `npm --prefix frontend run check:i18n`, `npm --prefix frontend run test:webui-assets`: synchronized release assets, 2 locales /21 namespaces, 113 files /350 references. Existing chunk-size warnings remain. |
| Browser | pass | Bundled Playwright with isolated headless Chrome and actual AgentWorkspace/client: normal success, timeout confirmed, still present, query failure, busy-disabled state, keyboard Enter/Escape, cancel/reopen, general deletion and 390×844 view. Mock fetch blocked real cloud calls; temporary server/fixtures removed. |
| Ruff / new-module Pyright | pass | Temporary `uvx` tools; Ruff on all 3 changed Python files and Pyright with `.venv/bin/python` on new module/test. No machine-global installation. |
| Legacy CLI Pyright | fail | 37 existing errors; comparison against HEAD has exactly the same diagnostic messages/rules, with no new diagnostics from the fix. Unrelated historical errors were not changed. |
| Documentation / whitespace / secrets | pass | Paired-language/identifier/link review, `git diff --check`, repository-configured redacted Gitleaks on changed sources/assets. |
| Live destructive E2E | not_run | No new deletion authorized or executed; earlier read-only diagnosis is not a live test of this fix. |
| Broad SDK/process/harness tests | not_applicable | No SDK, process or harness contracts changed; focused deletion, RBAC and frontend regression cover the changed path. |
| Commit/pre-commit | not_run | No commit authorized; branch synchronization and full pre-commit remain required before any later commit. |

Restart Studio in the original credential-bearing terminal and refresh the page to load the backend and matching assets. No server restart, commit, push or deployment was performed. Remaining limits: contexts are process-local and expire; restart, a different worker process or credential rotation leaves the outcome unconfirmed. Runtime absence does not independently prove externally triggered related-resource cleanup. No new review blockers remain in the scoped fix.
