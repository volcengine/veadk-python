# Named Studio MPA creation

[中文版](2026-10-09-named-studio-creation.zh.md)

- Change ID: `named-studio-creation`
- Created/revised: 2026-10-09
- Status: approved; approved by the user on 2026-10-09; implemented; local verification and deployment tracked below.
- Contracts: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), especially CON-1, CON-3, CON-5, CON-6, CON-9 and the HTTP body.

## Background and scope

The Studio dialog currently generates and displays an agent ID and submits editable Runtime/Worker image fields. `frontend/server/mpa_creation.py` requires that ID. The managed runner forwards it to provisioning, where `runtime.py` uses it as the new Runtime Name. The built-in `studio_profile.py` still points at older images.

The requested change replaces these technical inputs with a required Name field, generates the stable agent ID on the server, and creates new agents with the published `mpa/mpa_agent:latest` and `mpa/mpa_codex_worker:latest` images in registry `agentkit-platform-2112682748-cn-beijing.cr.volces.com`.

Existing agents, database identities and CLI configuration are outside this change. Updating the user-specified cloud Studio is authorized as a separate delivery step. Preserve the existing dialog layout, components and other resource steps. No new dependency, cloud operation, account permission or data migration is required to implement this change.

## Requirements and scenarios

- FR-1: Basics contains editable Name and Description, with neither agent ID nor image inputs. Name follows the existing Studio Runtime-name validator: 4–64 ASCII letters, digits, underscores or hyphens; surrounding whitespace is trimmed. Invalid names block forward navigation and submission and are rejected by the server before provisioning.
- FR-2: A fresh browser request contains `name` and `requestId`, without `agentId`, `runtimeImage` or `workerImage`. The server derives a stable `mi-` plus 24 hexadecimal-character ID from trusted owner and request UUID and persists it with the creation task. Different owners or requests have distinct identities; lost responses, duplicate submits, cancellation and retries retain the same identity.
- FR-3: The Name flows through task persistence and the fixed child-process protocol into the new Runtime's `Name`. `MPA_AGENT_ID`, worker bindings, registry keys and other resource identities continue using the generated ID. Existing registered Runtime names are preserved.
- FR-4: New Studio requests use the two server-owned `latest` image defaults. Browser draft restoration must not silently replay old image overrides on a fresh request. Existing submitted drafts/tasks retain their original payload and image selections for safe retry.
- FR-5: Preserve the existing API's legacy `agentId` and image fields for older clients/submitted drafts. Legacy requests without a Name retain the previous Runtime naming behavior. CLI/YAML image overrides remain available. Do not weaken ownership checks or pending-request mismatch detection.
- FR-6: Preserve cancellation, polling, retry, input locking, secret exclusion, localized text and keyboard/IME behavior. The New Agent action creates a fresh name draft and request UUID. No production secrets appear in tests or artifacts.

Given a valid new form, submitting it creates one task whose Runtime Name is the entered name and whose generated ID is injected into both Agent and Worker. Given a lost POST response, retrying the same request does not create another identity. Given an old submitted draft, reopening and retrying it preserves the original operation. Given an invalid name, no cloud write starts.

## Design and affected files

1. Update `frontend/src/adk/mpaCreation.ts`, `frontend/src/ui/mpa-create/MpaCreateDialog.tsx` and localized strings. Reuse `frontend/src/create/runtimeName.ts`; retain the existing ModalLayout, Button and Textarea. New submissions explicitly omit removed fields, while restoring already-submitted legacy drafts preserves their request shape.
2. Extend `frontend/server/mpa_creation.py` with a validated Name and server-generated stable ID for the new request shape. Omit absent optional legacy fields rather than changing old persisted payload equality.
3. Carry the optional Runtime name through `managed/tasks.py`, `runner.py`, `service.py` and `runtime.py`. Name must participate in persisted request equality and pending Runtime request hashes. Preserve the existing name when reconciling an existing Runtime.
4. Update only the built-in Studio image defaults in `managed/studio_profile.py` to the published `/mpa/` images. Keep the shared CLI image-selection mechanisms.
5. Amend both component-spec languages, managed operator docs, frontend documentation and built web assets. The HTTP extension is backward compatible; no database schema change is needed.

The alternative of using Name as agent ID is rejected: users' display names must not become ownership/database keys. Generating a new random ID on each retry is rejected because it breaks idempotency. Deterministic owner/request generation uses trusted server ownership, not a browser-supplied owner.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1, FR-6 | T-1: add regression tests before UI changes | AC-1: Name required; removed inputs absent; loading/error/IME/keyboard states usable | frontend MPA dialog tests and real browser against isolated fake APIs |
| FR-2, FR-5 | T-2: extend request handling and recovery | AC-2: stable owner/request identity; legacy retry unchanged; changed input conflicts | route/task tests in `tests/integrations/mpa_managed/` |
| FR-3 | T-3: propagate Runtime name | AC-3: create payload uses Name while all identity bindings use generated ID; existing Runtime names retained | runner/service/runtime tests |
| FR-4 | T-4: update built-in defaults | AC-4: both selected images end in `/mpa/<repository>:latest`; submitted tasks preserve selections | profile/image/route tests |
| All | T-5: reconcile docs and artifacts | AC-5: bilingual contracts align; assets match source; no credentials | test/build/i18n/assets, Ruff/Pyright, pre-commit and diff review |

Commands: `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py`; `npm --prefix frontend test`; `npm --prefix frontend run build`; `npm --prefix frontend run check:i18n`; `npm --prefix frontend run test:webui-assets`; changed-file Ruff/Pyright; `uv run --extra dev pre-commit run --all-files`. Verify meaningful new executable lines exceed 95% incremental coverage. Broader regressions follow repository gates. Live cloud provisioning is not authorized by this code-change request and is reported separately from simulated checks.

## Risks, review and delivery record

- `latest` is mutable. Updating the registry tag affects later pulls, not existing running agents. A new creation can use a newer image than a prior creation; no automatic update of existing resources is introduced.
- Unsubmitted legacy drafts must be migrated without restoring hidden overrides. Submitted draft compatibility and duplicate-owner/request behavior need explicit tests.
- 2026-10-09 source review: confirmed UI ID generation, route requirement, persisted exact payload matching, fixed child protocol and Runtime Name override. Design approved before implementation; current verification is recorded below.
- `review-spec` is unavailable; perform the same contract/security/compatibility/testability/bilingual review directly. The repository's referenced UI skill paths are absent; available frontend-design guidance and Studio's own component/interaction rules govern this scoped form change.
- User requested implementation and the established fork/PR workflow. The user approved implementation, updating the supplied Studio deployment, and adding this change to PR #21 on the existing branch.


## Verification and release evidence (2026-10-09)

Scope: the named-creation changes on `czh/fix-mpa-tos-copy`, based on `origin/main` `ef0ad51`; delivered with the existing TOS copy change in PR #21. No dependency or schema migration was introduced.

- `pass`: targeted Python regression, 481 tests (`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -o addopts='' --cov=veadk.integrations.mpa.managed --cov=frontend.server.mpa_creation`). The coverage run must omit the repository's Pydantic warning-filter preload: with that filter pytest-cov produces duplicate Pydantic classes during collection; without coverage the standard MPA tests passed (457 tests before the last two cases). No tests were excluded to collect coverage.
- `pass`: `npm --prefix frontend test` — 1,377 Node tests and 52 component tests, including 35 creation-dialog cases. Cases cover required/invalid/trimmed names, removed fields, draft migration, legacy retries, late responses, cancellation and composition input.
- `pass`: changed executable-line coverage is 75/75 (100%): Python 27/27 and dialog 48/48. Type-only and non-executable call-argument lines are not separate coverage statements. Runner/child-protocol and Runtime identity assertions independently cover name propagation.
- `pass`: `npm --prefix frontend run build`, `check:i18n` (2 locales, 21 namespaces) and `test:webui-assets` (113 files, 350 internal references).
- `pass`: Ruff and Pyright for changed production Python files and the new regression test; pre-commit Ruff/format and secret scans. Additional Pyright on existing modified tests retains two pre-existing errors in `test_service.py` (confirmed against the pre-change file); none were introduced here.
- `pass`: local browser with isolated fake API responses — empty/invalid names block progress, valid name and description render without ID/image inputs, Tab and Enter navigation work, all three steps render, simulated 503 shows an error and locks submitted fields. At 390×844 the dialog remains usable without horizontal overflow. The captured POST contains Name/requestId and no Agent ID/image override. Composition input and retry/cancellation are additionally covered by automated tests; an OS IME session and real cloud creation were not run.
- `fail` (baseline/environment): full default Python regression excluding opt-in Codex/Pi smoke: 6,239 passed, 19 skipped, 2 xfailed, 7 failed, 2 collection errors. All seven failures and both errors reproduce on pre-change commit `ae39492`: six Harness cases need the optional `llama_index` dependency, two Sandbox modules need `anthropic`, and the artifact writer MIME assertion returns `application/octet-stream` instead of `text/markdown` on this host. The unchanged baseline subset had 108 passes and the same failures/errors. No unrelated dependency or MIME behavior was changed.
- `pass`: the authorized existing Studio code update was released as stable revision 37 (previously 36). The homepage returned HTTP 200 and references `/assets/app/index-BGwZgNyo.js`; that online file returned HTTP 200 and its SHA256 exactly matches the verified local build. All 44 existing environment values have the same aggregate hash before/after the release. The packaged changed backend files also matched local source byte-for-byte. VeADK wheel SHA256: `f1413695218969f8a34765cc1f7392ae44ffea9971ddba96c5c84ce03f12ada3`. No new MPA Runtime was created by this release. Credentials were kept outside the repository/package and removed after deployment verification.
- `not_run`: real cloud MPA provisioning and message delivery. Local tests/build/browser proof do not establish cloud adoption or Agent/Worker execution.

Direct design/implementation review checked bilingual equivalence, owner-scoped deterministic identity, legacy request equality, hidden draft overrides, name propagation and existing-resource preservation. These local checks found no unresolved issue in the changed behavior. `latest` remains mutable; retry snapshots retain tag references, not immutable digests.


## Validation feedback follow-up (2026-10-09)

The user reported that Next looked active but did nothing for a Chinese Runtime name, and approved a frontend correction. The existing ASCII name contract remains unchanged. The shared Button primitive lacks a base disabled appearance; add its existing 0.45 opacity/not-allowed cursor treatment to all variants, retaining loading overrides. The MPA form uses the existing danger token for the invalid name border/focus and error text, and adds a localized valid-name placeholder. No API, identity, image or resource behavior changes. Review confirmed component ownership, keyboard/native disabled semantics, theme-token reuse and bilingual equivalence. Verify a failing computed-style regression first, then valid/invalid names, all Button variants/loading, build and browser checks before updating the same Studio and PR.

Follow-up local verification: `pass`. The regression reproduced the enabled-looking disabled Next button and passed after the CSS fix. All 1,377 Node tests and 54 component tests passed, including all six Button variants and loading opacity. The added JSX line is covered (1/1, 100%); CSS is checked through computed styles and browser rendering. Build, i18n, packaged-asset references, pre-commit and whitespace checks passed. Browser checks covered the Chinese-name report, danger border/text, disabled opacity/cursor, correction with Tab/Enter navigation, light/dark themes and 390px width. Backend code is unchanged; prior backend verification and baseline limitations still apply.

Follow-up deployment: `pass` — stable revision 38, homepage HTTP 200, app JS and stylesheet bytes matching the verified build, and all existing environment values unchanged. Wheel SHA256: `0ff26dd247e26fedd96faa21fd62b96f6b86904fd0168f535db39de2047186da`. Temporary deployment credentials were removed after verification. No cloud MPA creation was performed.
