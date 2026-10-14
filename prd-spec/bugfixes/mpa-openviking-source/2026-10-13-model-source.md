# OpenViking model source and rejected-intent recovery

[中文版](2026-10-13-model-source.zh.md)

Date: 2026-10-13. Status: implemented; live acceptance pending. Base: `71175c68636dc5b951e9804eb292d85402511e68` plus the uncommitted automatic OV feature.

## Background and scope
A user-created Beijing MPA reached OV after Worker preparation and was rejected by CreateOpenVikingCollection with InvalidParameter: unsupported model source empty. Cloud audit confirms an explicit rejection, not an uncertain create. Omitting Credentials is therefore insufficient. The reference library reports Source volcengine and versioned model identifiers even though its console custom-credential list is empty. Official create documentation requires Source and EndpointID for volcengine and conditionally ApiKey.
Goal: keep automatic Beijing OV, with explicit model source/identifiers and the already resolved deployment-account Ark key. Do not add UI inputs, create model endpoints, alter BytePlus/general agents, update existing OV credentials, or execute a paid cloud retry without separate user action/authorization.

## Requirements and design
- FR-1: VLM Credentials uses Source `volcengine`, EndpointID `doubao-seed-2-0-lite-260428`; Embedding uses Source `volcengine`, EndpointID `doubao-embedding-vision-251215`. Keep the existing model names/versions. These identifiers come from the reference library; acceptance for a new API library remains subject to live verification.
- FR-2: The adapter receives the resolved Ark model key separately, validates it locally, and attaches ApiKey to a copied wire payload only. Nonsecret intents contain Source/EndpointID but no model key. Registry, task results, diagnostics and repr must exclude both Ark and OV keys. Fresh Studio uses its account-discovered key; explicitly opted-in CLI can use its configured model key, including template MODEL_AGENT_API_KEY. Missing/masked/invalid keys fail before dispatch with the existing configuration error. Registered-library retry reads OV key again without resending model credentials.
- FR-3: Upgrade the complete matching previous no-Credentials intent only when there is no OV ID, no pending Runtime operation, and openviking_create_requested is explicitly false. This is the durable state after a proven rejection. Unknown/in-flight creates, changed project/name/model/description and registered IDs remain fail-closed; do not erase bindings or reset flags to work around failures. A recovered request retains agent/library name and records the corrected nonsecret intent before dispatch.
- FR-4: Validate Source/EndpointID in Get results before reuse, excluding returned key values from storage. Keep lock, timeout, cancellation, one-shot create and readiness behavior. Create requests get at most one dispatch; no extra paid fallback.

## Affected files and tasks
OpenViking adapter/provisioner, MPA service wiring, focused OV/service tests, bilingual creation contract and operator/design docs. No frontend or Runtime protocol change; the same four OV env vars are already supported. T-1 regression tests for wire credentials/no secret persistence; T-2 source validation and safe rejected-intent recovery; T-3 wire existing model key; T-4 run affected creation regression, Ruff/Pyright, secret scan and paired-document checks.

## Acceptance, risks and review
AC-1 wire credentials are explicit and secret-free intent remains stable; AC-2 same failed agent can recover only after proven rejection; AC-3 changed/unknown/registered requests never create a duplicate; AC-4 BytePlus/manual/general paths unchanged and checks recorded. Endpoint aliases and model/key authorization still require live acceptance; default model access may require account enablement. No claim of successful cloud creation until confirmed.
Direct design review (review-spec unavailable) covers compatibility, secret lifetimes, copied payload, ownership, rejection vs uncertainty, cancellation/deadlines and bilingual equivalence. User requested the missing-source fix on 2026-10-13; the concrete plan reuses the existing Ark key and preserves the failed task identity. No commit, push or cloud retry authorized.

## Verification
Test-first regression: 27 failed / 2 passed before implementation (new keyword and explicit Credentials were absent). After implementation, OV/service tests passed 192 cases. Final broad creation/RBAC regression passed 1,087 cases with two workers. Read-only Get of the reference library confirms the exact Source and both EndpointID values; this is not new-library creation acceptance.

| Gate (2026-10-13, uncommitted correction) | Result |
| --- | --- |
| `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed/test_openviking.py tests/integrations/mpa_managed/test_service.py` | pass: 192 |
| `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/frontend/server/mpa/test_runtime_profile_routes.py tests/cli/test_studio_rbac.py` | pass: 1,087 |
| `uvx ruff==0.11.12 check <four-correction-python-files>` and `format --check` | pass |
| `uvx pyright --pythonpath .venv/bin/python <four-correction-python-files>` | pass: 0 errors/warnings |
| `uv run --extra dev pre-commit run gitleaks --files <changed-files>` | pass: source/tests/docs/built assets |
| Paired docs, links/identifiers and `git diff --check` | pass |
| Frontend rebuild/browser | not_applicable: correction has no frontend changes; initial auto-OV frontend gates remain recorded in the feature PRD |
| Corrected live create / key retrieval / Runtime readiness | not_run: user can retry the same failed task; no automatic cloud write performed |
| Full-repository pre-commit / commit / push | not_run: no commit requested |

Review: wire payload is copied; credentials never enter the registry intent; source/endpoint readback excludes secret fields; registered/ambiguous/changed requests cannot be upgraded. AC-1–AC-4 implementation/offline checks complete; corrected cloud acceptance remains pending. Each retry starts a new runner process, so this child-process correction is loaded on retry without changing the existing browser request.
