# First-token timestamps

[中文版](2026-10-28-first-token-timestamps.zh.md)

Change ID: `first-token-timestamps`; created/revised: 2026-10-28; status: approved (implementation and local verification complete; current publication checks are tracked in PR #1190).
Component: [model-timing](../../../specs/model-timing/README.md). Base: `23014771`.

## Background, scope, and approval

A360 needs timestamps to analyze model and Agent waiting time. Existing `portal_metrics.py` defines TTFT/TPOT instruments but leaves recording as TODO; response tracing alone does not preserve first-output receipt. The user explicitly narrowed scope to first-token timestamps, timing definitions/ranges, and non-streaming distinction, then authorized implementation on a new branch, changed-line coverage >=95%, and real cloud E2E. This approval covers isolated test deployment. The user subsequently authorized committing and pushing this feature branch. PR creation is not requested.

Goals: additive timing attributes on request/model spans, receipt-time capture without usage dependency, documented scopes, live cloud proof. Non-goals: TTFT/TPOT histograms, client-render timing, provider inference timestamps, hidden provider retry instrumentation, external-engine model interception, frontend changes, dependency upgrades.

## Requirements and scenarios

- FR-1: HTTP requests and direct Runner calls establish isolated request timing before preprocessing (CON-1/5).
- FR-2: SDK requests capture model start and first generated delta for text/reasoning/tool-call streams; empty/metadata/final aggregate events are ignored (CON-2/3/6).
- FR-3: Non-streaming and unsupported/no-output paths expose explicit status with absent first-token timestamp; retries and cancellation retain accurate attempt evidence (CON-4/5).
- FR-4: Existing cloud exporters and JSON dumps retain the timing attributes without exposing content or changing responses (CON-6).

Given a stream beginning with role metadata, when text arrives, then its receipt timestamp is latched once. Given reasoning or tool arguments precede text, the first generated delta is tagged by type. Given no usage, timing remains present. Given a non-streaming request, completion never becomes a first token. Given two parallel requests or resumed generator iterations, timestamps remain associated with the correct invocation. Given a failed pre-output attempt and retry, child attempt spans are distinct. Given generator cancellation, attempt spans end and the original cancellation propagates.

## Design and impact

Use a small shared timing module with request ContextVar, ASGI middleware, yield-safe Runner propagation, content-delta classification, and a per-SDK-request span recorder. A timed LiteLLM client subclass intercepts the actual SDK call before ADK aggregation; Ark capture is at its raw event loop. This avoids estimating first output from final telemetry and avoids globally patching third-party clients. Supported HTTP factories install the middleware once. Existing annotation processing copies request timing to invocation/agent spans. Final telemetry marks unsupported paths without inventing model start.

Affected code: timing module, LiteLLM client/RetryingLiteLlm, ArkLlm, Runner, telemetry, in-memory annotation processor, AgentKit/Harness factories. Generated AgentKit projects already use the shared factory. No auth or database contracts change. Existing tools, content redaction, retry/fallback behavior, and exports remain intact. Rollback removes additive fields/code; no migration is required.

## Tasks and acceptance

| Requirement | Task | Acceptance | Test/command | Result |
| --- | --- | --- | --- | --- |
| FR-1 | T-1: request boundary/context | AC-1: correct start/source; no context leakage | `uv run --extra dev pytest tests/test_model_timing.py -q` | pass: request/context contracts |
| FR-2/3 | T-2: adapter instrumentation | AC-2: first delta latched; non-streaming absent; attempts terminate | timing and adapter regression tests | pass: 55 timing/adapter cases |
| FR-4 | T-3: span/export wiring | AC-3: attributes survive export and dump | tracing/integration regression tests | pass: actual cloud exporter/dump |
| FR-1/2/3/4 | T-4: verification | AC-4: changed executable line coverage >=95%; required checks pass | coverage JSON against `23014771`; `uv run --extra dev pre-commit run --all-files`; `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | pass: 100% coverage, static/docs checks; fail: one existing default-regression case |
| FR-1/2/3/4 | T-5: isolated live cloud E2E | AC-5: deployed branch code, real streaming/non-streaming model calls, exported timestamps verified | isolated AgentKit Runtime; protected environment credentials; HTTP calls and exported span assertions | pass: 6 real cloud cases, source hashes verified, Runtime deleted |

## Review, risks, and delivery

Direct design review completed because `review-spec` is unavailable. PRD/spec responsibilities, bilingual identifiers, no-usage/empty/non-streaming semantics, generator context and resource cleanup, request source, privacy, compatibility, testability, and deployment authorization have been reconciled; no design blocker remains. User authorization is the implementation request following the agreed scope. Implementation review verified raw SDK interception, yield-safe request context, stream cleanup, compatible client injection, no-content timing, and factory/export consumers. The feature-specific acceptance evidence is complete. AC-4's repository-wide default-regression condition remains fail for one existing Sidecar test reproduced on the comparison base; this PRD stays approved rather than claiming all delivery gates passed. SDK boundaries do not expose internal provider retry start. HTTP timing starts at ASGI entry and is not browser-visible wait.

## Verification conclusions (2026-10-28)

Comparison base: `2301477104f6f77e76c8182529545950e2d8ae6e`; branch: `feat/first-token-timestamps`. The inspected diff includes every modified tracked file and new untracked production/test/design file. The user's original dirty checkout is preserved in a separate worktree. Python 3.12.13, google-adk 2.7.1, LiteLLM 1.83.14, and the repository environment with all extras were used; test commands retained that environment with `--no-sync`. No dependency metadata changed.

Old behavior did not preserve first generated delta receipt. CON-1..6 now define additive UTC Unix-nanosecond attributes, source/mode/type/status, per-SDK-request attempt spans, and unchanged response/error propagation. HTTP factories, Runner, raw adapter loops, final telemetry, existing exporters/dumps, and bilingual user documentation are the affected consumers. Generated AgentKit projects already call the shared factory. No frontend UI, schema migration, authentication, or metric histogram contract changes.

### Gate status

| Gate | Status | Evidence or blocking reason |
| --- | --- | --- |
| Change Basis | PASS | Complete tracked/untracked diff inspected against `23014771`; original work preserved. |
| Contract | PASS | FR-1..4 and CON-1..6 agree with code and both document languages. |
| Impact | PASS | R-1..7 map request, model, lifecycle, export, factories, compatibility, and docs consumers. |
| Portfolio | PASS | Controlled clocks, raw SDK boundaries, failure injection, ASGI contracts, cloud E2E, and existing regression. |
| Baseline | PASS | Missing timing module was RED; close-before-iteration was RED then GREEN. Existing Harness HTTP test preconditions were corrected without changing assertions; two collection-context cases are GREEN. |
| Execution | PASS | Changed behavior checks executed; exact final counts below. One unrelated default-regression failure is reproduced on the comparison base and remains `fail`. |
| Evaluation | PASS | 208/208 changed executable production lines; 53/54 changed branch arcs; all material feature risks verified; the remaining Ark optional-close guard branch is explained below. |
| Handoff | PASS | Bilingual contracts/docs reconciled, live evidence saved without content/credentials, isolated cloud Runtime deleted; commit/push subsequently authorized. |

### Change Impact

| Change ID | Changed contract | Affected surface | Repository evidence | Failure mode | Risk |
| --- | --- | --- | --- | --- | --- |
| FR-1 | CON-1/5 request source and propagation | Runner, ASGI request/invocation spans | `timing.py`, `runner.py`, application factories | Request timing leaks across yields/concurrent requests or begins after preprocessing | R-1 High |
| FR-2 | CON-2/3 first delta | LiteLLM and Ark raw SDK responses | `timed_lite_llm.py`, `ark_llm.py` | Metadata/aggregates counted; reasoning/tool output missed; usage dependency | R-2 High |
| FR-3 | CON-4 mode/status | Model spans and unsupported engines | `ModelTiming`, `mark_uninstrumented_model` | Non-streaming completion or invocation start falsely becomes first-token/model start | R-3 High |
| FR-3 | CON-2/5 attempts and termination | Retry, error, cancellation, stream closure | `RetryingLiteLlm`, `_TimedStream`, Ark response loop | Leaked spans/resources, replayed output, lost first-output evidence | R-4 High |
| FR-4 | CON-6 export | OTel processors/exporters and trace dump | `inmemory_exporter.py`, `telemetry.py`, live `/e2e/evidence` | Timing disappears on export or sensitive content is added | R-5 Medium |
| FR-1/4 | Additive compatible wiring | AgentKit/Harness factories, generated apps, existing callers | Existing AgentKit/Harness/Runner/model test contracts and generator factory call sites | Request events, route/session behavior, or public client injection regresses | R-6 High |
| FR-1..4 | Maintained definitions | PRD/spec and tracing pages in both languages | Paired `.md`/`.zh.md`, `.mdx`/`.en.mdx` | Scope/identifiers disagree or MDX breaks the docs build | R-7 Medium |

High ratings reflect common public exposure plus timing/lifecycle hazards; Medium ratings reflect cross-module export/document boundaries. No new authorization or persistence risk is introduced. Coverage reduces execution uncertainty; it does not reduce failure impact severity.

### Test Portfolio

| Risk ID | Boundary | Method | Cases | Oracle | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R-1 | ASGI/async generators | Clock control, concurrency, context/closure contracts | HTTP vs Runner, inherited start, parallel yields, errors/close, non-HTTP scope | Correct source/start; caller context restored; request isolation | `tests/test_model_timing.py`; 2 concurrent live cloud calls | VERIFIED |
| R-2 | Actual owned adapters; provider boundary controlled | Equivalence partitions and adapter integration | Text/reasoning/tool deltas; empty/metadata/aggregate; missing usage | Timestamp latches once on first generated delta before ADK aggregation | Both new test modules; 4 real cloud adapter/mode cases | VERIFIED |
| R-3 | Timing state/telemetry | Mode/status contracts | Non-streaming, no output, unsupported, no recording tracer | Explicit status and absence of fabricated model/first-token time | Unit/tracing tests and both real cloud non-streaming cases | VERIFIED |
| R-4 | SDK request/iterator lifecycle | Failure injection and real VeADK retry integration | Pre-output 429 retry, error/cancel, close before/after iteration, close error | Distinct child spans, preserved output/errors, original stream closes once, terminal outcome | `tests/models/test_model_timing_adapters.py` and existing retry/fallback tests | VERIFIED |
| R-5 | Actual exporter/dump | Integration and privacy inspection | Cloud-exported request/model fields; source fingerprint | Expected attributes/parent/order survive actual dump; timing adds no content | 6 sanitized live evidence files, credential-content check, pre-commit scans | VERIFIED |
| R-6 | Factories and existing SDK callers | Contract/affected/default regression | Routes, session creation/config, Runner events, adapters/retries/fallbacks | Existing assertions retained; additive timing middleware and fields | 244 affected tests; final default-regression and baseline conclusion below | VERIFIED |
| R-7 | Docs build and paired files | Type/build, identifiers and relative links | Chinese/English definitions and valid MDX | Equivalent fields/IDs/scopes; site compiles and type-checks | Docs commands, paired-language/link check, `git diff --check` | VERIFIED |

### Executed checks

- `uv run --no-sync --extra dev pytest tests/models/test_model_timing_adapters.py tests/test_model_timing.py -q`: **55 passed**, zero failures/skips. Provider calls are controlled at the SDK boundary; these are local adapter tests.
- `COVERAGE_FILE=/tmp/veadk-first-token-delivery.coverage uv run --no-sync --extra dev pytest tests/test_tracing_content.py tests/test_tracing.py tests/test_inmemory_exporter.py tests/test_runner.py tests/runner/test_runner_contract.py tests/integrations/agentkit/test_app.py tests/cloud/test_harness_app_contract.py tests/cloud/test_harness_app_http.py tests/models tests/test_model_timing.py --cov=veadk --cov-branch --cov-report=json:/tmp/veadk-first-token-coverage-delivery.json --cov-report= -q`: **244 selected/executed/passed**, zero failures/skips.
- `uv run --no-sync --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" -q`: **7,987 selected; 7,945 executed (including 4 expected failures); 7,940 passed, 1 failed, 42 skipped, 4 xfailed; 6 subtests passed; 472.86s; status: fail (existing comparison-base failure)**. Two workers match repository policy. The Codex/Pi smoke markers are excluded by the repository default; external-engine model instrumentation is outside this feature's scope. Skipped/expected-failure cases provide no live evidence.
- Comparison-base execution with full test collection, `-n 2 -k test_run_wraps_child_with_sidecar_environment -q`: **1 failed**. The remaining default-regression failure is the same existing Sidecar child-model-URL assertion (fixed port versus the relay URL). It is not changed or suppressed by this feature.
- `uv run --no-sync --extra dev pre-commit run --all-files` and explicit `--files` for newly added Python/design/spec files: **pass** for Ruff, formatting and applicable secret/dependency checks. Hooks with no matching file are reported skipped, not executed.
- `npm --prefix docs run types:check` and `npm --prefix docs run build`: **pass**. Docs dependencies came from the existing pnpm lock; no package/lock changes.
- Paired-language identifiers, relative links, full production-file SHA256 versus the cloud build, credential-content inspection, and `git diff --check`: **pass**.

Changed-line coverage is computed from the entire Git diff plus all lines in new untracked production Python modules, intersected with coverage.py executable lines. Tests and Markdown are not production executable lines. No coverage exclusions were added. Result: **100% (208/208)**. Both new production modules have 100% line and branch coverage. The overall changed branch arcs are **53/54**; the unexecuted arc is Ark's optional missing-`close` guard, while the verified real Ark SDK stream implements async `close`. Normal/early-close/error paths use that actual interface.

The timestamp, status/absence, one-event latch, request isolation, parent relationships, original output and terminal cleanup assertions discriminate plausible defects; aggregate coverage alone is not the oracle.

### Real cloud E2E

Region: `cn-beijing`; isolated Runtime: `r-yey87ec8hs2hv32antzi`; actual model: `doubao-seed-2-1-pro-260628`; result: **6/6 pass**. The branch wheel was deployed to the cloud Runtime with all nine changed production files matching SHA256. Calls used the real LiteLLM Chat and Ark Responses adapters and real model service, through the actual VeADK app factory/middleware and Runner; evidence came from the built-in trace exporter/dump. This is distinct from locally controlled SDK-boundary tests.

Chat streaming/non-streaming, Responses streaming/non-streaming, and concurrent Chat/Responses streams returned nonempty real output and completed. Streaming spans had `http` source, correct `call_llm` parent, `sdk_request` scope, `observed` status/type and request-start <= model-start <= first-token <= span-end. Non-streaming spans had actual SDK `streaming=false`, `non_streaming` status, and no first-token time/type. Concurrent requests retained distinct request starts/session evidence. Exported parent fields agreed with child attempts. The isolated Runtime was deleted after evidence capture.

Sanitized evidence is retained outside Git in `veadk-first-token-20261028`; conclusions: `cloud-verification.json`; individual cases: `chat-stream.json`, `chat-nonstream.json`, `responses-stream.json`, `responses-nonstream.json`, `concurrent-chat.json`, `concurrent-responses.json`; diff coverage: `changed-coverage.json`. Only verification conclusions are recorded here; no credential or troubleshooting history is included.

### Delivery limits

Request start is server ASGI ingress or direct Runner execution, not browser submission/render. Model start is adapter SDK request, not provider inference. Opaque LiteLLM/provider retries remain within one SDK request; external/custom engines have explicit unavailable status. No new TTFT/TPOT histogram or cross-host duration guarantee is added. Cloud proof covers one Beijing Runtime and the two supported adapters/model modes; no broad provider matrix or load benchmark is claimed. The existing Sidecar regression above remains outside this change. Commit and push are subsequently authorized; no PR is requested. Git history and the remote feature branch record publication.

Pre-publication verification (2026-10-28): fetched and rebased against `origin/main` (`23014771`, unchanged); all applicable pre-commit hooks passed and all 244 affected tests passed again. Production SHA256 values still match the real cloud E2E build.

CI follow-up (2026-10-28): [test stabilization](../../bugfixes/pr1190-ci/2026-10-28-stabilize-concurrent-tests.md) corrects the concurrent Sandbox test oracle and isolates the existing Sidecar fixture. The former baseline failure is resolved. Latest local default regression: **7,942 passed, 0 failed, 42 skipped, 4 xfailed; 6 subtests passed**. Historical failures above describe the original run. All nine production hashes, 100% (208/208) changed production-line coverage, and 6/6 real cloud E2E evidence remain unchanged. PR creation and the CI follow-up are now explicitly authorized. Published checks are available at [PR #1190](https://github.com/volcengine/veadk-python/pull/1190/checks).
