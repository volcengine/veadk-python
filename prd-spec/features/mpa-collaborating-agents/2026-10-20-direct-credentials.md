# Collaborator credentials entered in Studio

[中文](2026-10-20-direct-credentials.zh.md)

Change: collaborator-direct-credentials | 2026-10-20 | implemented locally, verified; not published.
Supersedes the environment-reference-only decision in the collaborating-agents design; other boundaries remain unchanged.

## Requirements and design
- FR-1: Name, URL and credential inputs use the description field's border color, scoped to this form. Reuse existing InputWithTailIcon, Textarea, Select, Checkbox and Button; no global theme changes.
- FR-2: Enter Bearer/API Key directly. Default masked, explicitly show/hide the newly entered value; clear it on successful save/cancel/refresh/auth-mode or target switch. Editing leaves the input blank and preserves the saved credential only when authentication, header and destination origin are unchanged. Changed origin requires a new credential to prevent forwarding an old secret to a different service. None clears authentication.
- FR-3: Add write-only `secret` (SecretStr, at most 8192 characters, no control characters); responses expose only `credential_configured`. Legacy `secret_env` remains accepted and usable, but the new form does not request environment setup. Never return plaintext or ciphertext. Validation errors must not echo input.
- FR-4: Encrypt the secret and its MPA/registration binding with Fernet in the existing configuration JSON. Generate a separate persistent `collaborator_credential_key` in existing `mpa_deployment_settings`, under a DB transaction lock. No new dependency, migration or environment variable. Missing key with existing ciphertext must fail, never silently rotate. DB and backups remain privileged: the wrapping key lives in the same DB, so this is not protection from DB administrators. Back up both tables together.
- FR-5: Enabled is dispatch eligibility; disabled retains configuration. Connection verification remains separate and actual task dispatch is out of scope.

## Tasks and acceptance
T-1/AC-1: Regression tests for direct create/check/resolve, persistence/restart, edit preserve/replace/clear, legacy compatibility, revision and MPA isolation, missing/corrupt key, response/validation redaction.
T-2/AC-2: UI tests for masking/toggle/reset, correct write payload and blank edits; browser check light/dark, narrow layout and input borders.
T-3/AC-3: MPA make lint/test, Studio frontend npm test/build, proxy tests and asset checks. Record executed outcomes; live cloud acceptance is not implied.

## Review and delivery
User explicitly requested direct input and consistent field appearance. Manual design review: no review-spec/front-end design skills available at repository/catalog paths; used repository SPEC and existing components. Risks addressed: credential replay to changed origin, plaintext leakage, concurrency and key-loss recovery. No new dispatch or cloud resource changes. Validation results follow below.

## Verification record (2026-10-20)

| Requirement | Evidence | Result |
| --- | --- | --- |
| FR-1/FR-2 | Browser: light/dark, 360px form, mask/show/hide, create, check, reopen, blank save, recheck; real local Runtime DB/API and simulated remote Card | pass |
| FR-2/FR-3 | Frontend 1,389 Node tests + 129 React tests; TypeScript, i18n and production assets | pass |
| FR-3/FR-4 | Runtime credential/registration tests including isolated PostgreSQL 16: 45 passed; 399/415 executable lines covered (96.14%), branch-inclusive 95% | pass |
| FR-3/FR-5 | Studio proxy/auth regressions 127 passed; Ruff/Pyright for proxy and new Runtime modules | pass |

Runtime make lint passed; full make test: 9,343 passed / 251 skipped / 0 failed, 645.31 seconds, Python 3.12.13 and Codex 0.155.1. Skipped tests are not verified; the credential suite ran separately against PostgreSQL. Browser fixtures and disposable PostgreSQL were cleaned up. No live external Agent check, cloud deployment, formal CI or image publication for this change. Default Studio Python environment lacks Ruff/Pyright; used installed tools from MPA with the Studio Python interpreter for import resolution.
