# Harness TOS Skills

[中文版](2026-10-12-harness-tos-skills.zh.md)

## Metadata

| Field | Value |
| --- | --- |
| Change ID | `harness-tos-skills` |
| Created | 2026-10-12 |
| Status | implemented |
| Related specs | No component spec update; this extends the existing Harness selected-skill request contract without changing ownership boundaries. |

## Background And Evidence

Harness can already load SkillHub skills and Skill Space skills. Skill Space loading eventually downloads TOS-backed Skill archives through the existing materializer, but callers cannot directly provide an object-storage Skill directory.

The requested behavior should align with AWS AgentCore Harness S3 skills: one object-storage URI points to one Skill directory containing `SKILL.md`; multiple Skills are represented as multiple selected-skill entries.

## Goals

- Add `source="tos"` to `HarnessSelectedSkill`.
- Support current-account TOS directories via Runtime cloud identity.
- Support public readable TOS zip URLs without requiring AK/SK.
- Preserve existing SkillHub and Skill Space behavior.

## Non-Goals

- No parent-directory auto-discovery of multiple Skills.
- No plaintext AK/SK in Harness requests.
- No cross-account private TOS credential reference in this MVP.

## Requirements

| ID | Requirement |
| --- | --- |
| FR-1 | A TOS selected Skill with `tos_url="tos://bucket/path/to/skill/"` loads exactly one Skill directory and requires `SKILL.md` or `skill.md` at that URL root. |
| FR-2 | Multiple TOS Skills are loaded by multiple `selected_skills` entries. |
| FR-3 | A public TOS zip URL can load one Skill archive. |
| FR-4 | Empty/bucket-root TOS URLs, parent directories, unsupported public URLs, non-TOS hosts, credential-bearing public URLs, and redirects to non-TOS hosts fail closed. |
| FR-5 | TOS download failures and invalid Skill directories fail the whole SkillToolset build. |
| FR-6 | Public TOS zip downloads, public zip extraction, and private TOS directory downloads enforce bounded file/object count and byte limits before Skill loading. |

## Design

`HarnessSelectedSkill.source` accepts `tos` with either:

```python
HarnessSelectedSkill(source="tos", tos_url="tos://bucket/skills/reporting/", region="cn-beijing")
HarnessSelectedSkill(source="tos", tos_public_url="https://bucket.tos-cn-beijing.volces.com/skills/reporting.zip")
```

Multiple Skills are expressed as multiple entries:

```python
selected_skills=[
    HarnessSelectedSkill(source="tos", tos_url="tos://bucket/skills/reporting/", region="cn-beijing"),
    HarnessSelectedSkill(source="tos", tos_url="tos://bucket/skills/search/", region="cn-beijing"),
]
```

Harness serializes these as internal refs and dispatches them in `build_skill_toolset`. TOS selected Skills use `tos_url` and `tos_public_url` as the only locator fields. The materializer parses `tos://` URLs, downloads one directory through `VeTOS`, validates path containment, requires root-level `SKILL.md` or `skill.md`, and loads with ADK. A URL pointing at a parent folder containing child Skills is rejected instead of selecting one child. Public URLs must not contain userinfo or TOS signature query credentials. They are streamed as zip archives from validated TOS hosts, every redirect hop must also target a TOS host before it is requested, and the existing safe zip extraction path enforces expanded file count and uncompressed byte limits for public TOS archives.

Rejected TOS refs are redacted when wrapped into Harness skill-load errors, so invalid userinfo or signature query values are not returned to callers or written by the Harness error path.

## Tasks

| ID | Task |
| --- | --- |
| T-1 | Add schema fields and validation for TOS selected Skills. |
| T-2 | Add materializer helpers for TOS directory and public zip sources, including strict root-manifest validation and resource limits. |
| T-3 | Wire Harness SkillToolset building to TOS refs. |
| T-4 | Add focused contract and materializer tests. |

## Verification

| Requirement | Command | Result |
| --- | --- | --- |
| FR-1..FR-6 | `uv run --extra dev pytest tests/skills/test_adk_skill_materializer.py tests/test_ve_tos.py::test_download_can_propagate_tos_error tests/test_ve_tos.py::test_download_rejects_object_over_byte_limit tests/test_ve_tos.py::test_download_directory_rejects_too_many_objects tests/test_ve_tos.py::test_download_directory_rejects_total_bytes_from_listing -q` | pass, 30 passed on 2026-10-12 |
| FR-4..FR-5 | `uv run --extra dev pytest tests/cloud/test_harness_app_contract.py::TestHarnessOverrides::test_tos_selected_skill_rejects_public_url_userinfo tests/cloud/test_harness_app_contract.py::TestHarnessOverrides::test_tos_selected_skill_rejects_public_url_signature_query tests/cloud/test_harness_skill_download.py::test_build_skill_toolset_redacts_tos_ref_on_error -q` | pass, 3 passed on 2026-10-13 |
| FR-1..FR-6 | `uv run --extra dev pytest tests/cloud/test_harness_skill_download.py::test_build_skill_toolset_loads_tos_skill_uri tests/cloud/test_harness_skill_download.py::test_build_skill_toolset_loads_multiple_tos_entries -q` | pass, 2 passed on 2026-10-12 |
| FR-1..FR-6 | `uv run --extra dev ruff check veadk/skills/materializer.py veadk/integrations/ve_tos/ve_tos.py tests/skills/test_adk_skill_materializer.py tests/test_ve_tos.py` | pass on 2026-10-12 |
| FR-1..FR-6 | `uv run --extra dev pre-commit run --all-files` | pass on 2026-10-12 |
| FR-1..FR-6 | `git diff --check` | pass on 2026-10-12 |
| FR-1..FR-6 | `uv run --extra dev pytest tests/skills/test_adk_skill_materializer.py tests/test_ve_tos.py -q` | fail, existing environment limitation: four async tests in `tests/test_ve_tos.py` need an async pytest plugin; TOS-focused tests passed. |

## Risks

- Real TOS IAM behavior requires cloud smoke validation outside the offline unit tests.
- Public directory URLs remain excluded because object storage does not provide a stable generic HTTP directory listing contract.
