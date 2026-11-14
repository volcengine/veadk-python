# Run each evaluation pass once, not once per case

[中文版](2026-10-27-evaluator-model-calls.zh.md)

## Metadata

- Change ID: `adk-evaluator`
- Created/revised: 2026-10-27
- Status: implemented
- Component: no maintained component spec covers evaluation; see the no-impact conclusion below

## Background, goals, and scope

`ADKEvaluator.evaluate()` loops over the eval cases and, for each case and each run, calls `generate_actual_outputs()`. That method already runs the agent on **every** case of the eval set. Evaluating `C` cases with `R` runs therefore makes `C x R x C` agent runs instead of `C x R`. With a real model each run is a paid call.

Measured on 1.1.19 and confirmed unchanged on `main` (`2301477`) by reading the loop: with a scripted model that counts calls, 3 cases x 1 run made 9 model calls, 3 x 2 made 18, and 6 x 2 made 72. A 27-case set with 2 runs would make 1458 calls instead of 54. The scores themselves are not wrong: each case still reads its own result, so the defect is cost and latency, not correctness. The `veadk eval --evaluator adk` command uses this evaluator, so it is affected too. The `DeepevalEvaluator` was not examined.

The fix runs the agent once per run and scores every case from those runs. It does not change thresholds, metrics, the result or failure structures, the public signatures, the eval-set formats, or the `DeepevalEvaluator`.

## Scenarios and requirements

- FR-1: Given `C` cases and `num_runs = R`, `evaluate()` calls `generate_actual_outputs()` exactly `R` times, so the agent runs `C x R` times in total.
- FR-2: Given the same actual outputs as before, each case is scored on the same invocations in the same run order, and returns the same results and failure messages as before.
- FR-3: Given a failing case, only that case is reported as failed, and the other cases are unaffected.
- FR-4: Each run's actual values are captured as ADK invocations right after its pass, because the next pass overwrites them in place.

## Design and contract impact

Hoist the run loop above the case loop. After each pass, convert the actual values of all cases into ADK `Invocation` objects (the existing conversion, moved into `_to_actual_invocation`) and keep them per run. Inside the case loop, the case's actual invocations are those of every run, in run order, which is what the loop produced before. Alternatives rejected: caching `generate_actual_outputs()` results per call index couples to the loop order; changing `generate_actual_outputs()` to take a case would alter a shared `BaseEvaluator` contract used by `DeepevalEvaluator`.

Public imports, signatures, defaults, return values, eval-set formats, configuration, dependencies, concurrency, and security are unchanged. The only observable change is that the agent is called fewer times. Session ids are still regenerated before each run. No documentation page describes the call pattern.

No component-spec impact: `specs/` has no evaluation component, and this changes neither an interface nor state, only how many times an existing call is repeated. No spec is created for a single bugfix.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1 | T-1: add a failing regression test, then hoist the run loop | AC-1: 3 cases x 2 runs makes 2 passes, not 6 | `uv run --extra dev --extra eval pytest tests/test_adk_evaluator.py -q` |
| FR-2, FR-3 | T-2: keep the conversion identical, add a failing-case test | AC-2: a wrong tool call fails only its own case and the failure names the trajectory metric | same command |
| FR-4 | T-3: convert after each pass | AC-3: results across runs stay in run order | covered by AC-1 and AC-2 |
| All | T-4: run Ruff and the focused tests, reconcile both languages | AC-4: checks pass and limits are recorded | see delivery record |

## Risks and review

With a stochastic model, a case now uses results from the same `C x R` runs rather than from `C` repeated sweeps, so its distribution is unchanged and only the extra, discarded runs disappear. Nothing in the loop depended on those extra runs. Callers that counted on the extra runs for rate-limit warm-up are not known and are not expected.

Design reviewed directly: scope, compatibility, tests, and bilingual equivalence have no open blockers. User approval: request on 2026-10-27 to submit this fix upstream.

## Delivery record

- Baseline: `2301477`; verification date: 2026-10-27
- Scope: `adk_evaluator.py` loop, one regression test file, and this bilingual PRD; T-1 through T-4 complete
- Regression before the fix: fail as expected, `assert 6 == 2` for the pass count; the failing-case test passed on both versions
- Focused checks after the fix: pass, 4 tests via `uv run --extra dev --extra eval pytest tests/test_adk_evaluator.py tests/test_evaluator.py -q`
- Real-model evaluation: not_run, a scripted model measured the call counts and no provider was called
- `DeepevalEvaluator`: not_run, not examined
- UI validation: not_applicable, no frontend change
