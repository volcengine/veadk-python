# Channel authorization methods

[中文](2026-09-15-channel-auth-methods.zh.md)

Change ID: channel-auth-methods; date: 2026-09-15; status: implemented.

## Background and scope
The user explicitly requested the existing Dashboard WeCom SDK authorization flow in Studio and manual DingTalk Client ID / Client Secret binding. Studio currently supports only manual WeCom and QR DingTalk. Preserve both existing flows and Feishu. No gateway, identity, or network changes.

## Requirements and design
- FR-1: WeCom opens the official SDK 0.1.0 popup synchronously on a user click (`source=mpa-agent`, debug off), validates returned Bot ID/Secret and submits to authenticated `/wecom/bindings`. Never show or persist SDK credentials. Use one disposable SDK instance per attempt, cancel on navigation/user cancellation, ignore late results, bound waiting to five minutes, and show sanitized blocked/cancelled/timeout/malformed-result errors.
- FR-2: DingTalk retains QR authorization and adds masked Client ID / Client Secret manual submission to `/dingtalk/bindings/manual`. Runtime advertises `credentialBindingChannels`; old images show an upgrade hint for the new manual entry. Reject blanks, require admin, sanitize validation/provider failures, return 409 for ambiguous registration, and reuse existing encrypted Gateway registration logic.
- FR-3: Reuse current channel form/Button styles, Chinese/English localization, IME guards, duplicate-submit lock, disabled/loading/uncertain states. Clear secrets after success; do not overwrite another Runtime after navigation.

## Contract and tasks
Update CON-11 in [MPA channels](../../../specs/mpa-channels/README.md). T-1: failing frontend and backend contract tests. T-2: SDK adapter, UI, Runtime endpoint/capability, dependency/lock and translations. T-3: targeted tests, frontend test/build, browser checks and Runtime release. T-4: reconcile bilingual docs and verification record. No generated Agent code changes; built Studio assets must match source.

## Acceptance and verification
AC-1/FR-1: popup success submits exact normalized credentials once; cancellation/unmount/timeout/blocked popup/missing fields do not register. AC-2/FR-2: manual DingTalk posts correct payload, preserves QR, rejects unauthenticated/invalid requests, redacts secrets, handles uncertain registration. AC-3/FR-3: frontend tests/build and narrow/keyboard browser checks pass; deployed Runtime exposes manual endpoint and existing Feishu binding is retained. Tests use fake credentials; real user authorization and actual new-channel messaging require user interaction and are reported separately.

## Review and authorization
Scope is authorized by the user's explicit instruction to use the Dashboard implementation and add manual DingTalk binding. Reviewed directly (review-spec skill unavailable): requirements, API ownership, auth, error redaction, async lifetime, compatibility and paired language agree. No blocking design findings. Referenced frontend-design/ui-ux-pro-max skill files are absent locally; implementation follows frontend/SPEC.md and existing channel controls. SDK tarball is 15,336 bytes, zero runtime dependencies; pin 0.1.0. Source inspection confirms origin checking; do not claim state validation beyond implemented SDK behavior. Risks: browser popup blocking, provider availability, SDK compatibility, ambiguous Gateway outcome. Never automatically re-register an ambiguous bot.

## Delivery record
Checks: not_run before implementation. User-driven QR authorization and live provider messages: not_run without user action.

### Verification completed (2026-09-15)
- pass: backend channel tests, 74 cases including new manual authentication, validation, redaction and uncertain-outcome checks.
- pass: `vitest run tests/runtimeChannels.test.tsx`, 24 cases; `npm test`, 1206 cases; `npm run check:i18n`; `npm run build`; `npm run test:webui-assets` (104 files, 248 references).
- pass: isolated real-browser component checks for WeCom SDK waiting/cancellation, manual DingTalk failure/retry/success, keyboard provider switching and 390px viewport. Provider credentials in those checks were fake and never sent to cloud. Browser inspection caught the SDK browser UMD/default-export mismatch; explicit official ESM import and a type declaration fixed it.
- pass: scoped secret-pattern and whitespace checks. Ruff reports 17 pre-existing B008/RUF100 findings; the previous image produces the same findings. Pyright reports one pre-existing dynamic ChannelService import issue; reproduced against the previous image source. These full-file checks are `fail` on the baseline too, not claimed passing.
- pass: new image `studio-channels-20260915-v2` released to the existing Runtime, version 4 Ready. Network/env/auth unchanged; capabilities 1.2 advertises manual DingTalk. Both credential endpoints reject empty payloads with 422. Existing Feishu BOUND and existing DingTalk configuration retained; diagnostics include previous delivered observations.
- pass: local Studio restarted with its original working directory/arguments (without browser auto-open); served index and JS match the final build.
- not_run: new real WeCom authorization completion, new manual DingTalk credentials and subsequent real messages; these require user account interaction. The already bound DingTalk bot was not replaced.
