# Studio MPA Prewarm

- Component ID: `studio-mpa-prewarm`
- Status/revision: proposed, 2026-09-23
- Chinese: [README.zh.md](README.zh.md)
- Change: [Studio MPA login prewarm](../../prd-spec/features/studio-mpa-login/2026-09-23-studio-mpa-prewarm.md)

## Responsibility and contract

Studio owns `POST /web/mpa/identity-prewarm/{runtime_id}` and the MPA web-chat call before Runtime run. The route requires an authenticated Studio OAuth browser session, refresh credential, authorized MPA Runtime, and Runtime key-auth. It refreshes the Studio token pair, verifies the new ID token against the configured UserPool JWKS/issuer/client and Studio user subject, then sends `idToken` and `refreshToken` server-to-server to the Runtime's fixed `/identity/sessions/put`. It returns only success or a bounded error; no token enters browser JavaScript or logs. The Runtime endpoint and key come solely from Studio's trusted control-plane resolver.

## State, failure, security, and compatibility

The refreshed Studio session replaces the signed HttpOnly cookie, including when Runtime handoff fails after refresh-token rotation. ID tokens are request-local and omitted from newly encoded cookies; old cookies with the optional field remain decodable. A missing OAuth session, refresh token, MPA tag, key-auth credential, mismatched token subject, or failed upstream call is an explicit route error, but the frontend continues the MPA web-chat run so its normal login remains available. User cancellation still stops the run. The prewarm request is bounded to ten seconds on the frontend. Gateway-only sessions and Feishu chat do not use this route. No new browser-visible credential or client-controlled URL is accepted. Multiple Studio instances and independent MPA refresh rotation need live validation.

## Verification

`tests/auth/test_oauth2_auth.py` covers token/cookie state; `tests/cli/test_frontend_runtime_proxy.py` covers authorized handoff and failures. Frontend tests/build cover call order and non-MPA behavior. A real browser/UserPool/Runtime check remains necessary for production readiness.
