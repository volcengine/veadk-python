# Signed TOS URL Skill Download

## Background and Evidence

`VeSkillRegistry.get_skill()` refreshes Skill Space metadata with `load_skills_from_cloud()`, selects a remote skill, and materializes it with `materialize_remote_skill()`. For legacy AgentKit Skill Spaces, `_build_skill_from_space_item()` maps `TosPath` to `Skill.path` and `BucketName` to `Skill.bucket_name`.

Today `_download_legacy_skill_space_skill()` assumes `Skill.path` is a TOS object key such as `skills/<skill_id>/<version>/<name>.zip`. If the cloud API returns a complete HTTPS pre-signed TOS URL in `TosPath`, the non-Vestack branch passes that URL to `VeTOS.download()` as an object key, while the Vestack branch tries to parse it as a legacy object path.

## Goals

- Load a normal Skill Space skill when `TosPath` is a complete pre-signed HTTPS TOS ZIP URL.
- Preserve existing behavior for object-key `TosPath` values.
- Reuse the existing archive safety checks: streaming size limit, zip validation, safe extraction, and ADK `SKILL.md` load validation.
- Keep signed URL content out of error messages and source fixtures except redacted, synthetic test URLs.

## Non-Goals

- Do not change Harness `tos_public_url` validation. User-provided Harness public URLs must continue to reject TOS credential query parameters.
- Do not change private TOS directory loading through `tos://bucket/prefix/`.
- Do not add new cloud APIs or change `ListSkillsBySpaceId`.

## Scenarios

1. `ListSkillsBySpaceId` returns `BucketName` plus object-key `TosPath`; the SDK TOS download path remains unchanged.
2. `ListSkillsBySpaceId` returns `TosPath=https://bucket.tos-cn-beijing.volces.com/...zip?X-Tos-Signature=...`; the materializer downloads that URL directly and loads the Skill.
3. A signed URL redirects to a non-TOS host or returns a non-ZIP payload; materialization fails closed.

## Requirements

- Detect signed HTTPS TOS ZIP URLs only for cloud-returned Skill Space metadata.
- Accept TOS signing query keys for this cloud-returned path.
- Require HTTPS, a TOS endpoint host, a `.zip` path, and no username/password in the URL.
- Stream downloads with the same 64 MiB archive limit used by public TOS ZIPs.
- Preserve cache key behavior by using `version_id` when present; otherwise the metadata digest includes the URL.

## Design

Add a materializer branch for cloud-returned signed TOS ZIP URLs. `_build_skill_from_space_item()` will classify a `TosPath` that is an HTTPS TOS ZIP URL as a signed URL source. `materialize_remote_skill()` will then route that source through a signed-URL downloader instead of the legacy TOS object-key downloader.

The signed-URL downloader should share the public TOS ZIP streaming implementation, but use a validator that allows TOS signature query keys. Harness `tos_public_url` continues to use the stricter public validator that rejects credential query keys.

## Affected Files

- `veadk/skills/utils.py`
- `veadk/skills/materializer.py`
- `tests/skills/test_adk_skill_materializer.py`

## Component Contract Assessment

No component spec update is required. The external Skill Space metadata contract already allows `TosPath` to carry the location returned by AgentKit; this change only fixes local materialization of one returned shape. Public Python APIs, Harness request schema, and user-facing configuration remain unchanged.

## Tasks

- Add a failing regression test for a cloud-returned pre-signed TOS URL in `TosPath`.
- Classify signed TOS URL metadata during Skill construction.
- Add a materializer download path that allows signed query keys only for cloud-returned TOS URLs.
- Run targeted Skill tests and whitespace checks.

## Tests

- `uv run --extra dev pytest tests/skills/test_adk_skill_materializer.py`
- `uv run --extra dev pytest tests/skills/test_adk_skill_registry.py tests/skills/test_skill_space_policy.py`
- `git diff --check`

## Risks

- Signed URLs contain credentials in query parameters; logs and error messages must not echo raw URLs.
- URL cache keys may change when a refreshed signed URL changes. This is acceptable when no stable version is provided; `version_id` remains authoritative when available.

## Acceptance Criteria

- A Skill Space skill whose `TosPath` is a pre-signed HTTPS TOS ZIP URL downloads and loads successfully.
- Existing object-key Skill Space downloads still pass.
- Harness `tos_public_url` tests that reject signed query credentials still pass.
- No real credentials or production signed URLs are committed.

## Design Review

Direct review completed because no repository-local `review-spec` skill is available in this checkout. The design is bounded to cloud-returned metadata, preserves Harness user-input validation, fails closed on unsafe URL shapes, and has targeted regression coverage.
