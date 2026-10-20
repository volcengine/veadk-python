# Preserve managed Runtime recovery across subnet ordering changes

[中文版](2026-10-09-subnet-order.zh.md)

- Change ID: `mpa-subnet-order`
- Created/revised: 2026-10-09
- Status: implemented
- Contracts: [Studio creation](../../../specs/studio-mpa-creation/README.md), [Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md).

## Background and scope

Read-only diagnosis found a Runtime with platform Ready and HTTP 200 readiness, but its creation task failed immediately after V1 became Ready. The shared registry and Runtime contained the same two subnets in opposite order. validate_runtime compares SubnetIds as an ordered list and raises a migration error. An isolated synthetic reproduction confirmed this cause. AccountNetworkProvisioner.ensure repeats that ordered comparison on resume. Adopting the platform order also changes the existing request hash on retry.

Goals: ignore provider-only subnet permutations at both guards and resume the original deployment without replacing resources. Non-goals: cloud resource writes during verification, registry repairs, broad diagnostics changes, UI/chat changes, permissions, image changes or bypassing actual network drift.

## Scenarios and requirements

- FR-1 / AC-1: Given identical unique nonempty subnet lists in different orders, initial Runtime validation and existing Runtime network preparation accept them. VpcId and EnableSharedInternetAccess remain exact comparisons; added, removed, substituted, duplicated or malformed subnet selections remain errors.
- FR-2 / AC-2: Retry retains the caller's requested subnet order, or the registered order when its membership equals the current Runtime selection. Otherwise retain the current selection, never adopt a different registered membership. This preserves already persisted request hashes and ClientTokens for unchanged inputs. Do not sort or rewrite old deployment records or relax changed-input conflict checks.
- FR-3 / AC-3: Simulated full creation and recovery of a pending V1 deployment with reordered provider metadata finish environment/key finalization and readiness, retain the Runtime/Skill Space/database identifiers and create no duplicate resources. Caller inputs and provider objects remain unchanged.

## Design and contract impact

Share a small subnet-membership comparator in managed/network.py, validating list shape, nonempty string IDs and uniqueness before set comparison. Use it only for SubnetIds in network.py and runtime.py; other immutable fields remain strict. For resume, retain explicit requested ordering. With no explicit selection, prefer the shared registry ordering only if it has identical members to the active Runtime; otherwise preserve the active per-agent selection. This addresses both migration guards and retry hash stability without changing hashing format or persistent schema.

Studio creation owns this network/recovery contract; Runtime provisioning references it. No API/configuration/schema/dependency/permission changes; general agents, CLI legacy provisioning, async deadlines, locks, cancellation, terminal handling and credential boundaries remain unchanged. Malformed lists are rejected rather than converted to sets blindly. Reuse existing fake cloud/registry lifecycle tests; no frontend or generated assets are affected.

## Tasks and affected files

- T-1 (FR-1/AC-1): failing tests in test_deployment_network.py and test_runtime_deployment_edges.py; update managed/network.py and managed/runtime.py.
- T-2 (FR-2, FR-3/AC-2, AC-3): regression for a persisted pending V1 with original hash, reversed metadata, same-ID retry and no duplicates; preserve explicit order and registered order in network preparation.
- T-3: reconcile paired Studio/Runtime specs and managed README guides, run targeted/broader affected provisioning tests, Ruff/Pyright, scoped pre-commit/secret scan and document link/whitespace checks.

## Risks and acceptance verification

Blind set conversion could hide duplicate or invalid IDs: validate before comparison and cover negatives. Returning provider order could strand old pending hashes: exercise an already persisted original request through the production retry path. Registry membership can differ for explicit per-agent overrides: do not substitute the shared default when members differ. Simulated tests do not prove cloud publication; live retry remains an operator action after the fix. No unreviewed cloud mutation is needed to deliver this code repair.

## Review and approval

User approved the preceding proposed repair with “修复下” on 2026-10-09. The implementation detail preserving hash order is necessary to deliver that same-ID recovery requirement. review-spec is unavailable in the skill catalog; direct review before production/test edits checked bilingual equivalence, contract ownership, error boundaries, compatibility, security, testability and retained concurrency/deadline behavior. No blockers. Tested scope will be ef0ad519 plus this fix and the pre-existing uncommitted MPA changes. Results will be recorded below; full commit synchronization/gates await commit authorization.

## Results (2026-10-09)

- pass: T-1/T-2 and AC-1/AC-2/AC-3. The corrected fail-first fixture produced six failures from ordered comparison/request-hash drift, one existing-success boundary passed (103 deselected), before implementation.
- pass: `uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/cli/test_frontend_deploy_iam.py -q --tb=short` — 625 passed, five existing deprecation warnings. Includes fresh/pending lifecycle, finalization, unchanged hash/token, negative drift and malformed-list coverage.
- pass: `uvx --from ruff==0.11.12 ruff check` and `uvx pyright --pythonpath .venv/bin/python` on network.py, runtime.py, test_deployment_network.py and test_runtime_deployment_edges.py. Initial Pyright findings were repaired (list narrowing and conditional test variables); final result zero errors.
- pass: direct implementation review verifies unchanged request hashing, no mutation of caller/provider selections, same-membership-only registry ordering preference, no relaxed resource ownership or real-drift checks, and unchanged async lifecycle/cleanup.
- blocked: fresh live read-only Runtime/registry verification returned ApiError; no provider payload or credentials were printed. The earlier diagnostic snapshot and synthetic regression establish the ordering defect, but no successful post-fix cloud read or retry is claimed.
- pass: scoped pre-commit (Ruff, formatting and hardcoded-secret detection), paired-language relative links/identifiers and diff whitespace. Formatting initially changed two test files; checks were rerun after formatting. YAML scan not_applicable, no YAML changed.
- not_run: cloud deployment retry/full live publication; this verification performs no cloud writes. Full SDK-wide regression is not_run because the affected managed/legacy deployment suite covers the scoped integration change. UI/build/browser/generated artifacts and Codex/harness process smoke are not_applicable: no changes to those paths. Full commit synchronization/all-files gates await an authorized commit. T-3 complete; no deferred implementation scope.
