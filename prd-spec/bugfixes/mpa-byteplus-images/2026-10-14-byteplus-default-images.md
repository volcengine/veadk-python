# Use BytePlus-hosted defaults for managed MPA images

[中文版](2026-10-14-byteplus-default-images.zh.md)

- ID: `mpa-byteplus-default-images`
- Created/revised: 2026-10-14
- Status: implemented
- Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md)

## Background and evidence

BytePlus managed creation currently inherits the Volcengine Beijing Runtime and Worker image references unless trusted environment overrides are set. Live BytePlus creation reached `CreateTool` and failed with `provider_error`; the persisted task snapshot confirmed that it still selected the Beijing `cr.volces.com` Worker image. Public BytePlus repositories have now been prepared and anonymous manifest reads verified for:

- `agentkit-platform-3001037806-ap-southeast-1.cr.bytepluses.com/mpa/mpa_agent:latest`
- `agentkit-platform-3001037806-ap-southeast-1.cr.bytepluses.com/mpa/mpa_codex_worker:latest`

The verified manifests had digests `sha256:1db0caa3...` and `sha256:b9ea5f49...` respectively. The Worker image was built from `agentkit-mpa-codex-worker` `master@7aa11f0`.

## Goals and non-goals

Make new built-in BytePlus Studio requests select the BytePlus-hosted Runtime and Worker images by default. Preserve trusted server overrides and all domestic defaults.

Do not mutate or retry existing tasks, change image validation, pin defaults to digests, rebuild images, alter cloud resources, change browser inputs, or change CLI/YAML profiles.

## Scenarios and requirements

- FR-1: `load_studio_profile(provider="byteplus")` defaults Runtime and Worker images to the two `ap-southeast-1.cr.bytepluses.com` latest references above.
- FR-2: Nonempty `VEADK_MPA_BYTEPLUS_RUNTIME_IMAGE` and `VEADK_MPA_BYTEPLUS_WORKER_IMAGE` remain higher-priority trusted overrides.
- FR-3: `load_studio_profile()` for Volcengine retains the Beijing Runtime and Worker defaults exactly.
- FR-4: Existing submitted tasks retain their persisted image snapshots. A new request after Studio restart is required to receive changed defaults.

## Design and affected files

Define the BytePlus registry once in the BytePlus branch of `studio_profile_values` and use its two image references as the fallback values behind the existing environment overrides. No frontend or HTTP shape changes are required because config/task APIs already expose and snapshot the resolved nonsecret defaults.

Affected files:

- `veadk/integrations/mpa/managed/studio_profile.py`
- `tests/integrations/mpa_managed/test_byteplus.py`
- paired Studio MPA component contract
- this paired bugfix design

## Tasks, tests and acceptance

| Requirement | Task | Acceptance |
| --- | --- | --- |
| FR-1/FR-3 | Add a failing provider-isolation assertion, then change the defaults | BytePlus selects the overseas references and Volcengine remains unchanged |
| FR-2 | Retain and run override coverage | Both trusted overrides still win |
| FR-4 | Update the paired contract and verify task semantics | Documentation states that only new task snapshots receive the defaults |

Verification: targeted BytePlus pytest, changed-file Ruff and Pyright, paired-language/link review, and `git diff --check`. Frontend build and browser checks are not applicable because no frontend or HTTP contract changes.

## Risks and review

The `latest` tags are mutable by design and match the requested Studio convention; the verified digests are evidence, not pinned runtime values. Public manifest readability does not prove AgentKit `CreateTool` or Runtime application readiness, so a new isolated BytePlus creation remains required. Existing failed tasks cannot adopt the new images because changing their snapshot would violate retry identity.

Direct design review (`review-spec` unavailable): scope, provider isolation, override precedence, task immutability, security, compatibility, testability and bilingual equivalence checked; no blockers. The user approved the preceding plan with “帮我改下”. No commit, push or cloud deployment is authorized by this approval.

## Verification record

2026-10-14 working diff:

- pass: the new default assertion failed against the old implementation with both images still resolving to the Beijing registry.
- pass: `uv run --extra dev pytest tests/integrations/mpa_managed/test_byteplus.py tests/integrations/mpa_managed/test_tasks.py tests/integrations/mpa_managed/test_studio_shared_resources.py -q` — 47 passed, with two upstream deprecation warnings.
- pass: Ruff 0.11.12 check/format and Pyright for the changed Python files; `git diff --check`; paired links and semantics reviewed.
- pass: direct profile evaluation selected both BytePlus-hosted references while retaining both Beijing domestic references.
- pass: public BytePlus image manifests were readable before implementation.
- pass: after restarting Studio, live task `209b63d5-04ec-490f-95d8-41b7931891f4` persisted both BytePlus-hosted defaults and completed Worker creation/readiness. The task later failed independently at automatic OpenViking creation with `openvikingCreateUnknown`; Runtime creation was not reached.
- not_applicable: frontend build/browser checks; no frontend or HTTP contract changed.
