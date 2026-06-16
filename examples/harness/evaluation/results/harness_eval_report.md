# Harness Evaluation Report

Generated at: `2026-06-12T08:46:09.937706+00:00`

## Summary

| Metric | Baseline | Harness | Delta |
| --- | ---: | ---: | ---: |
| Result verifier accuracy | 20.0% | 100.0% | +80.0 pp |
| Unsafe false-accept rate | 100.0% | 0.0% | -100.0 pp |
| Unsafe detection recall | 0.0% | 100.0% | +100.0 pp |
| Context quality score | 0.0% | 100.0% | +100.0 pp |

## Scenario Lift

| Scenario | Harness module | Baseline behavior | Harness behavior | Lift shown |
| --- | --- | --- | --- | --- |
| RAG memory freshness | ResultVerifier | trusted | blocked | unsafe answer blocked |
| Tool failure claimed as success | ResultVerifier | trusted | blocked | unsafe answer blocked |
| Security over-blocking of allowed tools | ResultVerifier | trusted | blocked | unsafe answer blocked |
| Model runtime parameter drift | ResultVerifier | trusted | blocked | unsafe answer blocked |
| Channel and cron context anchoring | ContextEngine | anchor=False; control_noise=True; evidence=False | anchor=True; control_noise=False; evidence=False | anchor_contract, no_control_pollution |
| RAG evidence beats stale memory | ContextEngine | anchor=False; control_noise=False; evidence=False | anchor=True; control_noise=False; evidence=True | anchor_contract, evidence_visible, evidence_before_history |

## ResultVerifier Cases

| Scenario | Case | Expected done | Baseline done | Harness done | Failure mode |
| --- | --- | ---: | ---: | ---: | --- |
| Core guardrail: fabricated source URL | fabricated-url | False | True | False | fabricated_url |
| Core guardrail: current fact without evidence | no-evidence-current-fact | False | True | False | missing_evidence |
| Core guardrail: unsupported date fact | unsupported-date | False | True | False | unsupported_key_fact |
| Core guardrail: requested JSON contract | format-mismatch-json | False | True | False | format_mismatch |
| Core guardrail: grounded policy answer | grounded-policy | True | True | True | safe |
| Core guardrail: grounded sourced list | grounded-list | True | True | True | safe |
| RAG memory freshness | production-rag-stale-memory | False | True | False | production_missing_current_kb_evidence |
| Tool failure claimed as success | production-tool-failed-but-passed | False | True | False | production_failed_tool_claimed_success |
| Security over-blocking of allowed tools | production-security-blocked-but-passed | False | True | False | production_security_failed_tool_claimed_success |
| Model runtime parameter drift | production-model-runtime-token-mismatch | False | True | False | production_unsupported_runtime_parameter |

## ContextEngine Cases

| Scenario | Case | Checks | Baseline pass details | Harness pass details |
| --- | --- | --- | --- | --- |
| Core context: follow-up task anchor | follow-up-anchor | anchor_contract, acceptance_visible | anchor_contract=False; control_polluted=False; budget=True; evidence=False | anchor_contract=True; control_polluted=False; budget=True; evidence=False |
| Core context: control message filtering | control-message-filter | no_control_pollution | anchor_contract=False; control_polluted=True; budget=True; evidence=False | anchor_contract=True; control_polluted=False; budget=True; evidence=False |
| Core context: prompt budget control | budgeted-follow-up | budget_compliant, anchor_contract | anchor_contract=False; control_polluted=False; budget=False; evidence=False | anchor_contract=True; control_polluted=False; budget=True; evidence=False |
| Core context: evidence before history | evidence-first | evidence_visible, evidence_before_history | anchor_contract=False; control_polluted=False; budget=True; evidence=False | anchor_contract=True; control_polluted=False; budget=True; evidence=True |
| Channel and cron context anchoring | production-group-chat-anchor | anchor_contract, no_control_pollution | anchor_contract=False; control_polluted=True; budget=True; evidence=False | anchor_contract=True; control_polluted=False; budget=True; evidence=False |
| RAG evidence beats stale memory | production-rag-evidence-first | anchor_contract, evidence_visible, evidence_before_history | anchor_contract=False; control_polluted=False; budget=True; evidence=False | anchor_contract=True; control_polluted=False; budget=True; evidence=True |

## Method

- Baseline trusts every non-empty final answer and uses raw history as context.
- Harness treatment uses the example ContextEngine and ResultVerifier modules.
- No LLM call is made; the benchmark isolates deterministic Harness guarantees.
