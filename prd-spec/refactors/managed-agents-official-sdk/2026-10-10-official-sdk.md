# Official Anthropic SDK adapter verification

[中文版](2026-10-10-official-sdk.zh.md)

Change ID: `managed-agents-official-sdk`. Created/revised: 2026-10-10. Status: implemented.

## Background and scope

The original example's Dockerfile installed an adjacent custom Anthropic wheel to
provide `anthropic.lib.environments._dispatcher`. The migrated Worker already uses
published `anthropic==1.3.0` and a VeADK dispatcher. Its locked wheel hash matches
[PyPI](https://pypi.org/project/anthropic/1.3.0/). The user's follow-up asks to research
and implement the same function using the official SDK, optionally through Python
extension techniques. The approved scope includes image publication, local Kubernetes deployment and real
SDK acceptance in the specified namespace. Cloud AgentKit deployment remains excluded.

## Requirements and design

- `FR-1`: install the unchanged official SDK; the image checks its installed Python
  files against distribution RECORD hashes to reject modified package contents.
- `FR-2`: environment polling uses generated `work.with_raw_response.poll`, preserving
  HTTP 204 handling, strict Work validation, scoped auth, routing headers, leases,
  cancellation and readiness. Account `/v1/model-work/poll` is a VeADK gateway extension
  accessed with documented `client.get`; it is not an official Claude endpoint.
- `FR-3`: tests exercise VeADK's real scoped-client adapter rather than importing the
  SDK's private auth helper. Parent auth is removed; transport identity injection
  preserves Runtime gateway auth alongside Work lease auth.
- `FR-4`: build guides explain the original dependency, official installation, extension
  boundaries and remaining version-sensitive helpers.

Use composition. Official EnvironmentWorker has no arbitrary handler callback;
subclassing it would override private execution and SessionToolRunner behavior. Global
monkeypatching would affect unrelated clients. Public headers/http-client/raw-response
options provide the required transport extension without altering SDK code.
`ToolError` uses its public tools export. Published internal `_download_and_extract`
remains necessary because public download_session_skills silently skips failed pinned
Skills; this dependency is documented and covered by real SDK archive tests.

## Tasks and acceptance

| Task | Requirement | Files and verification |
| --- | --- | --- |
| `T-1` | `FR-1` | Docker SDK-integrity checker, image installation gate, tamper regression |
| `T-2` | `FR-2`, `FR-3` | dispatcher and identity protocol tests: public generated poll, empty/malformed responses, all-request headers and credential refresh |
| `T-3` | `FR-4` | paired build guides, runtime spec, this design; link and whitespace checks |

`AC-1`: unmodified installed SDK passes and modified SDK files fail integrity checks.
`AC-2`: targeted Runtime/MPA tests pass on locked official SDK, including Python 3.10.
`AC-3`: pre-commit and Docker build/isolated imports pass; no private wheel input,
version churn, SDK source overwrite or cloud changes. Cloud E2E remains not_run.

## Review and risk

The user explicitly requested research followed by implementation, continuing the
approved official-SDK migration approach. Direct review confirms public raw-response
support and composition feasibility; no review-spec skill is available. Update both
runtime component languages for FR-1/FR-2. Other resource and model contracts are
unchanged. SDK-internal helper names remain version-sensitive; locked versions and
integration tests bound this risk. RECORD verification detects modified installed
files, while the lock's official artifact hash verifies origin during installation.
Neither verifies server behavior. No live credential or endpoint is recorded.


Independent review also found that the official internal cleanup helper logs raw exceptions. `T-2` includes a local cleanup adapter using close/aclose and additive context-manager exits; it reports only exception types and propagates cancellation. Regression tests verify cleanup continues without exposing exception text.

## Delivery evidence


- **pass (2026-10-10):** 213 targeted Python 3.12 tests; official-SDK adapter
  subset 109 tests on Python 3.10, plus 41 credential tests after the local-key
  opt-in addition. All-file pre-commit passed.
- **pass:** published immutable Worker image; official SDK 1.3.0 RECORD matches
  all 1389 Python files. Running Kubernetes Worker source hashes match the local
  dispatcher/worker/identity/Session implementation. Worker is Ready in the
  authorized namespace. The official SDK 1.5.0 acceptance client is installed
  separately, preserving AKX's existing version.
- **pass:** the user approved deleting one historical Key. Archived/zero-active state was
  revalidated before deletion; a dedicated Environment Key was created. Official SDK 1.5
  passed two real model turns, six native tools, pinned Skill instructions, cross-Worker
  continuation and stopped model Work; test Session/Agent/Skill cleanup passed. Official
  tool config type discriminators now work with legacy name fallback; real-SDK regression
  coverage is included in 213 targeted tests. Public APIG, cloud Identity and remote tools
  remain outside this acceptance.


## Authorized local Kubernetes deployment

The user subsequently authorized deployment in `ma-infra-stg-zn-ppe`, deployment
assets in `/home/mofanke/gitcode/akx`, and final acceptance with official Anthropic
SDK. `T-4` adds a dedicated environment-scoped Worker and a new VKE template;
existing Helm revisions/images are saved and existing backend/frontend/cloud
Runtime defaults remain intact. Official SDK creates isolated resources and checks
real Work polling, model/tool events, two-turn continuation and pinned Skills.

Current workers require Session model Identity even for local VKE. Add opt-in
`MANAGED_AGENT_MODEL_CREDENTIAL_SOURCE=environment` for non-AgentKit Sessions
without a provider reference, reading only `MODEL_AGENT_API_KEY`. The default
`session` retains Identity behavior; AgentKit or any explicit provider reference
always uses Session Identity without fallback. Unknown sources/missing keys fail
closed. A dedicated Kubernetes Secret provides the local model key; no credentials
enter repository files. This acceptance proves configured model credentials, not
cloud Runtime Identity. Rollback deletes the new Worker and restores only any
explicitly changed config; test Agents/Sessions/Skills are cleaned up.
