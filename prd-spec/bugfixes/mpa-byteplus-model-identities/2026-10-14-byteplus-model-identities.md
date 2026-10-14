# Use BytePlus Model Identities for Managed OpenViking

[中文版](2026-10-14-byteplus-model-identities.zh.md)

- Change ID: `mpa-byteplus-model-identities`
- Created/Revised: 2026-10-14
- Status: implemented
- Related spec: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md)

## Background and evidence

BytePlus managed OpenViking currently defaults `OV_VLM_ENDPOINT_ID` and
`OV_EMBEDDING_ENDPOINT_ID` to domestic `doubao-*` identifiers. Read-only Ark
lookups in account `3001037806`, region `ap-southeast-1`, returned
`NotFound.EndpointId` for those identifiers. A live OpenViking resource accepted
the configuration but semantic ingestion timed out with embedding work repeatedly
requeued and no vectors produced.

BytePlus Ark `CreateEndpoint` dry runs rejected the domestic model names and
accepted `seed-2-0-lite` version `260428` and
`skylark-embedding-vision` version `251215`. The user approved retaining the
current API Key plus model-identity binding instead of adopting Coding Plan or
creating account-specific `ep-*` resources.

## Goals and non-goals

Goals:

- Default BytePlus VLM identity to `seed-2-0-lite-260428`.
- Default BytePlus embedding identity to
  `skylark-embedding-vision-251215`.
- Preserve API Key injection, environment overrides, validation, redaction,
  retry, and persisted nonsecret intent.

Non-goals:

- Do not change domestic OpenViking defaults.
- Do not create, update, or delete Ark endpoints or OpenViking resources.
- Do not adopt Coding Plan or change data-plane base URLs.
- Do not migrate existing tasks or OpenViking resources.

## Scenarios and requirements

- `FR-1`: Given a new BytePlus automatic OpenViking request without overrides,
  its VLM and embedding credentials use the two BytePlus model identities above.
- `FR-2`: `OV_VLM_ENDPOINT_ID` and `OV_EMBEDDING_ENDPOINT_ID` continue to
  override defaults and use the existing validation.
- `FR-3`: The resolved model API Key is attached only to the copied wire request
  and is never persisted.
- `FR-4`: Volcengine requests and existing persisted requests remain unchanged.

## Design and contract impact

Change only the fallback values returned by `byteplus_model_endpoints()`. The
existing request builder, API Key injection, registry comparison, and cloud
adapter remain unchanged. Existing requests retain their persisted identities;
changing their inputs continues to produce a configuration conflict. New tasks
created after Studio restart receive the new defaults.

Security, permissions, concurrency, state, and public Python APIs are unchanged.
The maintained Studio MPA creation contract must record the new defaults.

## Affected files and tasks

- `T-1` / `FR-1..4`: update BytePlus regression fixtures and assertions first.
- `T-2` / `FR-1..2`: update `byteplus_model_endpoints()`.
- `T-3` / `FR-1..4`: synchronize the bilingual Studio MPA creation spec.
- `T-4`: run targeted tests, Ruff, Pyright, bilingual checks, and diff checks.

## Verification and acceptance

| Requirement | Acceptance criterion | Verification | Result |
| --- | --- | --- | --- |
| `FR-1` | Default request uses both BytePlus identities | OpenViking and service pytest suite | `pass`: 240 tests |
| `FR-2` | Explicit overrides and invalid-value checks remain covered | Same pytest command | `pass` |
| `FR-3` | API Key remains wire-only | Same pytest command | `pass` |
| `FR-4` | Domestic code path is unchanged | Diff review and existing service tests | `pass` |
| Quality | Changed Python passes static checks | Ruff `0.11.12`, Pyright, and `git diff --check` | `pass`: 0 errors |

Acceptance criteria:

- `AC-1`: new BytePlus automatic requests persist the approved model identities.
- `AC-2`: the wire request contains the API Key while registry state does not.
- `AC-3`: environment overrides retain precedence.
- `AC-4`: no cloud resource is mutated by implementation verification.

## Risks and recovery

Provider acceptance at collection creation does not prove successful inference;
a new isolated live resource is required for end-to-end semantic verification.
Existing misconfigured resources are not mutated. Operators can restore the old
behavior with both environment overrides if rollback is required.

## Review and delivery record

Direct review found no API, credential, state-machine, or domestic compatibility
change beyond the BytePlus defaults. The model identities were verified by
BytePlus Ark dry run. The user approved the exact values and retained API Key
binding on 2026-10-14. Implementation completed on 2026-10-14. Verification:

- `uv run --extra dev pytest tests/integrations/mpa_managed/test_openviking.py tests/integrations/mpa_managed/test_openviking_byteplus.py tests/integrations/mpa_managed/test_openviking_diagnostics.py tests/integrations/mpa_managed/test_service.py -q`: `pass`, 240 tests.
- Ruff `0.11.12` check/format and Pyright for the changed Python files: `pass`.
- `git diff --check` for the scoped files: `pass`.
- Live creation with the corrected identities: `not_run`; it requires a new paid OpenViking resource and explicit execution after Studio restart.
