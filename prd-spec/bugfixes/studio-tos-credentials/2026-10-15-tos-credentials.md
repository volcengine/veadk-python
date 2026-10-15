# Studio TOS credential handoff

- Change ID: `studio-tos-credentials`
- Date: 2026-10-15
- Status: implemented
- [中文](2026-10-15-tos-credentials.zh.md)
- Contract: [Studio creation](../../../specs/studio-mpa-creation/README.md)

## Evidence and scope

DeploymentResourceService receives resolved credentials, but its TOSService
constructor discards them and independently resolves credentials. Cloud BytePlus
resource listing can therefore fail before making a TOS request. CR already
consumes these credentials. No frontend, Runtime image, database, dependency,
permission or cloud-resource changes are required.

## Requirements and design

- FR-1: With explicit complete AK/SK, resolve the provider/region TOS endpoint
  through VolcConfiguration and construct TosClientV2 with that AK/SK and session
  token. Adapt its bucket response through the existing client/actual_region
  shape; do not patch SDK globals or mutate process environment.
- FR-2: Without complete explicit credentials, retain the existing TOSService
  resolution path. Both Volcengine and BytePlus retain endpoint resolution,
  regional filtering, pagination and resource validation.
- FR-3: Route invocations resolve credentials and construct a service per request;
  rotated credentials take effect on the next request. No cross-request client
  cache or new retry/cancellation policy is introduced.
- FR-4: Errors remain HTTP 400/502 as appropriate; credential values are redacted
  by the existing route handler. No secret persistence or response fields added.

## Tasks and acceptance

1. T-1: Add failing explicit-credential, rotation and redaction tests in
   tests/frontend/server/test_deployment_resources.py (FR-1/3/4).
2. T-2: Adapt frontend/server/deployment_resources.py and preserve fallback;
   cover both providers and existing bucket validation (FR-1/2).
3. T-3: Update paired contract and run targeted pytest, Ruff, Pyright and diff
   checks. No UI changes, so frontend build/browser gates are not applicable.

Acceptance: mocked TOS calls receive current credentials including token;
no-credential callers retain SDK fallback; existing list/validation tests pass;
SDK errors cannot expose supplied credentials. Live cloud deployment is separate
and not authorized by this code-fix request.

## Risks and review

The raw TOS response differs from the wrapper response: reuse _tos_buckets to
normalize it and test list/validation consumers. Keep endpoint resolution in the
SDK rather than hardcoding hosts. One request keeps one credential snapshot;
rotation during a request is not retried automatically. Rollback is code-only.

The user approved the proposed scope with “改改”. Direct design review (review-spec
skill unavailable) confirmed scoped changes, provider compatibility, secret
handling, testability and paired-language equivalence; no blockers. Verification
is pending. No production code or tests were modified before this review.


## Verification (2026-10-15)

Scope: local TOS credential handoff diff based on `8ae26a6d`.
- `pass`: regression first reproduced five failures; two fallback cases passed.
- `pass`: `uv run --extra dev pytest -q tests/frontend/server/test_deployment_resources.py`
  — 38 passed, one upstream Starlette deprecation warning. All cloud calls were mocked.
- `pass`: Ruff 0.11.12 check and format on both changed Python files.
- `pass`: `uv tool run pyright --pythonpath .venv/bin/python frontend/server/deployment_resources.py tests/frontend/server/test_deployment_resources.py`
  — zero errors/warnings.
- `not_applicable`: frontend assets/build/browser; no UI or HTTP shape changes.
- `not_run`: live cloud acceptance and deployment; requires running the updated
  Studio service with its IAM credentials. No cloud resources were changed.

Implementation review confirmed the existing bucket normalization and regional
validation are reused; the fallback remains unchanged. No credentials are added
to logs, persistent state or browser output. Credential refresh is covered for
successive resource-list requests, not automatic mid-request recovery.

Submission verification on 2026-10-15: fetched origin and rebased onto the
unchanged tracking branch at `8ae26a6d`; `uv run --extra dev pre-commit run
--all-files` passed all hooks, and the targeted suite passed all 38 tests again.
