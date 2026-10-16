# Decode Runtime SDK rejection metadata and restore BytePlus OV

[中文版](2026-10-14-sdk-json-and-restore-ov.zh.md)

Change ID: mpa-runtime-json-and-restore-ov. Date: 2026-10-14. Status: implemented; live cloud retry pending.
Predecessors: [Runtime diagnostics](2026-10-14-sdk-error-codes.md) and [temporary OV skip](../mpa-byteplus-without-openviking/2026-10-14-skip-new-requests.md).
Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-10/CON-17/CON-18.

## Evidence, goals and non-goals

Live CreateRuntime failure retained only provider_error. Installed SDK Service.json raises Exception(bytes) for non-200 responses; its wrapper retains the cause without structured attributes. Existing Runtime diagnostics inspect only attributes. The user now reports BytePlus OV allowlisting and requests restoring automatic OV. Authorization covers these two fixes, not real cloud creates, restarting Studio, commits or pushes. General agents, domestic payloads, IAM, billing, model defaults, resource bindings and uncertain-create protection are outside scope.

## Requirements and scenarios

- FR-1: Given a direct or wrapped SDK rejection, extract validated errorCode/requestId from attributes, HTTP/SDK structured bodies, or a single bounded exception argument containing JSON or its SDK bytes representation. Traverse at most eight causes with cycle detection. Limit argument/body parsing to 65,536 bytes/characters; reject malformed, oversized, deeply nested and non-JSON text. Never evaluate code or log provider Message, body, credentials or ClientToken. Reuse existing OV metadata validators/decoder.
- FR-2: Reraise the same exception and preserve dispatch count, cancellation, payload, token, classification and retry behavior. No cloud replay is added.
- FR-3: Built-in BytePlus ap-southeast-1 new requests again advertise automatic OV. Remove temporary skip-only UI/locales and normalization. New/editable drafts select auto without manual fields; submitted no-OV/auto/manual tasks retain original intent across configuration refresh and retry. Domestic auto and manual fallback for unsupported profiles remain unchanged.
- FR-4: Keep existing BytePlus personal developer library creation, endpoint/key injection and durable binding reuse. No existing tasks or cloud resources are rewritten. Old uncertain creates remain guarded; operator allowlisting does not prove model credentials or service readiness.

## Design and tasks

T-1 (FR-1/FR-2): Add failing tests in test_runtime_diagnostics.py for wrapped bytes/JSON/string representations, HTTP/SDK bodies, malformed/unsafe/oversized/cyclic cases, exception identity and one dispatch; extend Runtime helper only.
T-2 (FR-3/FR-4): Change profile regression to require auto and add submitted no-OV recovery tests. Restore config.py supported-provider defaults and remove only temporary skip portions in MpaCreateDialog.tsx/locales. Retain submittedIntent race protection and all unrelated BytePlus features.
T-3: Synchronize bilingual component/module documentation and supersede historical skip design. Run targeted and managed/startup Python regression, Ruff/Pyright, frontend tests/build/i18n/assets, real browser using isolated mocked APIs, scoped secret scan and paired-link/whitespace checks. Preserve unrelated work including package-lock changes.

## Review, risks and acceptance

User approval: explicit 2026-10-14 request to complete logs and restore OV. Direct design review (review-spec unavailable) found no blocker after bounding parsing, retaining original exception and immutable submitted intents. Existing dialog/Foundation styles are reused without new visual components. Referenced frontend-design/ui-ux-pro-max skills are unavailable; apply repository SPEC directly.

AC-1: Safe Runtime identifiers survive real SDK-shaped simulated exceptions; forbidden values/text never enter diagnostics; original exception/token and single dispatch survive.
AC-2: New BytePlus requests contain auto; previously submitted no-OV and auto requests preserve their identity/mode on retry and config reload; domestic behavior is unchanged.
AC-3: Required checks pass with actual evidence. No real cloud mutation or service restart. Live user-driven retry remains separate.

Parser fallback cannot reconstruct historical errors or identify transport failures with no provider response. Already submitted no-OV tasks cannot gain OV on retry; create a new request for OV testing. Actual BytePlus OV allowlisting/model usability and Runtime rejection cause remain unverified.

## Verification

2026-10-14, local diff based on 2ffe6e14. not_run: implementation gates pending. not_run: real cloud creation/retry, no cloud writes authorized for implementation. not_applicable: harness/Codex smoke, protocols unchanged. All-files pre-commit not_run: no commit requested; scoped static and secret checks required.

2026-10-14 results (local diff on 2ffe6e14): pass, pre-fix regressions reproduced 11 failures; Runtime/BytePlus/OV diagnostic targeted suite passed 73 tests, final Runtime-only suite 30. pass, managed/startup regression with two workers 1,075 tests (four dependency warnings). pass, npm --prefix frontend test: Node suite and 101 React tests; production build, i18n (2 locales/21 namespaces), asset validation (113 files/350 references). pass, Ruff 0.11.12 check/format and Pyright with repository interpreter on four Python files (zero errors/warnings). pass, actual in-app Chromium dialog with mocked APIs: new overseas auto submission, original no-OV retry identity/mode, domestic auto presentation, 420x760 viewport and Escape. Browser fixture initially used the wrong i18n import and was corrected before validation; it and the isolated Vite server were removed. One initial frontend regression incorrectly expected an unavailable reload button; corrected to verify recovery on configuration arrival. Initial Pyright fixture attribute errors were corrected with a typed SDK-shaped exception. Scope secret and paired-document checks pending below. not_run, real cloud creates, restart, all-files pre-commit/commit/push; no mutations performed. No new dependency or package-lock change in this fix.

Final review: pass, paired requirement/contract IDs, relative links and git diff whitespace. pass, repository-configured Gitleaks hook on an isolated 106-file snapshot. Initial scan omitted .gitleaks.toml and flagged a generated MarkdownPromptEditor vendor expression using anchor.key as generic-api-key; verified as code, then reran with the unchanged repository configuration. Existing repository allowlist excludes tests and built WebUI; source changes were scanned under that policy, not a newly added bypass. No source credential was found. Browser artifacts/server were removed; existing package-lock remains its pre-existing 512-line deletion. All in-scope acceptance checks complete; live provider behavior is not claimed as verified.
