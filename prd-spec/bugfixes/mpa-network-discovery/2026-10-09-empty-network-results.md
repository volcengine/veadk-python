# Empty managed network discovery results

[中文版](2026-10-09-empty-network-results.zh.md)

Change ID: mpa-network-discovery. Created/revised: 2026-10-09. Status: implemented.

## Evidence and scope

Read-only diagnosis confirmed an Available managed VPC, no subnet creation intent, and a successful DescribeSubnets response serialized by the installed SDK as `subnets=None, total_count=0`. `NetworkCloud._list` rejects this as invalid before the provisioner can create its first subnet. This follows the [ownership-description fix](../mpa-network-description/2026-10-09-valid-network-marker.md).

Goal: normalize a confirmed empty provider result and resume preparation in the recorded VPC. Non-goals: changes to UI, IAM, PG, APIG, Runtime/chat, resource naming or automatic deletion. No cloud writes, task retries, database edits, commits or deployment performed by this change's verification.

## Requirements and scenarios

- FR-1: On the first discovery page, a null or absent `vpcs`/`subnets` collection with an integer `total_count=0` is an empty list. Existing list responses retain their behavior.
- FR-2: Reject null/missing collections without an explicit integer zero, scalar collections even with zero, and a null collection on subsequent pages. Boolean/string/float counts are not integer evidence. Do not convert provider errors to empty results.
- FR-3: A recorded managed VPC with this empty subnet result proceeds to create one subnet. A second ensure reuses the same VPC and subnet; durable intents, ownership validation and uncertain-outcome duplicate prevention remain unchanged.

Given a fresh VPC and zero subnets, discovery returns empty and creation continues. Given incomplete/malformed discovery or a provider permission error, preparation fails. Given a paginated nonempty result, a later null/zero response cannot discard earlier rows.

## Design and contract impact

`managed/network_cloud.py` owns normalization in `_list`; both discovery methods use it. Normalize only `items is None`, `type(total_count) is int`, zero count, and first page. All existing pagination limits, errors, credentials and request parameters remain unchanged. No schema, public signature, permissions or configuration changes; no new dependencies. The [Studio creation contract](../../../specs/studio-mpa-creation/README.md) owns empty/error distinctions; [Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md) references it. Caller retry retains the existing VPC; no migration or cleanup is needed.

Concurrency, cancellation and timeout handling are unchanged because only a successfully returned discovery payload is normalized. Never reinterpret a failed request or unknown Create outcome as an empty discovery.

## Tasks, tests and acceptance

| Requirement | Task | Acceptance |
| --- | --- | --- |
| FR-1 | T-1: failing installed-SDK and absent-collection tests, then normalization | AC-1: DescribeVpcs/DescribeSubnets zero-result responses return empty |
| FR-2 | T-2: negative and pagination regressions | AC-2: malformed responses/errors still fail; populated pages are retained |
| FR-3 | T-3: isolated provisioner/adapter integration | AC-3: resume recorded VPC, create one subnet, reuse on repeat |
| FR-1–3 | T-4: bilingual review and verification | AC-4: affected tests, Ruff/Pyright, secret/diff/document checks pass |

Commands: `uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py -q`; changed-file Ruff/Pyright and pre-commit. Real cloud retry is a separate user-submitted smoke; no live success is claimed from fakes.

## Review, approval and risks

Direct design review performed because review-spec is unavailable. Reviewed provider serialization, null-versus-invalid distinctions, pagination consistency, ownership, recovery, credential redaction and bilingual equivalence. No blocking findings. User approval: “帮我改正” after the diagnosed null/zero response and proposed empty-result correction. Risk: null responses lacking integer zero still fail deliberately; this is not a general suppression of malformed discovery. Unrelated working-tree changes remain preserved.

## Verification and delivery

2026-10-09, working tree based on `ef0ad519`. Test-first, implementation and verification results are recorded below. Frontend/build/browser/generated assets and sidecar checks are not_applicable: those contracts are unchanged. Full-repository/all-files commit checks and live cloud smoke are not_run: no commit or live retry is requested in this change.


Results for the scoped correction:

- pass: before implementation, the four installed-SDK/absent-collection regressions failed with `Network discovery returned invalid results`; after completing the durable VPC test fixture, the orchestration regression also failed at the same discovery error.
- pass: network adapter/provisioner suite: 88 passed. Final managed/Runtime command above: 534 passed, 5 existing dependency deprecation warnings, 23.67 seconds.
- pass: final isolated resume regression: 1 passed after a test-only parameter-name correction; production behavior was unchanged.
- pass: `uvx --from ruff==0.11.12 ruff check` and `ruff format --check` for `network_cloud.py`, `test_deployment_network_cloud.py`, `test_deployment_network.py`; `uvx pyright --pythonpath .venv/bin/python` on the same files: 0 errors, 0 warnings. The initial fake/adapter method parameter-name mismatch was fixed without a type suppression.
- pass: `uv run --extra dev pre-commit run --files` for the three Python files and six bilingual documents: Ruff/check/format and hardcoded-secret scan passed. YAML scan not_applicable (no YAML changes). Paired FR/T/AC identifiers, all relative document link targets and `git diff --check` passed.

Implementation review: only a confirmed first-page empty result is normalized. Rejected null/nonzero and later-page responses do not reach resource creation. Existing list responses, provider-error propagation, record reuse and persist-before-create recovery are covered. AC-1–4 are met by isolated tests and final document/secret checks. No successful live retry is claimed.
