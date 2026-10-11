# Normalize the managed MPA registry TLS URL

[中文版](2026-09-23-mpa-registry-tls-url.zh.md)

Date: 2026-09-23. Status: implemented in the working tree. Component: [Studio MPA creation](../../specs/studio-mpa-creation/README.md).

## Evidence, scope and requirements

A newly deployed Runtime reached platform Ready in V2 but `/readiness` returned 503. Its MPA metadata bootstrap reported TypeError. Replaying the image's SQLAlchemy asyncpg connection construction with the injected registry URL reproduced `connect() got an unexpected keyword argument 'sslmode'`. VeADK's own database adapter converts this parameter, whereas the independently versioned MPA image does not.

FR-1: Normalize `sslmode` to `ssl` when injecting `SHARED_APIG_DATABASE_URL`, preserving its value, credentials, host, database and unrelated parameters. Already-compatible URLs stay byte-for-byte unchanged. Reject contradictory or repeated TLS parameters without exposing the URL.
FR-2: Both initial creation and finalization receive the compatible URL. A pending deployment whose recorded hash differs only by this normalization may resume. A lost create response must replay its original payload with its original client token. Unrelated changes remain rejected.
FR-3: Recover the authorized current Runtime by changing only this environment value, then verify platform readiness, application readiness and Studio task completion. No new PG, APIG, worker or Runtime is allocated by recovery.

## Design, tasks and acceptance

T-1 / AC-1: Add offline tests for driver connection arguments, TLS modes, conflicting parameters, initial/final payloads and retries. First demonstrate failure.
T-2 / AC-2: Add a pure URL normalizer in managed `runtime.py`; use it in the injected environment. Extend the pending-hash compatibility check for this specific legacy representation, retaining exact replay when the Runtime ID is unknown.
T-3 / AC-3: Run managed deployment regressions, changed-file Ruff/Pyright, whitespace checks and secret scanning. Apply the single-variable Runtime correction and observe the existing creation task.

Only managed MPA provisioning is affected; generic Studio conversations, UI, images, database ownership and APIG creation are outside scope. Update the owning component contract in both languages. The raw deployment profile remains available to the control plane; credentials never enter reports or tests. The URL conversion preserves the requested TLS mode; a database proxy's internal connection encryption is outside this adapter's control.

## Review, authorization and verification

Direct design review (review-spec is unavailable): reviewed compatibility, idempotency, secret handling and failure boundaries. User authorized fixing and recovering this failed creation with “帮忙解决下”. No additional design blocker remains. Live recovery may publish one additional Runtime version. Existing registry records and cloud resources are retained.

Verification (2026-09-23, `feat/from-main-20260922`, this uncommitted fix):

- **pass:** 12 new regression cases failed before implementation and passed afterward. The affected deployment selection passed 52 tests. Broader managed-creation and provisioning-environment regression passed 359 tests; the CLI selection passed 19 tests. Six initially failing service tests used a non-URL stub; their fixture now uses a valid fake PostgreSQL URL.
- **pass:** `UV_CACHE_DIR=/private/tmp/veadk-uv-cache uv run --extra dev pytest -q tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py` and the separate `tests/cli/test_cli_mpa.py` selection. CLI tests ran with local mock-server port binding allowed.
- **pass:** Ruff 0.11.12 and Pyright on `runtime.py`, `test_registry_url.py`, and `test_service.py`; Gitleaks on affected files; `git diff --check`; paired-document links/identifiers reviewed. Tools used temporary caches after the default cache path was unavailable.
- **pass (live):** Only the existing Runtime's registry environment value was corrected. V3 reached Ready, the application readiness probe returned success, the existing Studio task became `succeeded`, and the deployment registry is `ready` with `pending=false`. No additional PG, APIG, worker or Runtime was allocated. No secret values were included in evidence.
- **not_applicable:** frontend build/browser visual gates and harness smoke because no frontend, transcript or harness code changed. **not_run:** repository-wide regression and all-files pre-commit because this delivery is a scoped uncommitted fix; affected regression and secret/static checks ran. Old Runtime images are supported through producer-side normalization, without a rebuild.

T-1–T-3 and AC-1–AC-3 are satisfied. No commit or push was performed.
