# Studio deployment account from STS

[中文版](2026-10-09-sts-account.zh.md)

Change ID: mpa-studio-account. Created/revised: 2026-10-09. Status: implemented.

## Evidence and scope

Built-in Studio configures a fixed expected account. A new-account credential passes STS but fails the `checking` stage in `managed/service.py` before IAM or resource preparation. The user explicitly requested removal of this built-in account restriction on 2026-10-09. No real credentials or task payloads belong in this document.

## Requirements and scenarios

- FR-1: Studio has no expected account; a nonempty STS identity determines the deployment account for IAM, PG, network, APIG and Runtime ownership.
- FR-2: Fresh Runtime `CLAW_SPACE_ID` and `RUNTIME_IAM_ROLE_TRN` derive from the verified account and selected role. No old-account environment value overrides them in built-in defaults.
- FR-3: Explicit YAML account restrictions, caller environment overrides, referenced/template Runtime behavior and the existing check against credential account changes remain compatible.
- FR-4: Image registry addresses and Worker reference IDs are source resources, not deployment identities. Preserve their defaults; do not assume source resources exist in a new account or claim cross-account access is verified.

Given a different valid STS account, built-in provisioning reaches IAM preparation and uses that account in Runtime environment values. Given an explicit YAML expected-account mismatch, creation still stops before mutation. Given blank STS identity or account changes during creation, fail closed as before.

## Design and affected contracts

Remove built-in `account-id` and fixed account-derived environment fields. Keep the image registry as an explicitly named source registry. Fresh templates generate role name/TRN using the selected Runtime role and verified account; existing `apply_runtime_settings` overrides remain authoritative. `build_runtime_env` already derives `CLAW_SPACE_ID` from STS account, so reuse it.

Contracts: [Studio creation](../../../specs/studio-mpa-creation/README.md), [Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md). No API, database schema, frontend, task state or permission changes. No cloud mutations, deployment, process restart, commit or push are included. Cancellation and resource cleanup remain unchanged.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1, FR-2 | T-1: regression tests, profile/template fix | AC-1: simulated built-in creation without an account override uses fake STS account through IAM and Runtime | managed config/shared-resource tests |
| FR-3 | T-2: boundary regressions | AC-2: explicit mismatch fails before IAM; selected role derives correct TRN | service tests |
| FR-4 | T-3: bilingual contracts and usage | AC-3: preserved image/reference defaults, documented access limitation | document and diff checks |

Affect `managed/studio_profile.py`, `managed/service.py`, managed tests, both component specs and managed READMEs. Run `uv run --extra dev pytest tests/integrations/mpa_managed`, changed-file Ruff/Pyright and secret scanning. Frontend/browser/build are not applicable because UI and web assets are unchanged by this fix. Live cloud creation is not_run without an isolated authorized test.

## Review, approval and risks

Direct design review (review-spec skill unavailable): requirements and bilingual contracts agree; preserve explicit CLI safety checks, credential-change protection and overrides; no secret output or implicit source-resource cloning. No blockers. User instruction to remove the built-in restriction approves this bounded fix. New-account source-image/reference access can still fail later; this fix does not certify the full new-account deployment chain. Verification recorded below.

## Verification record

2026-10-09, working-tree account fix on base `ef0ad519`; previous IAM work and unrelated lockfile changes retained.

- pass: pre-fix profile/shared-resource regression, 5 expected failures reproduced the fixed-account guard; after implementation the same flow passes with simulated STS identity, IAM preparation and account-derived Runtime metadata.
- pass: `uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py -q`: 496 passed. A new role test initially used an invalid fixture MPA ID; corrected to the supported format, then the full target passed.
- pass: `uvx --from ruff==0.11.12 ruff check` and repository pre-commit Ruff format/check for the five changed Python files; production Pyright initially passed. Test Pyright found two pre-existing fixture typing issues and one new missing AsyncMock assertion; fixed minimally, final check recorded below.
- pass: changed-file `uv run --extra dev pre-commit run --files` including Python, bilingual specs, managed README and this design: Ruff and hardcoded-secret scan passed; YAML scan not_applicable (no YAML changes).
- not_applicable: frontend tests/build/browser, general-agent chat and sidecar gates; this fix changes no frontend/chat/sidecar contracts or generated assets.
- not_run: full repository regression and all-files pre-commit; no commit requested, narrow provisioning regressions cover this fix. Live new-account creation, image/reference access and server restart are not_run; no cloud mutation was performed.

Review: existing CLI account assertion is retained for explicitly configured profiles; built-in profile omits the assertion input. Verified account remains the registry scope and credential-change guard. Additional fixture assertions/monkeypatch only repair typing in the affected tests. Both document languages and relative links are reconciled.

- pass: final `uvx pyright --pythonpath .venv/bin/python` for both production files and all three affected test files: 0 errors, 0 warnings. Post-fixture `uv run --extra dev pytest tests/integrations/mpa_managed/test_service.py tests/integrations/mpa_managed/test_studio_shared_resources.py -q`: 70 passed. Final changed-file pre-commit passed.
