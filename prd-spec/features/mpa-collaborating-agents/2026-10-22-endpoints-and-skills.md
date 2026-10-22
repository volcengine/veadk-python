# A2A Runtime endpoints and Agent details

[中文版](2026-10-22-endpoints-and-skills.zh.md)

ID: mpa-a2a-endpoints-and-skills. Created/revised: 2026-10-22. Status: implemented.
Related: [component](../../../specs/mpa-collaborating-agents/README.md), [member actions](2026-10-22-member-actions.md), [authentication fix](../../bugfixes/mpa-a2a-space-deletion/2026-10-22-runtime-auth.md).

## Background and evidence

Registration currently always offers public/private without reading actual Runtime addresses. The details projection omits AgentCard service address and skills. The user requested console-aligned options, concrete addresses, and skills in View, and approved: “按此实现”. Official [registration](https://docs.volcengine.com/docs/86681/2229304), [service address](https://docs.volcengine.com/docs/86681/2248691), and [GetA2aAgent](https://docs.volcengine.com/docs/86681/2249666) describe Runtime-specific public/private service addresses and AgentCard metadata. The deployed MPA registry already parses AgentCard as JSON string/object, although the public Get documentation's examples are inconsistent. Missing/unparseable metadata must therefore be explicit rather than invented.

## Goals, scenarios and requirements

FR-1: Selecting or entering a source Runtime reads its authorized network configurations in the target region. Show only configured public/private endpoints, with localized Public address/Private address and concrete address. Select the previous type if still available, otherwise the first available type. Switching Runtime immediately invalidates old choices; loading, empty and read error remain distinct. Provide retry and abort stale requests on Runtime/region/source changes or unmount. Do not submit without a current matching endpoint. Registration payload remains RuntimeId plus NetworkType; never accept a browser URL as the registration destination.
FR-2: View shows the effective AgentCard service address and skill name, description, tags and examples as plain text. Service URL is distinct from the AgentCard document URL. Distinguish known empty skills from unavailable/malformed metadata. Preserve basic detail if optional Card metadata is unavailable. Keep bounded projection, identity checks and read retry.
FR-3: Strip URL query/fragment and reject credentials, non-HTTP(S), malformed ports, control characters and oversized URLs. Never return raw Cards, security schemes, headers, keys, provider reasons or environments; do not fetch Card URLs. Bound Card input to 128 KiB, skills to 100 with an explicit truncation notice, each ID/name/description to 256/512/4096 characters, tags/examples to 20 entries of 128/1024 characters. Invalid skill metadata is unavailable, not an empty list. Use existing form controls, ModalButton, typography and scrolling; long addresses/text wrap at narrow widths.

## Design, contracts and compatibility

GET /web/a2a-runtime-endpoints/{sourceRuntimeId}?targetRuntimeId=...&region=... requires Studio administrator plus authorization for both Runtime IDs. Return {runtimeId, endpoints:[{networkType:public|private,url}]}, at most two entries, one per configured type, with explicit empty response when no safe usable endpoint exists. No key is exposed. Add this dedicated client/read rather than expanding the shared Runtime list/detail DTO. The provider remains responsible for registration eligibility and races.

GET /web/a2a-agents/{agentId} adds serviceAddress:string|null, skills:Array<{id,name,description,tags:string[],examples:string[]}>|null, skillsTruncated:boolean. Additive fields preserve existing callers. Null means unavailable; [] means confirmed empty. Read metadata only on View, not on DELETE validation, so a malformed optional Card never changes deregistration eligibility. No schema/data migration, dependency, SDK public signature, Runtime deployment, dispatch, Harness or IAM change.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1 | T-1: endpoint route/client/parser, then registration state and selection | AC-1: public-only/private-only/both/no endpoint, retry, stale response, invalid manual ID and submit gates work; no credential leaks | Python endpoint auth/projection tests; frontend/tests/collaboratingAgents.test.tsx |
| FR-2 | T-2: bounded Card projection and detail display | AC-2: Runtime/Standard details show address and skills; empty/unavailable differ; plain text and identity checks retained | Python metadata tests; UI modal tests; browser |
| FR-3 | T-3: security/compatibility, docs and release assets | AC-3: unsafe URLs and raw credentials excluded, malformed/oversized metadata explicit; keyboard/narrow/loading/error/cancel behavior retained | affected Python tests, Ruff/Pyright; npm test/build/check:i18n/test:webui-assets; tsc; browser; secret scan; git diff --check |

## Review, approval, risks and verification

No review-spec skill is available; direct review covered bilingual equivalence, API ownership, authorization, security, failures, compatibility, cancellation and tests. No blockers. User confirmed the scoped plan before production/test edits. Existing UI controls and alerts satisfy the layout/feedback baseline; no restyling or new dependencies. Runtime endpoint reads may fail independently of list reads and must remain visible/retryable. Safe addresses intentionally omit query/fragment secrets. No automatic writes or live cloud registrations/deletions during verification. Real end-to-end cloud success is not established by mocked tests.

Date: 2026-10-22. Scope: current uncommitted A2A diff above HEAD 9ab0ef2d. Final checks are recorded in the delivery evidence. Commit, push and cloud deployment are outside authorization.


## Delivery evidence (2026-10-22)

Implemented the approved scope against the existing uncommitted A2A changes above 9ab0ef2d. Regression-first evidence: 22 selected Python and 8 UI cases failed before implementation. Review resolved stale endpoint selection, safe optional Card projection, browser credential override, and separate read-auth versus cloud-permission failures. No unresolved in-scope findings.

| Check | Result | Evidence / limits |
| --- | --- | --- |
| `uv run --extra dev pytest tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py tests/cli/test_frontend_runtime_proxy.py tests/test_mpa_collaborator_proxy_policy.py -q` | pass | 227 passed (6 warnings); MockTransport exercises actual Studio mounting and the shared helper, including successful simulated deletion and zero cloud calls on binding-auth refusal. |
| `npm --prefix frontend test` | pass | 1389 Node tests and 183 Vitest tests across 11 files, including 36 collaborating-Agent cases. |
| `npm --prefix frontend run build` | pass | Current packaged WebUI rebuilt; existing large-chunk advisory remains. |
| `npm --prefix frontend run check:i18n`; `npm --prefix frontend run test:webui-assets` | pass | 2 locales / 22 namespaces; 114 packaged files / 351 internal references. |
| `frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json` | pass | No diagnostics. |
| `uv run --extra dev pre-commit run ruff-check --files ...`; `ruff-format` with the same files | pass | a2a_center.py, test_a2a_center_actions.py, test_frontend_runtime_proxy.py, cli_frontend.py. Formatter changes were reconciled before final tests. |
| Pyright using existing adjacent-repository executable, `--pythonpath .venv/bin/python frontend/server/a2a_center.py tests/cli/test_a2a_center_actions.py` | pass | 0 errors/warnings; no dependency installation or global configuration changes. |
| Whole-file CLI/proxy-test Pyright | fail (baseline) | 37 CLI and 20 existing proxy-test diagnostics. Re-running with only this change's helper block and proxy tests removed produced identical diagnostic-message multisets (57 each), establishing no added diagnostics. Temporary comparison files removed. |
| Browser | pass | Real browser with isolated mocked fetch: endpoint descriptions and full selected URL, mouse and keyboard switching, cancel/focus return, details/skills, 390px iframe and internal scrolling, and actionable preflight-auth alert. Fixtures and Vite process removed. |
| Live local read integration | pass | Current localhost Studio exposes the new endpoint route, serves the matching built app, and returns HTTP 200 for both real source Runtime endpoint reads and both registry detail reads. Observed one Runtime with public/private and another with public only; effective addresses and skills matched the console records. No cloud write performed. |
| Scoped gitleaks with repository config; document links/pairs/IDs; `git diff --check` | pass | No leaked secrets found; existing scanner exclusions retained, no bypass. |
| Full Python regression, commit-time all-files pre-commit, live cloud writes | not_run | Changes are scoped to A2A routes and a path-filtered existing auth policy; affected proxy/API consumers tested. No commit/push authorized, so branch synchronization and commit gates were not invoked. Real cloud deletion/registration is not proven by mocks or read-only checks. |

T-1/T-2/T-3 and AC-1/AC-2/AC-3 completed. Current Studio was restarted externally during the task; this agent did not interrupt it. New backend and built app are active; refreshing the browser loads the new UI. No commit, push or Runtime deployment. Retained all unrelated user changes. Subsequent name investigation used read-only live values and did not alter AgentCard or registration names.
