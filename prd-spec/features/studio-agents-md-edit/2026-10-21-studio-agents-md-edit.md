# Studio AGENTS.md editing and application

[中文](2026-10-21-studio-agents-md-edit.zh.md)

change-id: `studio-agents-md-edit`

## Background and authorization
On 2026-10-21 the user explicitly requested implementation in Runtime and Studio, matching ArkClaw editing behavior, excluding caching and Bot Profile changes. This authorizes scoped additive APIs and implementation, not commits, releases or cloud changes. ArkClaw ModifyAgentConfig edits a debug Runtime and publishes separately. Studio edits the selected Runtime; this change does not introduce dual environments. Old ADK injected agentsMd; reused Worker sessions update it by fingerprint.

## Goals and non-goals
REQ-1: Studio administrators edit, save and clear AGENTS.md in the information rail, with persisted readback. Members retain read access. Preserve unrelated Agent settings.
REQ-2: Ordinary sessions use the latest content on the next turn; an active turn uses one snapshot for Main and Worker. Existing sessions need no recreation. Retain Worker profile fingerprint updates.
REQ-3: Detect concurrent saves and report errors honestly. Older Runtimes remain read-only. No cache, migration, dependency, Bot Profile, MA remote-host instruction, tool permission or model configuration changes.

## Design and boundaries
Add GET/POST /api/v1/studio/agents-md: GET returns content:string and revision:int (0 when unconfigured). POST requires content (empty allowed, at most 40000 characters) and revision; reject extra fields. Runtime verifies X-MPA-Studio-Key against its current key. The Studio proxy injects the server-owned key only for administrators; browser headers cannot impersonate it. Preserve the existing read-only information route.
Reuse mpa_agents revisions and existing row-lock/CAS primitives. Bootstrap with current MPA_AGENT_ID when absent; concurrent initialization returns409. Preserve model/Skill/MCP settings. Empty content removes custom instructions.
At turn entry in the ordinary Codex Worker architecture, read current configuration and freeze an AGENTS.md-only trusted RuntimeEnvelope snapshot. Inject into the active base instructions on thread start/resume: native Codex 0.155.1 does not propagate changed resume developerInstructions into the next model request. Carry through authorized MCP context and override the same Worker profile field, avoiding mid-turn drift. Carry no credentials and add no grant. Existing Bot snapshots remain unchanged; MA remote-host stays out of scope.

## Component impact
Runtime metadata API, AgentConfigService, Main envelope/runner/controller, trusted MCP context and Worker profile loading. Studio runtime proxy authorization, client, MPA rail, ModalLayout/Button/Textarea and localized copy.

## Spec review
review-spec checks cover empty clearing, older Runtime404/405, missing-record bootstrap, concurrent409, running turns, reused threads, identity isolation, late responses/cancellation and40k limit. Reuse storage/security without a registry/cache/new identity system. Platform rules outrank custom content. frontend-design/ui-ux-pro-max skills were not found locally; UI follows existing components and frontend/SPEC.md.

## Tasks and test plan
1. Design/contracts;2. API/persistence/turn regression RED;3. Runtime implementation;4. Studio implementation/tests;5. required gates/browser;6. separate implementation, verification and publication status.
Cover read/save/clear/bootstrap/replay/conflict/auth/size; Main/Worker snapshot and next-turn updates; UI loading/failure draft retention/retry/cancel/clear confirmation/keyboardIME/narrow viewport/target switch. Runtime make test/lint/mcp-tool-gate and governance; Studio targeted Python and proxy regression, Ruff/Pyright, npm test/build and browser checks.

## Risks and acceptance
Do not claim old control-plane publishing topology is replicated. Verify configuration delivery, not deterministic model obedience. Record live model/cloud checks separately; no deployment claim. Existing content over40000 characters is not silently truncated on save. Work follows task dependencies; reserve verification effort for cross-repository compatibility and real environments.

## Verification
Implemented. Targeted tests, real PostgreSQL CAS, native Codex update/clear, full Studio frontend tests/build and browser checks passed. Final full Runtime run: 10397 passed, 306 skipped, 1 failed. The sole failure is a scheduled Worker case reproduced on the pre-change HEAD; the full gate is not passed. Not released. Prior model-switch messages may retain old text as history, while current instructions explicitly replace the old configuration. See the paired Runtime report at docs/verification/studio-agents-md-edit/test-verification-report.md.

## Delivery clarification (2026-10-21)

The user authorized committing the local Studio changes and opening a PR to official main. Later Runtime native-protocol evidence supersedes the earlier claim that REQ-2 is fully verified: updating the Worker file does not reload instructions in an already reused native Worker thread. Main next-turn updates and persistence are verified; Worker hot reload remains deferred, including clearing. This PR delivers the Studio editor/proxy and requires the matching Runtime API; it does not fix or claim Worker hot reload. The separate Runtime full-suite baseline failure remains unresolved. No real cloud or model validation is claimed by this publication.

## Studio pre-commit verification (2026-10-21)

Scope: Studio editor/proxy changes after rebasing onto official `main` at `5e5deb6a`; the existing collaborator/creation-diagnostic commit was replayed without conflicts. No companion Runtime code is included in this repository commit.

- pass: `uv run --extra dev pytest tests/test_mpa_agents_md_proxy_policy.py tests/test_mpa_collaborator_proxy_policy.py tests/cli/test_frontend_runtime_proxy.py tests/integrations/mpa_managed -q`: 1,313 passed, 6 warnings.
- pass: `npm --prefix frontend test`: 1,389 Node tests and 154 Vitest tests.
- pass: `npm --prefix frontend run build`, `npm --prefix frontend run check:i18n`, and `npm --prefix frontend run test:webui-assets` (113 packaged files, 351 references). Existing bundle-size warnings remain.
- pass: `uv run --extra dev pre-commit run --all-files` after accepting Ruff formatting; includes hardcoded-secret scanning and dependency policy.
- fail (baseline unchanged): changed-file Pyright using the repository Python environment reports 57 diagnostics: 37 in cli_frontend.py and 20 in test_frontend_runtime_proxy.py. A comparison against the rebased HEAD has identical severity/message/rule counts; the two new Python files have no diagnostics. No global clean type-check claim.
- pass: paired-language local links and diff whitespace checks.
- not_run: new cloud/model operations and repeat browser acceptance during publication; prior isolated browser verification remains recorded above. No deployment is performed.

- fail: default parallel regression `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`: 7,572 passed, 53 skipped, 4 xfailed, 1 failed (483.08 seconds). The failure is `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`: `.md` MIME resolves to `application/octet-stream` instead of `text/markdown`. The same test fails in an isolated rerun (0.52 seconds); both the test and writer implementation are unchanged from official main. This unrelated failure is retained, not bypassed or silently fixed. Open the PR as a draft with this gate failure disclosed.
