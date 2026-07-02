# Harness Model Evaluation Report

Generated at: `2026-06-12T08:17:47.829143+00:00`
Model: `<configured-model>`
API base: `<configured-api-base>`

## Summary

Cases: `3` (answerable `2`, unsupported `1`).

| Metric | Baseline | Harness | Delta |
| --- | ---: | ---: | ---: |
| Trust decision accuracy | 66.7% | 100.0% | +33.3 pp |
| Unsupported false-accept rate | 100.0% | 0.0% | -100.0 pp |
| Answerable verified pass rate | - | 100.0% | +100.0 pp |
| Answerable receipt coverage | - | 100.0% | +100.0 pp |
| Unsupported request block rate | - | 100.0% | +100.0 pp |

## Scenario Matrix

| Scenario | Harness capability | Expected trust | Baseline runtime | Harness runtime | Receipts | Lift shown |
| --- | --- | ---: | --- | --- | ---: | --- |
| RAG memory freshness with source grounding | ResultVerifier evidence gate | True | trusted | trusted | 2 | trusted with receipts |
| Tool evidence and receipt coverage | Tool receipt + source verification | True | trusted | trusted | 2 | trusted with receipts |
| No-evidence hallucination suppression | ResultVerifier unsupported-answer block | False | trusted | blocked | 0 | trust decision corrected |

## Case Detail

| Scenario | Case | Scenario type | Baseline post-hoc verifier | Harness missing requirements | Harness tools |
| --- | --- | --- | --- | --- | --- |
| RAG memory freshness with source grounding | production-rag-policy-source | answerable_with_tools | blocked | - | public_web_lookup, sample_policy_lookup |
| Tool evidence and receipt coverage | production-tool-evidence-receipts | answerable_with_tools | blocked | - | public_web_lookup, sample_policy_lookup |
| No-evidence hallucination suppression | production-no-evidence-source-claim | unsupported_without_evidence | blocked | External/current factual task has no tool evidence or source receipt. | - |

## Method

- This report contains sanitized model outputs but no secrets.
- Baseline output is checked post-hoc only for evaluation; baseline runtime does not enforce that check.
- Harness runtime records receipts and enforces `VerificationReport.done` as the trust gate.
