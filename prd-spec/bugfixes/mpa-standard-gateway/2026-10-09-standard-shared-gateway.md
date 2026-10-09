# Standard shared APIG creation

[中文版](2026-10-09-standard-shared-gateway.zh.md)

Change ID: mpa-standard-gateway. Created/revised: 2026-10-09. Status: implemented.

## Evidence, goals and boundaries

Read-only investigation confirmed a successful historical shared MPA gateway is standard, with two 1c2g nodes, small_1 CLB, public/private networking and traffic billing. The new account has exhausted its Serverless gateway count while standard count has headroom. Current managed creation hardcodes serverless and prepares only one subnet. The provider [CreateGateway contract](https://docs.volcengine.com/docs/apig/CreateGateway?lang=en) requires at least two subnets in different zones. [GetGatewayAvailableZones](https://docs.volcengine.com/docs/apig/GetGatewayAvailableZones-QuerythecurrentRegionAvailabilityZonelist?lang=zh) supplies APIG-supported zones, which can differ from ECS zones.

Goal: new managed gateways use the working standard configuration, prepare an appropriate cross-zone network and recover definite quota rejection. Non-goals: frontend changes, general-agent chat, moving existing Runtimes, deleting resources, switching cloud accounts, copying old-account resource IDs, upgrading images or automatically increasing quota. Real creation remains a separate user submission. Existing standard/serverless registrations and explicit adoption retain compatibility.

## Requirements and scenarios

- FR-1: CreateGateway uses standard, Replicas=2, InstanceSpecCode=1c2g, CLBSpecCode=small_1, both public/private enabled and traffic billing. Reject fewer than two or duplicate subnet IDs before dispatch.
- FR-2: For a new gateway without registered/adopted ID, query APIG zones and prepare two available same-VPC subnets in distinct supported zones under the existing account lock. Reuse eligible subnets first, create only missing companions with nonoverlapping CIDRs. Include ready GetSubnet results in CIDR reservations when DescribeSubnets lags. Preserve VPC and all existing resources.
- FR-3: Each companion subnet has its own durable intent/token/dispatch flag and stable scope/zone name. Timeouts/cancellation/unknown results require discovery before another Create; retries retain payload and token. Conflicts, malformed zones, ownership drift, CIDR exhaustion and fewer than two APIG zones fail closed. A recorded pending companion remains authoritative even if another suitable subnet appears.
- FR-4: Existing gateway reuse/adoption does not require new zone discovery or network changes. Existing Runtime network payloads stay unchanged; new Runtime payloads use the prepared gateway subnet selection. Management registry records are the source of truth.
- FR-5: ExceededQuota is a definite provider rejection for gateway and IM creation; save create_requested/im_create_requested=false and allow same-agent retry after correction. Timeout/internal/unknown errors retain duplicate protection. A historical unknown flag is not automatically cleared. A one-off recovery may clear only the audited rejected intent under the shared lock after checking the exact scope/VPC/name and absence of the gateway; it must not delete resources or reset arbitrary intents.
- FR-6: Deployment IAM policy includes the read-only apig:GetGatewayAvailableZones action. Runtime role policy and other permissions remain unchanged. No credentials or provider payloads enter user output, source or reports.

Scenarios: fresh shared setup creates two cross-zone subnets and one standard gateway/IM service; a recorded single-subnet VPC adds only its missing companion; separate agents reuse the same admin registry; a lost companion Create response resumes by exact name; quota rejection is recoverable; an uncertain gateway outcome still blocks duplication; existing registered gateways/Runtimes retain their network.

## Design and contract impact

`gateway_cloud.py` owns the standard request and APIG zone adapter. `network.py` adds a gateway-specific preparation method using the same entry lock and persists companion intents inside gateway_subnet_intents keyed by zone. Existing single-subnet preparation remains unchanged for independent Runtime callers. `service.py` invokes companion preparation only when no gateway is registered/adopted, passes gateway subnets independently, and only changes a fresh Runtime's template network. `gateway.py` classifies the definite quota rejection. `frontend_deploy_policy.py` grants the one new read action. No public HTTP/API/CLI fields, configuration or tables change; the JSON registry gains optional companion intents. All provider calls refresh and verify credentials.

Owner contracts: [Studio creation](../../../specs/studio-mpa-creation/README.md) and [Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md). Update both languages and managed module READMEs. Frontend/browser/assets/sidecar gates are not_applicable because their interfaces/behavior are unchanged. Isolated tests cover actual request shape, orchestration and recovery; live provisioning is reported separately.

## Tasks and acceptance

| Requirement | Task | Acceptance |
| --- | --- | --- |
| FR-1, FR-6 | T-1: failing adapter/policy regressions then standard request/zones | AC-1: standard payload and minimum IDs, strict zones, deployment permission |
| FR-2–4 | T-2: failing companion/reuse/cancellation tests then durable preparation and entry-point wiring | AC-2: new setup/one-subnet recovery/repeated agents, no existing Runtime changes or duplicate subnet creation |
| FR-5 | T-3: failing quota recovery tests then definite-error handling | AC-3: gateway/IM quota retries allowed, unknown outcomes remain blocked |
| FR-1–6 | T-4: docs, targeted/regression tests and review | AC-4: affected tests, Ruff/Pyright, secret/diff/bilingual/link checks pass |

Commands: `uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/cli/test_frontend_deploy_iam.py -q`; changed-file Ruff/Pyright/pre-commit. No commit, push, deployment, destructive cleanup or live creation is part of verification.

## Review, approval and risks

Direct review because review-spec is unavailable: scoped ownership, cross-zone requirements, independent intents, locks, partial failures, unchanged Runtime compatibility, permissions and bilingual equivalence reviewed. User approved the standard gateway/two-zone/IM/registry/retry solution with “帮我改”. The new read action needs deployment permission; empty/failed zone lookup is not silently substituted with ECS results. New standard resources have their provider billing; quota/availability errors can still occur and remain explicit failures. Pending historical flags remain conservative until audited operator recovery. No design blockers remain.

## Verification and delivery

2026-10-09, tested working tree based on ef0ad519 plus this uncommitted gateway correction and preceding approved account/IAM/network fixes; unrelated user changes preserved. T-1–T-4 and AC-1–AC-4 are satisfied for isolated implementation verification.

- pass: test-first adapter/quota baseline (13 expected failures, 14 passes), companion/policy baseline (12 expected failures, 64 passes), and delayed-list CIDR regression (one expected failure), then implementation.
- pass: `uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/cli/test_frontend_deploy_iam.py -q --tb=short`: 578 passed, five existing dependency deprecation warnings. Covers standard payload, distinct APIG zones, reuse across agents, cancellation/lost-response recovery, authoritative pending intent, ownership/zone/account drift, CIDR exhaustion and delayed lists, quota recovery and unchanged existing Runtime network.
- pass: `uvx --from ruff==0.11.12 ruff check` and `ruff format --check` for the 12 affected Python source/test files; `uvx pyright --pythonpath .venv/bin/python` for gateway_cloud.py, gateway.py, network.py, service.py and frontend_deploy_policy.py (zero errors).
- pass: `uv run --extra dev pre-commit run --files <affected source/tests/docs>`: Ruff check/format and hardcoded secret scan. Concrete-YAML secret gate not_applicable (no YAML changes).
- pass: paired-language, relative-path/reference and diff whitespace checks; direct implementation review found no remaining blockers. Preserve scope, registry locks and Runtime network compatibility; cancellation does not roll back resources.
- pass (live data repair only): under the shared account/region lock, reverified deployment STS identity, failed local task/no active creation, exact provider ExceededQuota audit and absence of the scoped gateway; cleared only that rejected create_requested flag and verified readback. No cloud resource was created/deleted and no other record was changed. Unknown historical intents have no automatic bypass.
- not_run: real standard gateway/IM/Runtime creation; the user must submit after restarting local Studio (or redeploying cloud Studio). Provider quota, availability and permissions remain live checks.
- not_run: full repository parallel regression and all-files commit gate; verification covered affected creation/provisioning/CLI regressions. The earlier broad run has unrelated SDK dependency/collection failures recorded in the IAM design. No commit was requested.
- not_applicable: frontend/browser/build/assets/sidecar gates because no frontend or event/chat interface changed.

