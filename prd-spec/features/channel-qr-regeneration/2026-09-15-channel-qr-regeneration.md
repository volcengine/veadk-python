# Regenerate channel pairing QR code

[中文](2026-09-15-channel-qr-regeneration.zh.md)

Date: 2026-09-15. Status: implemented. User approval: request to add “重新生成二维码” and “消息渠道扫码配对” with Feishu replacement guidance. Contract: [MPA channels](../../../specs/mpa-channels/README.md).

## Background and scope
RuntimeChannels currently disables QR generation when a bot is already configured. Existing MPA upsert registers and saves the replacement before removing the old bot. Preserve the latest WeCom SDK and DingTalk manual-binding changes. No backend/API, provider authorization, deployment or credential-storage changes.

## Requirements and design
FR-1: A configured Feishu or DingTalk bot exposes an enabled Regenerate QR code action. Loading, an active pairing, uncertain registration and unavailable configuration still disable it.
FR-2: Clicking opens the inline Message channel QR pairing panel with loading/status/QR. For Feishu, explain that a successful scan and binding replaces the connected bot and the authorization flow can bind an existing bot or create a new one. Selection occurs in the provider flow, not a new Studio credential form.
FR-3: Creating the QR performs POST to the existing binding endpoint without DELETE. Keep the current bot summary until BOUND refreshes diagnostics. Request failure and navigation cancellation do not unbind the current bot.

## Tasks and acceptance
T-1/AC-1: regression tests for configured regeneration, replacement explanation, duplicate prevention and failed request preserving the old connection (FR-1/2/3).
T-2/AC-2: update RuntimeChannels.tsx and both ui.json languages, preserve provider isolation and Feishu-only group controls.
T-3/AC-3: run component Vitest, frontend regression, production build, assets and browser checks; record limitations.

## Review and risk
Direct design review (review-spec unavailable): additive UI contract, unchanged authentication and persistence; provider selection UI belongs to authorization service. No unresolved blocker. User request authorizes this implementation. Live replacement is not tested without an isolated Runtime/account. Pending QR replacement remains disabled to avoid concurrent active pairing sessions.

## Verification
2026-09-15, current uncommitted frontend channel diff: pass. The three new regression cases failed before implementation and all 23 component tests passed afterward (`cd frontend && ./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx --maxWorkers 1`). `npm --prefix frontend test`: 1206 passed. `npm --prefix frontend run build`: pass (TypeScript and both Vite outputs; existing chunk-size warnings). `npm --prefix frontend run test:webui-assets`: 104 files and 248 references verified. Locale-key parity, paired identifiers/links and scoped diff whitespace: pass.

Browser verification: pass using the actual component with isolated simulated responses, covering configured regeneration, pairing explanation, pending/loading, error with retained connection, keyboard navigation/cancellation and 480×850 layout. Temporary preview files/server/tab were cleaned up and viewport restored. Actual provider QR content and existing/new bot selection remain owned by the authorization flow; live bot replacement: not_run (no isolated Runtime/account supplied). Python checks: not_applicable (no Python changes).

## WeCom amendment (2026-09-15)
The user identified the missing WeCom regeneration entry and approved completing it. FR-1/FR-2 and T-1/T-2 now also cover configured WeCom bots. Regenerate QR code opens the existing WeCom SDK authorization window synchronously in the click gesture, shows the shared pairing title and WeCom replacement guidance, and sends returned credentials to the existing `/wecom/bindings` endpoint. Cancellation/blocked popup/failure retain the current bot; success refreshes diagnostics. No new API, permissions or browser credential storage. Add regressions for configured reauthorization, cancellation and blocked-popup retry. Direct review: reuse existing SDK cleanup and cancellation; no design blocker. New verification pending.

WeCom amendment verification, 2026-09-15 current uncommitted diff: pass. The three new cases failed first; all 27 channel tests then passed with the same Vitest command. Frontend regression: 1206 passed. Production build and packaged-asset verification: pass (104 files, 248 references). Browser checks using the real component with simulated SDK/API: configured entry, successful replacement summary, pending/cancel preserving the old bot, blocked-popup error, keyboard navigation and 480×850 layout passed. No real WeCom window/account was authorized in these checks. Temporary preview files/server/tab removed and viewport restored. Paired docs, locale keys and whitespace: pass. No backend change; live authorization remains not_run.

## Button layout and wording amendment (2026-09-15)
User-approved presentation-only adjustment: configured WeCom places Regenerate QR code and Unbind in the same existing horizontal action row, matching Feishu/DingTalk; all three Chinese labels use `解除绑定` and English uses `Unbind`. Reuse the WeCom authorization controls for bound/unbound placement, retaining the unbound form order and all handlers, disabled conditions, confirmation, and cancellation. No component state/API/security contract impact and no new behavior tests required for this formatting/localization change. Direct review found no blockers.

Verification on the current uncommitted presentation diff: pass — existing channel Vitest 31 tests; frontend suite 1208 tests; production build; packaged assets 104 files/248 references; scoped whitespace. Actual component in browser with mocked APIs: all three providers share button baseline/height/gap; WeCom also remains horizontal at 480×850. No live binding was performed. Python checks not_applicable. Required design skills remain unavailable; existing channel styling was reused. Temporary preview files, tab and server were cleaned up.
