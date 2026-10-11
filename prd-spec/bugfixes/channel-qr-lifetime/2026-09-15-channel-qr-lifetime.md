# Transient channel pairing QR

[中文](2026-09-15-channel-qr-lifetime.zh.md)

Date: 2026-09-15. Status: implemented. Contract: [MPA channels](../../../specs/mpa-channels/README.md). User approved removing waiting/link text and discarding QR display after navigation or refresh.

## Evidence, scope and requirements
RuntimeChannels stores binding IDs in sessionStorage and resumes pairing on mount. This restores a QR after returning to a channel. FR-1: remove the PENDING waiting text and Open authorization page link while keeping the QR and meaningful error/terminal states. FR-2: binding UI and polling live only in the mounted provider panel. Switching channel/page, browser reload or the panel Refresh clears pairing display. Returning requires an explicit new generation. Ignore and clean legacy stored binding IDs. FR-3: preserve persisted bot configuration, cancel requests/timers and reject late responses; no DELETE, provider revocation or backend changes.

## Design and review
Keep binding state in React only, remove sessionStorage persistence/resumption, clean the legacy key on mount, and reset transient pairing on panel refresh. Keep existing keyed provider mounts and abort controllers. Direct review (review-spec unavailable): API/credential/server binding lifecycle unchanged; only client resume contract changes. User request explicitly approves this change. QR hiding is not server revocation. No unresolved blocker.

## Tasks and acceptance
T-1/AC-1 (FR-1): regression verifies QR remains while waiting text/link disappear.
T-2/AC-2 (FR-2/3): test channel switch/return, legacy stored ID, refresh and cancellation; implement in RuntimeChannels.tsx.
T-3/AC-3: frontend Vitest/regression/build/assets and browser checks; update docs. Affected files: component, component tests, bilingual design/spec, frontend README and generated webui. No Python change or live cloud operation.

## Verification
2026-09-15, current uncommitted frontend diff: pass. Test-first regression: 8 failures before implementation, 31 channel component tests passed after (`cd frontend && ./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx --maxWorkers 1`). Frontend suite: 1206 passed (`npm --prefix frontend test`). Production build: pass (`npm --prefix frontend run build`), existing chunk-size warnings only. Packaged assets: 104 files and 248 references verified (`npm --prefix frontend run test:webui-assets`).

Browser checks with the real component and simulated API: pairing hides waiting/link text, keyboard switch/return does not restore pairing, browser reload does not restore it, and DingTalk panel Refresh removes pairing while preserving the bot summary; 480×850 layout checked. Component tests assert the QR image itself remains initially and disappears on reset; preview responses omitted actual image bytes. Temporary files/server/tab cleaned and viewport reset. Paired documentation, relative links and scoped whitespace checks passed. Python checks: not_applicable (no Python change). Live provider operations: not_run (UI-only change, no real accounts used).
