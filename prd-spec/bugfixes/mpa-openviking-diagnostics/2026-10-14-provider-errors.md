# Preserve OpenViking provider error diagnostics

[中文版](2026-10-14-provider-errors.zh.md)

Change ID: mpa-openviking-diagnostics. Date: 2026-10-14. Status: implemented; live reproduction not performed.
Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-10 and CON-18.

## Evidence and scope

A BytePlus creation failed at CreateOpenVikingCollection with provider_error. The task retained neither the structured provider code nor Request ID, and the uncertain-create guard subsequently reported openvikingCreateUnknown. A read-only account/region listing returned zero collections, but this cannot recover the original rejection. The user requested error logging after this diagnosis. This change preserves safe error metadata for both OV adapters; it does not change create parameters, model endpoints, error categories, retry eligibility, resource binding or uncertain-create recovery. Historical errors cannot be reconstructed.

## Requirements and scenarios

- FR-1: Structured OV response errors retain the interface operation, safe provider errorCode and Request ID in the existing diagnostic event. Structured HTTP/SDK exception bodies use the same extraction; malformed bodies and transport exceptions emit the existing category without raw text.
- FR-2: Permit only nonsecret bounded codes (1–128 characters, capitalized ASCII identifiers with dot/underscore separators) and existing hex/UUID Request IDs. Reject arbitrary text, credential-shaped values, URLs, multiline strings and oversized inputs. Never log provider Message, request/response bodies, model credentials, authorization headers or exception text.
- FR-3: Add optional errorCode to validated diagnostic events and an additive error_code SQLite column. Existing four-field and requestId events remain compatible, old records remain intact, retention remains 100 events per task, and the parent logs validated metadata with task/stage context. Public task responses remain unchanged.
- FR-4: Preserve domestic and BytePlus creation behavior, read retry limits, single create dispatch, cancellation and duplicate-create protection. OV errors remain enum-only user-visible messages.

## Design and affected files

T-1 (FR-1/FR-4): Add safe metadata extraction to managed/openviking.py using structured JSON bodies only; capture Request ID on malformed responses with a missing or invalid Result where available. Keep provider transports and create payloads unchanged.
T-2 (FR-2/FR-3): Extend managed/diagnostics.py validation/report and managed/tasks.py persistence/logging. Validate before data crosses the child/parent boundary. Existing IAM and Worker diagnostics continue to work.
T-3 (all requirements): Add tests/integrations/mpa_managed/test_openviking_diagnostics.py with mocked response errors for both providers, exceptions/transport errors, hostile metadata, interrupted create retry protection, persisted metadata and old-schema migration. Run these regressions before implementation, then affected MPA tests and static/secret checks.
T-4: Synchronize this bilingual design and CON-10/CON-18. No frontend assets or Runtime adaptation are needed because task HTTP fields and UI behavior do not change.

## Review, risks and acceptance

Approval: the user's 2026-10-14 request to add OV creation error logs accepts the previously proposed diagnostic capture. Direct review performed because review-spec is unavailable: structured-only extraction, secret exclusion, additive schema, legacy compatibility, bounded diagnostics and unchanged cloud side effects reviewed; paired documents are equivalent. No blocker.

- AC-1: A simulated BytePlus or domestic provider rejection produces operation/category/errorCode/requestId sufficient for lookup, while provider text and credentials never reach logs/events/errors.
- AC-2: Invalid metadata is omitted, legacy events are accepted, new metadata persists after reopening an isolated task database, and migration preserves existing rows.
- AC-3: Transport failures, read retries and uncertain-create duplicate protection retain existing behavior.
- AC-4: Affected Python tests, Ruff/Pyright, whitespace, paired contracts and secret checks pass. Real cloud writes, service restart, resetting failed tasks, commit and push are outside this request.

Live reproduction requires a later newly dispatched request after loading the change; the existing uncertain task does not automatically repeat its create. Code validation cannot prove overseas model endpoint availability.

## Verification

2026-10-14, local diff based on 2ffe6e14, preserving unrelated work. pass: the first regression reproduced 10 failures; after implementation the affected managed MPA/startup suite passed 1,040 tests with four dependency warnings (`uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py`, two workers). Two subsequent structured-SDK-body cases brought the targeted diagnostic suite to 20 passing tests (`uv run --extra dev pytest -q tests/integrations/mpa_managed/test_openviking_diagnostics.py`). pass: Ruff 0.11.12 check/format and `uvx pyright --pythonpath .venv/bin/python` on all four changed Python files (zero errors/warnings). Initial Pyright without the repo interpreter could not resolve dependencies; the explicit interpreter resolved this without machine-global changes. pass: the repository Gitleaks hook on an isolated staged copy of the 11 in-scope files; no secrets. pass: paired document identifiers/links and diff whitespace. not_run: full-repository/all-files pre-commit because no commit was requested and the focused Python/static/secret gates cover this scope. not_applicable: frontend/browser/Codex/Harness checks because no UI, generated assets or execution contracts change. not_run: cloud creation and live error reproduction; no additional writes authorized.
