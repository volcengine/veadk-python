# Studio MPA Login Prewarm

- Change ID: `studio-mpa-login`
- Date/status: 2026-09-23, approved by the user's request to continue no-second-login development
- Chinese: [2026-09-23-studio-mpa-prewarm.zh.md](2026-09-23-studio-mpa-prewarm.zh.md)
- Components: [Studio OAuth session](../../../specs/studio-oauth-session/README.md), [Studio MPA prewarm](../../../specs/studio-mpa-prewarm/README.md)

## Background, goal, and scope

Studio's browser session has a UserPool refresh token, while MPA web chat currently has only Runtime key-auth and may ask the same user to log in again. MPA already accepts a server-authenticated `POST /identity/sessions/put`; the Runtime key-auth proxy supplies the trusted Studio user ID. Retaining a full ID token in the signed browser cookie can exceed 4 KB. This change makes Studio web chat prewarm MPA with a fresh UserPool ID/refresh-token pair, without sending tokens or Runtime keys to browser JavaScript. Feishu login and MPA's existing token validator are out of scope. The Studio/MPA UserPool client match is an operational prerequisite, not proved by source tests.

## Requirements and design

- `FR-1`: Before an MPA Runtime web-chat run, Studio attempts to refresh its OAuth session and obtain a fresh ID token. A failed prewarm does not prevent the run; MPA may then request its normal user login.
- `FR-2`: Studio authenticates and authorizes the selected MPA Runtime, verifies the fresh ID token's signature, issuer, expiry, audience, and subject, and posts the ID/refresh tokens to its fixed `/identity/sessions/put` path with the server-held Runtime key. It never accepts a browser-selected upstream URL.
- `FR-3`: Rotated refresh credentials are returned in the existing HttpOnly signed Studio cookie, while the ID token remains request-local and is excluded from the cookie to avoid browser size limits. Old cookies remain readable.
- `FR-4`: Only MPA Runtime web chat invokes prewarm. Feishu and non-MPA transports are unchanged. Prewarm failure is diagnostic only; user cancellation still stops the run.

The new `POST /web/mpa/identity-prewarm/{runtime_id}` route accepts only a Runtime ID and region. It uses the already-authenticated Studio cookie, the existing control-plane Runtime authorization and credential resolver, and a bounded outbound request. The frontend invokes it immediately before the MPA run request with a ten-second limit and the chat cancellation signal. Its status is logged without tokens; failure continues to the normal run and manual MPA login. The route returns no token. A rotated session must replace middleware's prior cookie before the response is sent, including when the Runtime handoff fails.

## Tasks, verification, and risks

| Requirement | Task | Acceptance | Test |
| --- | --- | --- | --- |
| `FR-1`, `FR-3` | `T-1`: keep ID tokens request-local and preserve rotation | `AC-1`: refresh result is usable but cookie contains no ID token | `tests/auth/test_oauth2_auth.py` |
| `FR-2` | `T-2`: add authorized prewarm endpoint | `AC-2`: trusted subject, fixed destination, no token leakage; invalid inputs fail | `tests/cli/test_frontend_runtime_proxy.py` |
| `FR-4` | `T-3`: invoke prewarm before MPA run | `AC-3`: failed handoff still starts MPA run; cancellation stops it; other transports unchanged | frontend tests/build |

No new dependency or generated Runtime configuration is planned. Risks: UserPool refresh-token rotation across multiple Studio instances, MPA later rotating the same refresh token, and a mismatched UserPool client. The browser's ten-second prewarm limit can end before an unusually slow provider refresh finishes; that case needs live validation. Test with a real browser and cloud Runtime before claiming end-to-end success. Review: existing server-only credential resolver and OAuth validator are reused; a client-supplied token, URL, or sender ID is forbidden.

Verification on 2026-09-23: `tests/auth/test_oauth2_auth.py` passed (59); `tests/cli/test_frontend_runtime_proxy.py` and auth together passed (144); `npm --prefix frontend test` passed (1305 Node tests and 25 Vitest tests); focused prewarm Vitest tests passed (4); frontend build and pre-commit passed. Changed executable Python lines: 48/48 covered; changed frontend client statements: 11/11 covered. Pyright with the project interpreter still reports 40 errors outside the changed lines. Broad parallel regression: 5069 passed, 11 skipped, 2 xfailed, 8 failed, and 2 collection errors. Six cloud failures reproduce without the optional `llama_index` extension; two self-host Sandbox collection errors reproduce without the optional `anthropic` package. The two Skill version failures did not reproduce in isolation. Real browser/UserPool/Runtime E2E: not run.
