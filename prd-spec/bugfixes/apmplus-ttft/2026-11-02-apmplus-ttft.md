# APMPlus streaming and TTFT telemetry

[中文版](2026-11-02-apmplus-ttft.zh.md)

Change ID: `apmplus-ttft`; created/revised: 2026-11-02; status: approved.
Component: [model-timing](../../../specs/model-timing/README.md).
Predecessor: [first-token-timestamps](../../features/first-token-timestamps/2026-10-28-first-token-timestamps.md).
Inspected revision: `d9ef697b82fde94373737aae518148df348e60b0` on `feat/first-token-timestamps` (PR #1190).

## Background and evidence

The [PR review comment](https://github.com/volcengine/veadk-python/pull/1190#issuecomment-6514480806) requires the standard streaming flag, a seconds-valued TTFT span attribute, and actual TTFT Histogram recording. The supplied APMPlus Trace specification (revision 261) and Metrics specification (revision 17), read on 2026-11-02, agree with those requirements.

`ModelTiming` currently records custom timestamps and actual SDK streaming mode. `PortalMetricRecorder` already creates the correctly named TTFT Histogram with unit `s`, but its recording remains TODO. `record_call_llm()` runs on response callbacks and places existing measurements behind a usage check; it cannot establish exactly one TTFT measurement per SDK request. The original design explicitly excluded Histograms; this successor proposes that narrowly scoped extension.

## Goals and non-goals

Add `gen_ai.request.stream` and `gen_ai.chat_completions.streaming_time_to_first_token` to each observable SDK request span, and record the same TTFT value once in the existing Histogram. Preserve custom timestamp fields and model behavior.

Exclude TPOT, unrelated metric renaming, token accounting changes, client-render timing, hidden provider retries, new exporters/configuration/dependencies, frontend changes, and cloud deployment. Historical cloud evidence does not validate this new change.

## Requirements and scenarios

- FR-1: An instrumented `model_request` span has Boolean `gen_ai.request.stream` from the actual SDK request, independent of Runner streaming configuration. Preserve `veadk.model.streaming` and legacy attributes.
- FR-2: The first nonempty text, reasoning, or tool-call delta produces a floating-point seconds value `(first_token_time_unix_ns - model_start_time_unix_ns) / 1e9` under `gen_ai.chat_completions.streaming_time_to_first_token`. Reuse the same stored request-start timestamp used by custom attributes. Request ingress and outer span start are not calculation inputs.
- FR-3: At that first observation, record the identical value once in the existing same-name Histogram with unit `s`, even without usage or a recording trace span. Repeated chunks and final-response callbacks must not duplicate it. Every observable retry/fallback request owns its own latch and sample.
- FR-4: Non-streaming, no-output, and unsupported requests have no TTFT attribute/sample. Unknown actual SDK mode must not be invented from Runner configuration. A clock regression preserves raw timestamps but omits a negative duration with a bounded diagnostic; zero measured elapsed time is valid, not a missing-value placeholder.
- FR-5: Preserve samples observed before failure, cancellation, or close. Preserve original output, exception propagation, and resource cleanup. A metrics recording failure emits a bounded diagnostic without recording request content or replacing the model result/error.
- FR-6: New metric dimensions use dotted specification names and known stable values only. Include the actual requested model; omit unknown provider/response-model values. Never include prompt/output content, user/session/trace IDs, or response IDs. Continue using the existing global MeterProvider without installing an export pipeline.

Given metadata followed by a generated delta, only the generated delta records TTFT. Given two requests sharing one outer model span, each SDK child has independent fields and measurements. Given tracing disabled but a configured metrics reader, an observed streaming request still records the Histogram. Given a request with no generated delta, completion cannot fabricate a sample.

## Design, alternatives, and contract impact

Keep one measurement owner in `ModelTiming.observe()`. Store the request-start timestamp and model locally so calculation and metric recording do not depend on readable span attributes. Add a focused typed `PortalMetricRecorder` method for recording this measurement; remove only the superseded TTFT TODO. Reuse the existing instrument, unit, and bucket boundaries.

Use the per-SDK `model_request` child as the authoritative standard LLM span and label it `gen_ai.span.kind=llm`. This avoids presenting an aggregate/retry owner's lifetime as one SDK request. Existing custom timestamp mirroring to `call_llm` remains compatible; standard TTFT is not copied to an aggregate owner, avoiding stale observations after a later no-output attempt. Document this span boundary explicitly. Existing `gen_ai.is_streaming` is retained for compatibility.

Alternative: record from `record_call_llm()`. Rejected because callback multiplicity, absent usage, and retries would require additional shared state and could duplicate or lose measurements. Alternative: rename/delete custom timestamps. Rejected because timestamps remain useful and removing them would break consumers without satisfying the duration requirement.

Before implementation, update both model-timing spec languages: extend CON-2/4/6 and add a per-request Histogram contract covering FR-3/5/6. Add a predecessor note to the original design explaining this extension without rewriting historical acceptance. Update both tracing MDX pages. No persistence, permissions, HTTP/event payload, public model invocation signature, or database migration changes are needed. Rollback removes additive standard telemetry; existing custom timestamps remain usable.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification | Result |
| --- | --- | --- | --- | --- |
| FR-1..6 | T-1: reconcile bilingual design/spec and review | AC-1: consistent scope and approved design | Paired identifiers, links, direct design review | pass: approved on 2026-11-02 |
| FR-1/2/4 | T-2: add failing span contract tests, then implement | AC-2: actual Boolean mode; exact seconds; correct omissions | `tests/test_model_ttft.py`, `tests/test_model_timing.py`, `tests/models/test_model_timing_adapters.py` | pass: implemented and locally verified |
| FR-3/5/6 | T-3: add reader-backed metric tests, then wire recording | AC-3: real Histogram name/unit/count/sum/dimensions; no duplicate or missing samples | `tests/test_portal_metrics.py`, timing and adapter tests | pass: implemented and locally verified |
| FR-1..6 | T-4: run affected/regression/static/docs checks and review | AC-4: compatible outputs, cleanup, exports, and bilingual docs; changed production-line coverage >=95% | Commands below and coverage against inspected revision | local checks pass; default regression fail: one reproduced baseline MIME mismatch |

Test cases include text/reasoning/tool output, metadata-only chunks, repeat chunks, no usage, actual SDK mode differing from Runner mode, non-streaming, no output, retries/fallbacks, concurrent requests, cancellation/close before and after output, disabled tracing, configured/unconfigured MeterProvider, clock regression, genuine zero elapsed time, and a failed metric recorder. Assert Histogram type, unit `s`, count, sum, dimensions, and exported span fields using controlled clocks and provider boundaries.

Planned commands, discovered from repository guidance and manifests:

- `uv run --extra dev pytest tests/test_model_ttft.py tests/test_model_timing.py tests/models/test_model_timing_adapters.py tests/test_portal_metrics.py -q`
- `uv run --extra dev pytest tests/models tests/test_model_ttft.py tests/test_model_timing.py tests/test_portal_metrics.py tests/test_tracing.py tests/test_tracing_content.py tests/test_inmemory_exporter.py -q --cov=veadk --cov-branch --cov-report=json`
- `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`
- `uv run --extra dev pre-commit run --all-files` (and explicit changed-file checks for untracked additions)
- `npm --prefix docs run types:check`; `npm --prefix docs run build`; `git diff --check`

Use the repository-local environment; document any environment blockers rather than modifying machine-global settings. Two regression workers follow repository guidance. Actual provider/cloud calls are not part of this local change's acceptance; report local adapter/reader evidence separately from the predecessor's live tests. Commit/push remain subject to separate authorization.

## Review, risks, and delivery record

Direct review is used because `review-spec` is unavailable. Inspected calculation ownership, callback duplication, retry boundaries, missing observations, metric dimensions/privacy, failure isolation, compatibility, and bilingual equivalence. Design clarification: standard fields live on observable SDK-request children, not aggregate spans. Main risks are duplicate metric samples, wrong time boundaries/units, stale aggregate fields, and accidental dependency on trace sampling or usage. The acceptance cases directly exercise those risks.

User approval: explicitly granted on 2026-11-02 to create a new branch and implement immediately. Created `fix/apmplus-ttft` and synchronized the PR base with `git pull --ff-only origin feat/first-token-timestamps`. Implementation and component-spec/MDX reconciliation are complete. The lifecycle remains approved because the repository-wide AC-4 gate has the pre-existing failure recorded below. Runtime verification is recorded below. Source reads and specification comparison passed on 2026-11-02; repository branch checkout and `git pull --ff-only` succeeded. Implementation evidence, eight verification Gates, Change Impact, and Test Portfolio tables are recorded below and in the Chinese counterpart.

## Implementation verification (2026-11-02)

Scope: the working diff on `fix/apmplus-ttft` against `d9ef697b82fde94373737aae518148df348e60b0`, including the new test and design files. Production changes are limited to `timing.py` and `portal_metrics.py`. No unrelated user changes were present. Standard per-request fields and Histogram recording are implemented; final repository-wide verification has one reproduced baseline failure, recorded below.

### Gate status

| Gate | Status | Evidence or blocking reason |
| --- | --- | --- |
| Change Basis | PASS | Inspected the complete tracked/untracked diff against the PR head; new branch synchronized from that head. |
| Contract | PASS | FR-1..6 and CON-7..9 preserve legacy fields and define standard SDK-request fields, units, omissions, and metric ownership. |
| Impact | PASS | R-1..4 below cover spans, metrics, lifecycle, and maintained documentation. No dependency metadata, UI, payload, or deployment change. |
| Portfolio | PASS | Controlled clocks, real OTel reader/exporter, real model adapters with controlled provider boundaries, fault injection, and existing regression. |
| Baseline | PASS | Before implementation: 13 failing and 5 passing new tests; missing attributes and missing measurements caused the expected failures. |
| Execution | BLOCKED | Default regression: 7950 passed, 1 reproduced baseline MIME failure. Targeted/affected, static, and documentation checks passed; the repository-wide gate is not claimed to pass. |
| Evaluation | PASS | All changed production executable lines and changed decision arcs exercised; assertions distinguish wrong units, duplicate/missing samples, and wrong span scope. |
| Handoff | PASS | Scoped implementation and evidence delivered with the baseline regression limitation; no commit or push performed. |

### Change Impact

| Change ID | Changed contract | Affected surface | Repository evidence | Failure mode | Risk |
| --- | --- | --- | --- | --- | --- |
| FR-1/2/4 | CON-7 per-request standard fields | LiteLLM/Ark request spans and export | `ModelTiming`, actual adapter tests | Wrong mode/type/unit/start boundary; fabricated or stale aggregate TTFT | R-1 Medium |
| FR-3/6 | CON-8/9 per-request Histogram | Global metrics pipeline | `record_model_ttft`, real `InMemoryMetricReader` | Duplicate/lost samples, usage/trace dependency, wrong dimensions | R-2 Medium |
| FR-4/5 | CON-8 lifecycle and failures | Streaming, retries, cancellation, close | Timing/adapter tests and metric fault injection | Telemetry replaces model error/output; attempts mix or leak | R-3 High |
| FR-1..6 | Additive compatibility and documentation | Existing attributes, tracing pages, component specs | Existing regression, bilingual checks, docs build | Consumers receive conflicting definitions or lose old attributes | R-4 Medium |

R-1/2/4 cross observable contracts and are Medium. R-3 can affect model completion on a commonly executed path (High impact and exposure), so it is High before validation. No known material consumer remains untraced. Residual risks are bounded by local controlled-provider verification; no new live cloud export is claimed.

### Test Portfolio

| Risk ID | Boundary | Method | Cases | Oracle | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R-1 | SDK timing and span exporter | Clock control and contract tests | Text/reasoning/tool output, mode, empty/unsupported, negative/zero interval, retry scope | Exact float seconds, Boolean mode, child-only fields, correct absence | New TTFT tests plus existing LiteLLM/Ark adapter assertions | VERIFIED |
| R-2 | Real OTel metrics reader | Integration/state transition | No usage, no recording span, no exporter, repeated chunks/final callbacks, retry/concurrency | Histogram type/name/unit, exact count/sum, model isolation, exact safe dimensions | New TTFT tests; existing Portal provider/late-provider tests | VERIFIED |
| R-3 | SDK stream and recorder boundary | Fault injection and lifecycle tests | Error/cancel/close before/after first output; metrics failure | Original exceptions and cleanup preserved; observed samples retained; bounded diagnostic without error details | New TTFT tests plus existing timing and adapter lifecycle tests | VERIFIED |
| R-4 | Consumers and documentation | Regression, type/build, static review | Legacy attributes, exports, bilingual identifiers/links | Existing assertions pass; equivalent definitions and valid documentation build | Affected suite, pre-commit, docs checks | VERIFIED |

### Executed evidence

- Before the production change, `uv run --extra dev pytest tests/test_model_ttft.py -q`: **13 failed, 5 passed** (18 collected/executed). This is the expected RED result.
- After adding final-callback and no-exporter cases, `uv run --extra dev pytest tests/test_model_ttft.py -q`: **20 passed**, zero failures/skips. Negative-clock diagnostics are asserted.
- `uv run --no-sync --extra dev pytest tests/models tests/test_model_ttft.py tests/test_model_timing.py tests/test_portal_metrics.py tests/test_tracing.py tests/test_tracing_content.py tests/test_inmemory_exporter.py -q --cov=veadk --cov-branch --cov-report=json:/tmp/veadk-ttft-coverage-final.json`: **156 passed**, zero failures/skips (156 collected/executed).
- Production changed-line coverage is the intersection of added working-diff lines and coverage.py executable lines: **21/21 (100%)**, with **4/4** changed decision arcs covered. No coverage exclusions were added. Existing uncovered unrelated Portal metrics branches are outside this diff.
- `uv run --extra dev pre-commit run --all-files` plus explicit checks for new files: **pass**. Ruff initially formatted test changes; the subsequent check passed. Hooks without applicable files were skipped, not counted as execution.
- `npm --prefix docs run types:check` and `npm --prefix docs run build`: **pass**. Bilingual code identifiers/commands, relative links, new-test function lengths, and `git diff --check`: **pass**.
- The existing `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes` fails on the untouched `d9ef697b` snapshot too: expected `text/markdown`, observed `application/octet-stream`. The snapshot imported its own unmodified `writer.py`, `service.py`, and `timing.py`; its targeted run had **1 failed**. No assertion or unrelated production code was changed to hide this failure.
- `uv run --extra dev --extra sandbox --extra extensions --extra codex pytest -n 2 -m "not codex_smoke and not piagent_smoke" -q`: **fail: 7950 passed, 1 failed, 53 skipped, 4 xfailed**, plus **6 passing subtests**, in 412.98s. 8008 selected; 7955 executed including expected failures; 53 skipped. The sole failure is the unchanged baseline MIME test above. The two-worker setting follows repository guidance; skipped/expected-failure tests do not prove behavior. Live cloud/provider tests: **not_run**, outside the approved local scope. External-engine smoke tests: **not_applicable**, those engines are unchanged.

Final review confirms the existing first-output latch owns metric emission, duration calculation uses the stored SDK start rather than parent span timing, and metrics recording runs outside `span.is_recording()` guards. Only instrument recording failures are caught and diagnosed; model exceptions are not intercepted. Existing timestamps remain intact. The known baseline MIME mismatch is a repository-wide gate limitation, not TTFT acceptance evidence.

## Commit and push verification (2026-11-02)

The user explicitly authorized commit and push. PR #1190 had already been squash-merged as `c1d4096d`; the repair branch was rebased onto the fetched `origin/main` at `65f30f2881b5d09aca94ea0c5e3450852866748f`, without replaying the original PR commits. The production repair diff is unchanged.

After synchronization, `uv run --no-sync --extra dev pytest tests/models tests/test_model_ttft.py tests/test_model_timing.py tests/test_portal_metrics.py tests/test_tracing.py tests/test_tracing_content.py tests/test_inmemory_exporter.py -q` passed all **156 tests**. `uv run --no-sync --extra dev pre-commit run --all-files` passed.

`uv run --no-sync --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" -q` finished with **8044 passed, 1 failed, 55 skipped, 4 xfailed**, plus **6 passing subtests**, in 407.20s. The sole failure remains the previously reproduced baseline Markdown MIME mismatch; its production/test files are unchanged between the original PR head and the synchronized base. The repository-wide gate remains `fail`; no assertion was weakened. This authorization covers pushing `fix/apmplus-ttft`, not opening another PR.
