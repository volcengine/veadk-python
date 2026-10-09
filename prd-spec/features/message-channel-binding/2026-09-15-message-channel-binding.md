# DingTalk and WeCom binding

[中文版](2026-09-15-message-channel-binding.zh.md)

Change ID: message-channel-binding. Date: 2026-09-15. Status: approved.
Contract: [MPA channels](../../../specs/mpa-channels/README.md).

## Evidence and scope
Studio currently renders unavailable placeholders for DingTalk and WeCom. MPA already has DingTalk authorization and WeCom Bot ID/Secret Gateway registration, but the durable Studio binding API only supports Feishu. The user explicitly approved enabling both providers and testing them. This change connects these existing capabilities across both repositories. SDK execution, deployment and changes to provider infrastructure are outside scope.

## Requirements and scenarios
- FR-1: Selecting DingTalk offers QR authorization. Authorization completion registers the Gateway bot server-side; only successful persistence produces BOUND. Restart, expiry, owner isolation and uncertain registration preserve the existing Feishu guarantees.
- FR-2: Selecting WeCom offers a Bot ID and password-type Secret form. Credentials are sent to an authenticated server endpoint, never persisted in browser storage or returned in responses. Successful binding clears the form; errors remain visible.
- FR-3: All providers support diagnostics and unbinding. Group allowlists and group permission configuration apply only to Feishu; DingTalk and WeCom group messages do not require a local allowlist. Switching providers aborts pending requests and isolates resume IDs and UI state. Unsupported Runtime versions show an upgrade message.
- FR-4: Repeated identical registration reuses the existing bot. Ambiguous remote registration is reported without automatic retry. Diagnostics must not report another provider's delivery as this provider's success.

## Design and boundaries
Reuse the existing Studio channel component with a provider parameter. Keep Feishu API compatibility, add DingTalk durable bindings and WeCom credential binding, advertise supported providers via capabilities. Runtime remains credential owner and authenticates every new endpoint through require_channel_admin. DingTalk polling is request driven with encrypted database state and fenced leases; legacy background pollers are disabled for this path. WeCom uses the existing serialized upsert and encrypted channel store. No secret values appear in API error details. Live provider tests require an isolated Runtime and accounts; local tests mock all external services.

## Tasks, affected files and acceptance
| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1 | T-1: MPA studio.py, channels.py and tests | AC-1: QR, completed binding, expiry, ownership and no credentials returned | MPA targeted pytest |
| FR-2 | T-2: MPA credential endpoint and config.py | AC-2: WeCom registers, rejects blanks, hides errors and secrets | MPA targeted pytest |
| FR-3 | T-3: RuntimeChannels.tsx, client.ts, locales, CSS, tests | AC-3: both tabs usable; cancellation, forms and permissions scoped | Vitest, npm test, build, real browser |
| FR-4 | T-4: config and observations | AC-4: idempotence and channel isolation | targeted pytest |

## Review and risks
Direct design review performed because review-spec is unavailable: responsibilities, compatibility, authentication, encrypted storage, cancellation, failure semantics and paired-language equivalence reviewed; no unresolved design blocker. User approval: “帮我改，钉钉和企微的都要开启可以绑定”. External MPA repository edits require filesystem escalation. Existing unrelated changes are preserved. Runtime must be updated together with Studio; no deployment is authorized. Live testing is pending target configuration, so local evidence cannot establish real message delivery.

## Verification record
Initial review: implementation pending at approval; final results below. Required gates: targeted MPA pytest, Ruff/Pyright changed Python, frontend Vitest and npm test, npm build, webui asset checks, browser flow and error/cancellation/keyboard/narrow checks. Live smoke: blocked (Runtime and test accounts not provided).

Scope amendment approved 2026-09-15: user clarified “群聊限制只针对飞书”. FR-3/AC-3 now require hiding group permission forms and skipping permission reads for DingTalk/WeCom. Runtime admission checks enforce the allowlist only for Feishu. Existing group session isolation remains unchanged. Direct design review: no other auth or bot-binding checks change; add positive non-Feishu and negative Feishu regression tests.

## Implementation and verification update
2026-09-15, both repositories' current uncommitted channel diff. FR-1 through FR-4 implemented, including the Feishu-only amendment. Local acceptance AC-1 through AC-4 verified. No commit, deployment or live message was made. Implementation scope is complete locally; live verification and existing repository static-analysis debt remain visible below.

- pass: test-first evidence: original new UI tests failed 3 cases, original backend tests failed 3 cases; Feishu-only amendment failed 2 UI and 2 backend cases before implementation.
- pass: MPA channel regression 96 tests; after test typing cleanup, the 9 new backend cases passed again. Includes binding/ownership/persistence, credential validation and encryption, auth, remote error redaction, duplicate registration, bot-isolated observations, Feishu allowlist rejection and non-Feishu bypass.
- pass: frontend regression 1206 tests; channel component 14 tests (single worker), including both binding methods, old Runtime capabilities, unbinding, cancellation, provider isolation, IME and Feishu-only group controls.
- pass: production build (TypeScript and both Vite outputs); packaged assets verified: 104 files, 248 references. Only existing chunk-size warnings.
- pass: browser checks on real component with local simulated fetch: DingTalk pending to BOUND, WeCom credential to bound, Feishu-only group section, error/retry, loading/switching, keyboard and 480×850 layout. Temporary preview files/server/tab removed and viewport reset. Browser unbind click timed out in the dialog automation; both provider unbind paths are covered by component and backend tests, not claimed as browser-verified.
- pass: Ruff on studio.py, delivery.py, channel_control.py and new tests; Pyright on those files (including new tests), zero diagnostics.
- fail (existing findings): broader changed Python files retain Ruff 27 findings (channels.py 17, config.py 2, messages.py 8), with no added diagnostics compared to HEAD. Broader Pyright reports existing mixin/import/type issues in channels.py/config.py/messages.py; the newly introduced override mismatch was fixed. No unrelated source cleanup performed.
- pass: scoped whitespace checks, locale-key parity and paired documentation/relative links checked. No real credentials used; test secrets are explicit placeholders.
- not_run: full VeADK Python regression (no VeADK Python runtime changed); pre-commit/gitleaks (no commit requested; gitleaks executable unavailable). This is not represented as a passing secret-scan gate.
- blocked: real Runtime/provider smoke needs Runtime ID, region and isolated test accounts. Updating local Studio assets does not update a deployed MPA image. Operators must upgrade both sides and retain CHANNEL_STATE_ENCRYPTION_KEY before real binding.

The MPA repository uses a dev dependency group rather than VeADK's `--extra dev`; the existing local interpreter was used to avoid changing either dependency lock or contacting external services.

```bash
# MPA: repository-local interpreter; isolated from developer .env and external services
cd /tmp
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/bytedance/Desktop/code/agentkit-mpa-agent /Users/bytedance/Desktop/code/agentkit-mpa-agent/.venv/bin/python -m pytest /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_multi_channel_binding.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channel_studio.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channel_binding_edges.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channel_control_store.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channel_service.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channels_auth.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channel_message_edges.py -p no:cacheprovider -o addopts= -q
# VeADK working directory
npm --prefix frontend test
(cd frontend && ./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx --maxWorkers 1)
npm --prefix frontend run build
npm --prefix frontend run test:webui-assets
```
