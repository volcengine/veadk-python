# Retain the OIDC ID Token in Studio Sessions

- Change ID: `studio-oidc-id-token`
- Created/revised: 2026-09-23
- Status: superseded by [Studio MPA login prewarm](../studio-mpa-login/2026-09-23-studio-mpa-prewarm.md)
- Chinese: [2026-09-23-retain-id-token.zh.md](2026-09-23-retain-id-token.zh.md)
- Component: [Studio OAuth session](../../../specs/studio-oauth-session/README.md)

## Background and evidence

Historical proposal only: a 1,519-byte access token plus a similarly sized ID token produced a roughly 4,490-byte cookie in a local size check. The successor keeps the ID token request-local instead of persisting it in the browser.

`OAuth2Handler.exchange_code_for_token()` and `_refresh_access_token_once()` receive token responses but currently construct `OAuth2Session` without `id_token`. The signed Studio session cookie therefore cannot retain an OIDC ID token for a later, separately authorized MPA identity handoff. The live Studio and MPA client IDs are assumed equal for this change, not verified here.

## Goals and non-goals

Retain an optional `id_token` from authorization-code and refresh responses in the existing Studio session, including cookie round trips. Keep legacy cookies readable. Do not add a token-sharing API, send tokens to MPA, change MPA validation, or change UserPool configuration.

## Scenarios and requirements

- `FR-1`: Given an authorization-code response with `id_token`, the resulting Studio session and signed cookie retain it.
- `FR-2`: Given a refresh response with a new `id_token`, replace the old value. If the provider omits it, retain the preceding value; consumers must still validate its expiry before use.
- `FR-3`: A legacy session lacking `id_token` remains valid and yields `None` for that field.

## Design and contract impact

Add one optional field to `OAuth2Session` and pass the existing token-response value in the two construction sites. The existing cookie encoder/decoder handles the field without a new storage format. No new HTTP route, configuration, dependency, event, or frontend type is added. The cookie is signed but not encrypted and already carries access/refresh tokens; adding an ID token can increase its size beyond browser limits. This change does not make the ID token safe to expose to browser JavaScript or prove that two OAuth clients match. Before any future MPA handoff, verify token expiry, subject, issuer, audience, authorization, and cookie-size behavior; use server-side storage if the cookie limit is exceeded.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| `FR-1` | `T-1`: add a failing login/cookie test, then retain the field | `AC-1`: login ID token survives a cookie round trip | `tests/auth/test_oauth2_auth.py` |
| `FR-2` | `T-2`: add refresh tests, then retain or replace the field | `AC-2`: refresh with/without an ID token has the stated result | `tests/auth/test_oauth2_auth.py` |
| `FR-3` | `T-3`: test legacy-cookie compatibility | `AC-3`: old cookies decode without an ID token | `tests/auth/test_oauth2_auth.py` |

## Review and delivery record

Scope approved by the user's 2026-09-23 request to retain `id_token`, explicitly excluding MPA validation changes and treating client alignment as an assumption. Review: the minimal model-and-construction change preserves the existing session/cookie boundary; the cookie-size and cleartext-cookie risks are known and remain outside this scoped change. Verification and delivery results: pending implementation.
