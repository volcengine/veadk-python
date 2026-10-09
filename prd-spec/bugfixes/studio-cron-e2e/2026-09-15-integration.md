# Studio scheduled-task end-to-end integration

[中文](2026-09-15-integration.zh.md)

2026-09-15; approved by user. Target: local Studio and the explicitly selected Beijing Runtime. FR-1: create/update/run/list scheduled tasks through both conversation and page controls, with common user ownership. FR-2: inject x-user-id from the authorized Studio principal, never from arbitrary browser headers. MPA A2A may adopt this header only with JWT disabled; verified TIP identity has precedence. JWT-enabled behavior and existing user isolation remain unchanged. FR-3: upgrade old image to current additive ADK adapter; preserve database/network/credentials and existing task records. Long-running streams keep status and eventual results. No all-user reads.

T-1: failing identity regression and minimal fixes. T-2: unit tests, changed-line coverage above 95%, frontend build/tests as applicable and secret scan. T-3: publish amd64 image and update only authorized Runtime, preserving configuration, then verify readiness. T-4: use uniquely named Web-delivery test tasks for chat/page CRUD and manual execution, verify cross-channel listing and successful runs. Disable test tasks after checks; retain run evidence. Failures must be corrected and retested. Review: scoped identity resolution reuses existing service paths, no new authentication bypass or dependency. Acceptance is live functional evidence, not only image readiness. Record checks and limitations below.

## Verification, 2026-09-15

Pass: Runtime `r-yeuugf44qob21078l38i` is Ready on image `20260915-f617c67-studio-e2e` (linux/amd64, source `f617c67`). Health, readiness, list-apps, sessions and scheduled-task list return 200. Preserved database/network/auth settings; disabled optional metadata startup and AppCenter resource discovery for the standalone deployment.

Pass: real Chrome/local Studio conversation called create/update/run/list tools. Chat task `5819ad31-a2f7-4077-8f22-084a46a27cd0` reached version 2 and run `b990fc1d-d8f2-4c0b-9b13-d7c565e63e4b` succeeded. Page controls created/edited/triggered task `51ecb600-d3b1-41c1-b810-cfec427de9e2`, version 2; run result session `5047e17e-f41e-4742-be43-b515cbf438ca` succeeded. Both tasks appear together in the Runtime list, show 100% success (2 runs), and remain disabled with Web delivery. Scheduled execution sessions appear in history.

Live follow-up fix: assistant stream projection ignores `author=user` echoes while preserving agent-authored tool responses with `content.role=user`. Regression failed before the fix and passes after it; no event storage changes.

Pass: 151 MPA tests, 85 Studio Python tests, 1100 frontend tests, 5 waiting/echo coverage tests, frontend build and bundled asset verification. Changed Python identity statements and frontend echo guard have 100% coverage. Pre-existing Pyright diagnostics remain outside this change (34 source, 20 test diagnostics); not a clean whole-file typecheck. Standard pinned pre-commit is the lint/security gate.
