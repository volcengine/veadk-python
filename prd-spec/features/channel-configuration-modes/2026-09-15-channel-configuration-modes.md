# Channel configuration modes

[中文](2026-09-15-channel-configuration-modes.zh.md)

Change ID: channel-configuration-modes. Date: 2026-09-15. Status: implemented.
Contract: [MPA channels](../../../specs/mpa-channels/README.md), CON-15.
Predecessor: [authorization methods](../channel-auth-methods/2026-09-15-channel-auth-methods.md).

## Background and evidence

`frontend/src/ui/RuntimeChannels.tsx` presents QR authorization and manual credentials together for unconfigured WeCom/DingTalk channels, and no manual Feishu form. The user requests manual Feishu App ID binding and two exclusive methods named 极速配置 and 手动配置, defaulting to 极速配置. Local MPA source at `app/api/v1/channels.py` already exposes POST `/api/v1/channels/feishu/bindings/manual` and advertises Feishu in `credentialBindingChannels`; `app/services/channel/studio.py` owns credential registration. Availability in the deployed Runtime remains unverified.

## Goals and non-goals

Unify configuration method selection for all three providers and connect Feishu credentials to the existing Runtime API. Keep the current Runtime selection, diagnostics, unbinding, and Feishu group-permission ownership. No changes to the automation catalog, standalone Feishu Runtime creation wizard, cloud deployment, SDK dependencies, database schema, or external MPA source are planned.

## Requirements and design

- FR-1: Each provider displays mutually exclusive Quick setup / Manual setup options (Chinese: 极速配置 / 手动配置). Initial mount and provider/Runtime changes select Quick setup; selection is not persisted. Only the selected method's content is shown. Choosing Quick setup does not itself launch authorization.
- FR-2: Quick setup preserves the current Feishu/DingTalk QR and WeCom SDK authorization flow, including existing bot replacement guidance and QR regeneration. Manual setup requires Feishu App ID / App Secret, DingTalk Client ID / Client Secret, or WeCom Bot ID / Secret. Existing configured bots may be replaced through either method; retain the current binding until server-confirmed success and show replacement guidance.
- FR-3: Manual Feishu sends `{appId, appSecret}` to POST `/api/v1/channels/feishu/bindings/manual` through `channelRequest`; retain existing DingTalk and WeCom payloads/routes. Require Runtime capability before enabling new manual methods. Unsupported manual setup explains that an upgrade is required while Quick setup remains available when supported. Empty values cannot submit; secret inputs are masked and never persisted, logged, or shown in errors. Success clears credentials and refreshes diagnostics; recoverable failures preserve the active form.
- FR-4: Switching methods cancels QR polling and disposable SDK authorization, discards temporary pairing UI and credentials, and ignores late results. Do not permit switching while a registration mutation is in flight; retain the SDK cancel action. A 409 uncertain outcome blocks new registrations across both methods until reconciled. UI cancellation does not claim to revoke server-side binding. Existing navigation cleanup, bounded SDK timeout, IME guards and duplicate-submit protection remain enforced.
- FR-5: Reuse Studio controls/styles and add keyboard-accessible method selection, visible selection/focus, and narrow-window layout. Keep Chinese/English labels and documentation aligned. Update generated web assets after verification.

## Tasks and acceptance

| Requirement | Task | Acceptance |
| --- | --- | --- |
| FR-1, FR-2 | T-1: add failing cases in `frontend/tests/runtimeChannels.test.tsx` | AC-1: all providers default to Quick setup; Manual setup alone shows the appropriate form; configured replacement preserves the old binding on failure |
| FR-3 | T-2: wire Feishu fields and payload in `RuntimeChannels.tsx`, update capabilities mocks | AC-2: exact provider-specific request, capability gating, blank validation, masked secrets, sanitized errors, success clearing |
| FR-4 | T-3: implement method state and cleanup | AC-3: switching/navigation stop frontend work, late responses cannot update the current view, uncertain outcomes and duplicate/IME submissions remain guarded |
| FR-5 | T-4: update `RuntimeChannels.css`, both `ui.json` locales, `frontend/README.md`, specs and build artifacts | AC-4: bilingual labels, keyboard and narrow browser checks, source and generated assets agree |

## Verification

Run targeted tests first: `cd frontend && ./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx src/adk/channels.test.ts --environment jsdom --maxWorkers 1`. Then run `npm --prefix frontend test`, `npm --prefix frontend run check:i18n`, `npm --prefix frontend run build`, and `npm --prefix frontend run test:webui-assets`. Real-browser checks use simulated APIs and fake credentials for default/selection, all provider fields, configured replacement, loading/error/retry, cancellation, keyboard/IME and narrow layouts. Live provider authorization and messaging require separate authorization and an isolated target; they are not established by local tests. Before the already requested commit, rerun repository pre-commit and affected tests and record unresolved full-regression failures honestly.

## Review, risks and delivery record

Direct review performed because review-spec is unavailable: API ownership, payload, permissions, capability compatibility, secret lifecycle, asynchronous cleanup, replacement behavior, testability and bilingual equivalence reviewed. CON-15 records the changed contract. The user explicitly approved this proposal with “实施” on 2026-09-15. Implementation proceeds within the reviewed scope.

Risks: deployed Runtime may lack manual Feishu despite local support; cancelled browser work does not revoke server-side operations; ambiguous registration must not trigger automatic replacement retries. Configuration success is distinct from observed message delivery.

2026-09-15, this proposal only: runtime/browser checks `not_run` because implementation awaits approval. Earlier commit checks apply only to the prior diff: frontend 1208 passed, channel tests 32 passed with jsdom, targeted Python 15 passed, build passed, secret hook passed; Python full regression failed with 6 failures and 2 collection errors (4532 passed). Those failures still require investigation before the pending commit; no commit has been created.


## Implementation and verification (2026-09-15)

Scope: current channel changes based on `f1aa2d75` on `feat/my-feature`, including the previously pending MPA channel diff. T-1 through T-4 and AC-1 through AC-4 are complete locally. The frontend uses the existing Radio component and provider-specific Runtime routes; no MPA backend source or deployed Runtime was changed in this iteration. Existing Python changes received Ruff formatting only. Browser review also found and fixed Feishu group-form overflow at 390px using grid sizing and the Select component's public style prop.

- pass: test-first run produced 17 failures and 28 passes before implementation. Final `./frontend/node_modules/.bin/vitest run --root frontend tests/runtimeChannels.test.tsx src/adk/channels.test.ts --environment jsdom --maxWorkers 1`: 47 passed. Covers all providers, defaults, exclusive content, credentials, old capability responses, replacement failures, late QR/SDK responses, uncertain QR/manual registration, IME, duplicate requests and navigation.
- pass: `npm --prefix frontend test`: 1208 passed; `npm --prefix frontend run check:i18n`: 2 locales / 21 namespaces consistent; `npm --prefix frontend run build`: both outputs and TypeScript passed, existing bundle-size warnings only. Packaged asset verification is recorded below after the final build.
- pass: real browser with simulated Runtime API and SDK: all three manual binding paths, Feishu error/retry/success and secret clearing, WeCom authorization waiting/method cancellation, native radio keyboard navigation, default reset on provider selection, old-image manual upgrade with quick setup retained, and 390×844 layout. Feishu group inputs and Select no longer overflow; measured preview scroll width equals its client width (379px). Temporary preview files, server and tabs removed; viewport reset.
- pass: targeted Python command `uv run --extra dev pytest tests/test_mpa_channel_proxy_policy.py tests/integrations/test_mpa_provision_env.py -q`: 15 passed. Additional optional-dependency reproduction using sandbox extra and temporary `llama-index-core`, `llama-index-embeddings-openai-like`, `llama-index-llms-openai-like`: 73 passed for `tests/cloud/test_harness_app_contract.py`, `tests/runtime/test_self_host_sandbox_agent.py`, `tests/runtime/test_self_host_sandbox_client.py`.
- fail: full regression with the same temporary dependencies, `uv run --extra dev --extra sandbox --with llama-index-core --with llama-index-embeddings-openai-like --with llama-index-llms-openai-like pytest -n 2 -m "not codex_smoke and not piagent_smoke"`: 4546 passed, 3 failed, 7 skipped, 2 xfailed. Failures: `test_harness_app_exposes_agent_info`, `test_harness_session_create_accepts_id_and_get_agent_config`, `test_run_wraps_child_with_sidecar_environment` (model/port values differ). Their source/tests are unchanged. Repeating the two affected files in isolation passed all 26 tests; suite-order/environment interaction remains unresolved. Two workers were used to limit local resource use. Skips are not represented as verified behavior.
- fail (baseline): `uv run --extra dev --with pyright pyright veadk/cli/cli_frontend.py veadk/integrations/mpa/channel_proxy.py veadk/integrations/mpa/mpa_provision.py tests/test_mpa_channel_proxy_policy.py`: 33 diagnostics, all in cli_frontend.py. Running Pyright on the HEAD copy produces the identical 33 diagnostic messages. No new diagnostics in the channel/provisioning/test files; unrelated typing cleanup is outside scope.
- reviewed false positive: extra Gitleaks default-rule scan of changed files, including tests and generated assets, flags the minified editor expression the Lexical selection anchor/focus key comparison. The identical expression exists in the HEAD MarkdownPromptEditor asset; it is code, not credential material. No scanner configuration or hook was weakened. Required repository pre-commit results are recorded below.
- pass: paired language identifiers, relative links and scoped diff whitespace. Generated third-party JavaScript retains its existing whitespace conventions and is not hand-edited.
- not_run: live provider authorization, replacement and messaging; not authorized for this iteration. Local source support does not prove deployed Runtime capability. Harness/sidecar coverage gate is not_applicable to the configuration-mode change because sidecar contracts are unchanged.

Review: authentication remains in the existing BFF; passwords never enter browser persistence; method switches release owned resources and preserve uncertain outcomes; both design languages and CON-15 match the implementation. Prior user authorization to commit remains active. No push or deployment is authorized.

### Final commit checks (2026-09-15)

- pass: fetched origin and rebased onto `origin/feat/my-feature`; HEAD was already current and the content was preserved.
- pass: after synchronization, `uv run --extra dev pre-commit run --all-files` (Ruff check, Ruff format, Gitleaks), 15 targeted Python tests, 47 channel/client tests, locale parity, and packaged asset verification (104 files / 248 references).
- pass: all 20 changed PRD/spec files have language counterparts, matching requirement identifiers and valid relative links. Temporary debug files remain local and are excluded from the commit.
