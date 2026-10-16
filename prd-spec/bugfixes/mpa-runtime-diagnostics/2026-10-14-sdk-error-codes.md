# Preserve MPA Runtime SDK failure codes

[中文版](2026-10-14-sdk-error-codes.zh.md)

Change ID: mpa-runtime-diagnostics. Date: 2026-10-14. Status: implemented; live retry pending.
Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-10.

## Evidence, scope and approval

A BytePlus no-OV request initialized its business database and Skill Space, saved pending create intent, then failed without a Runtime ID. Its SDK error was reduced to provision/provider_error. AgentKit ApiError retains error_code, but the Runtime adapter does not record it. The user explicitly approves adding logs before retrying the same task. Direct review (review-spec unavailable) confirms bounded safe metadata, legacy diagnostic compatibility and unchanged side effects; no blocker.

## Requirements, design and tasks

- FR-1 / T-1: RuntimeCloud.call emits create_runtime/update_runtime failures using the existing diagnostic channel. These are also the requests that enable publishing; no separate release API is used in the current provisioning path. Preserve category, validated SDK errorCode and requestId when the SDK exposes one. Traverse at most eight exception/cause objects, reject cycles and use existing validators. Never parse exception text or emit request bodies, credentials, headers, provider Message or ClientToken.
- FR-2 / T-2: Reraise the same original exception; success, cancellation, request serialization, provider selection, timeout, call count and SDK retry behavior are unchanged. Neither saved inputs nor pending binding/token are modified. Skills/other operations keep their existing diagnostic behavior. Add only the two operation names to the allowlist; existing diagnostic persistence already supports these fields.
- FR-3 / T-3: Write failing isolated tests first for both providers, create/update, direct/wrapped/unsafe codes, missing Request ID, transport/cancellation, unchanged payload and successful results. Verify managed/startup tests, Ruff/Pyright, secret scan and paired docs. Update CON-10 and module READMEs. Frontend/general agents and cloud contracts do not change.

## Acceptance and risk

AC-1: Simulated Runtime SDK rejection reaches the persisted diagnostic channel with operation/category/errorCode and optional Request ID, without provider text or secrets.
AC-2: The same exception/payload and single dispatch are preserved, with bounded cycle-safe traversal, no logging on success/cancellation and no new retry/cleanup side effect.
AC-3: Affected checks pass with actual evidence. No commit/push, real API replay, server restart or cloud writes during implementation.

Historical exceptions cannot be reconstructed. Current AgentKit SDK does not expose structured Request ID on every ApiError; do not invent one. The user must load the updated backend before retrying. Original ClientToken semantics and binding checks remain in force. Unknown real provider causes are not claimed as fixed by logging.

## Verification

2026-10-14, local diff on base 2ffe6e14; preserve unrelated work. not_run: implementation checks pending. Frontend/browser/Harness/Codex gates not_applicable because their behavior is unchanged. Live Runtime create/retry not_run; user-driven reproduction follows implementation.

2026-10-14 verification: pass, the first isolated regression reproduced 11 failures before implementation. pass, Runtime/OV diagnostic targeted tests (32). pass, `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py` (1,057 tests, four dependency warnings, two workers). pass, Ruff 0.11.12 check/format and Pyright with `--pythonpath .venv/bin/python` on the two changed modules and new test (zero errors/warnings). pass, repository Gitleaks hook on 10 isolated in-scope files; no secrets. pass, paired identifiers/links and diff whitespace. Full-repository/all-files pre-commit not_run because no commit was requested; affected regression/static/secret gates cover this scope. Real cloud create/replay and service restart not_run; the user will restart and retry the original task.

Follow-up: non-200 SDK Exception(bytes) did not expose structured attributes. The original attribute-only limitation is addressed in [bounded JSON decoding](2026-10-14-sdk-json-and-restore-ov.md); this document retains the initial design and verification history.
