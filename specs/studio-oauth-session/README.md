# Studio OAuth Session

- Component ID: `studio-oauth-session`
- Status: proposed pending verification
- Revision: 2026-09-23
- Chinese: [README.zh.md](README.zh.md)
- Change: [Studio MPA login prewarm](../../prd-spec/features/studio-mpa-login/2026-09-23-studio-mpa-prewarm.md)

## Responsibility and entry points

`veadk/auth/middleware/oauth2_auth.py` owns Studio's OAuth authorization-code exchange, token refresh, `OAuth2Session`, and signed browser session cookie. The Identity provider owns token issuance; Studio MPA prewarm consumes a request-local ID token.

## Proposed contract

- `CON-1`: `OAuth2Session.id_token` is optional and defaults to `None`, so older signed cookies remain decodable.
- `CON-2`: Authorization-code exchange and refresh retain a returned `id_token` only in the request-local session; a refresh without a new ID token does not reuse an old one.
- `CON-3`: New session cookies exclude `id_token`; old signed cookies with that optional field remain readable. Cookies are signed, not encrypted, and HttpOnly. A downstream refresh override wins when the middleware writes the response cookie.
- `CON-4`: `validate_id_token()` checks JWKS signature, issuer, expiry, and configured client audience before the prewarm consumer compares subject.

## State, data, security, and compatibility

The token endpoint is the source of truth; the cookie is the existing portable access/refresh-token session store. Concurrent refresh coalescing is unchanged. Old cookies remain valid. A prewarm request returns a rotated refresh token to the cookie even if Runtime handoff subsequently fails. ID tokens never enter new cookies or browser JavaScript.

## Verification and limitations

`CON-1`–`CON-4` map to login, refresh, legacy-cookie, validation, and middleware-override tests in `tests/auth/test_oauth2_auth.py`. Live UserPool behavior, client alignment, and production cookie size require external validation.
