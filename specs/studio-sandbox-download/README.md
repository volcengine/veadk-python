# Studio Sandbox downloads

[中文](README.zh.md)

Component: studio-sandbox-download; revision: 2026-09-17; status: active.
Owner: frontend/src/ui/SandboxFileLink.tsx, Markdown.tsx, App.tsx and adk/client.ts. Depends on existing Studio Runtime proxy and MPA session download API. Related [PRD](../../prd-spec/features/studio-sandbox-download/2026-09-17-history-download.md).

## Contracts
- CON-1: Only assistant conversation Markdown with appName/sessionId context converts absolute links beneath `/data/output/` and `/data/workspace/`. Decode URL escapes once; reject malformed escapes, traversal segments, backslashes, control characters, empty filenames and query/hash suffixes. Chinese and spaces supported. Other Markdown consumers/links retain existing behavior.
- CON-2: GET `/api/v1/sessions/{sessionId}/files/download?path={encodedPath}` uses the current app's resolved endpoint and existing authentication/identity transport. Runtime credentials remain server-side; MPA verifies session ownership and Worker enforces filesystem boundaries. No artifact lookup or new Sandbox.
- CON-3: Link activation prevents navigation, suppresses duplicate requests, shows localized busy state, saves a blob with the path basename and releases object URLs. Failure displays a local alert; activation retries. Scope changes/unmount abort requests and ignore stale responses. Existing transfer timeout applies.

## Data, compatibility and diagnostics
No persistent data/configuration or protocol changes. Existing history and streaming Markdown share rendering. Normal external links and video behavior remain. Errors use localized generic feedback (no server response bodies). Sandbox expiry/file removal can make old links unavailable; browser buffers complete files.

## Verification and change record
Tests: frontend/tests/sandboxDownload.test.tsx and sandboxDownloadClient.test.ts. Cover CON-1/2/3 including negative paths, current Runtime/session routing, cancellation and retry. Run `npm --prefix frontend test`, dedicated Vitest coverage and build, plus browser history download. PRD records results and limits. Implemented; see PRD for verification.

- CON-4: Conversation Markdown hides `file-card` and `personal-drive-enable-card` elements including their children. Download controls use primary theme colors, 16px text, 44px minimum height, visible keyboard focus and wrapping filenames. Each download control occupies its own line with content-sized width. Surrounding message text is retained. Tested in sandboxDownload.test.tsx.
