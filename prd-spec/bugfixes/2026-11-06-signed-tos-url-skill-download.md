# Signed TOS URL Skill Download

## Background and Evidence

`VeSkillRegistry.get_skill()` refreshes Skill Space metadata with `load_skills_from_cloud()`, selects a remote skill, and materializes it with `materialize_remote_skill()`. For legacy AgentKit Skill Spaces, `_build_skill_from_space_item()` maps `TosPath` to `Skill.path` and `BucketName` to `Skill.bucket_name`.

Today `_download_legacy_skill_space_skill()` assumes `Skill.path` is a TOS object key such as `skills/<skill_id>/<version>/<name>.zip`. If the cloud API returns a complete HTTPS pre-signed TOS URL in `TosPath`, the non-Vestack branch passes that URL to `VeTOS.download()` as an object key, while the Vestack branch tries to parse it as a legacy object path. Real validation against `ss-yey3lbgruoq7vcs7xlp4` also showed the object-key path can return `403 AccessDenied` for sharing-bucket skills, while `GenTempTosObjectDownloadUrlSharing` returns a usable signed URL for the same skill.

## Goals

- Load a normal Skill Space skill when `TosPath` is a complete pre-signed HTTPS TOS ZIP URL.
- Preserve direct object-key downloads when they work, and fall back to a sharing signed URL when they are denied.
- Reuse the existing archive safety checks: streaming size limit, zip validation, safe extraction, and ADK `SKILL.md` load validation.
- Keep signed URL content out of error messages and source fixtures except redacted, synthetic test URLs.

## Non-Goals

- Do not change Harness `tos_public_url` validation. User-provided Harness public URLs must continue to reject TOS credential query parameters.
- Do not change private TOS directory loading through `tos://bucket/prefix/`.
- Do not change `ListSkillsBySpaceId`.

## Scenarios

1. `ListSkillsBySpaceId` returns `BucketName` plus object-key `TosPath`; direct SDK TOS download still succeeds for readable objects.
2. `ListSkillsBySpaceId` returns object-key `TosPath`, but direct SDK TOS download is denied; the materializer requests `GenTempTosObjectDownloadUrlSharing`, downloads `Result.SignedUrl`, and loads the Skill.
3. `ListSkillsBySpaceId` returns `TosPath=https://bucket.tos-cn-beijing.volces.com/...zip?X-Tos-Signature=...`; the materializer downloads that URL directly and loads the Skill.
4. A signed URL redirects to a non-TOS host or returns a non-ZIP payload; materialization fails closed.

## Requirements

- Detect signed HTTPS TOS ZIP URLs only for cloud-returned Skill Space metadata.
- Accept TOS signing query keys for this cloud-returned path.
- Require HTTPS, a TOS endpoint host, a `.zip` path, and no username/password in the URL.
- Stream downloads with the same 64 MiB archive limit used by public TOS ZIPs.
- Preserve cache key behavior by using `version_id` when present; otherwise the metadata digest includes the URL.
- Do not log raw signed URLs or credential-bearing query strings during fallback.

## Design

Add a materializer branch for cloud-returned signed TOS ZIP URLs. `_build_skill_from_space_item()` will classify a `TosPath` that is an HTTPS TOS ZIP URL as a signed URL source. `materialize_remote_skill()` will then route that source through a signed-URL downloader instead of the legacy TOS object-key downloader.

The signed-URL downloader should share the public TOS ZIP streaming implementation, but use a validator that allows TOS signature query keys. Harness `tos_public_url` continues to use the stricter public validator that rejects credential query keys.

For legacy object-key metadata, keep the current direct `VeTOS.download()` attempt first. If that attempt fails or raises, request `GenTempTosObjectDownloadUrlSharing` with the skill id and version, read `Result.SignedUrl`, and pass it through the same signed-URL downloader.

## Affected Files

- `veadk/skills/utils.py`
- `veadk/skills/materializer.py`
- `tests/skills/test_adk_skill_materializer.py`

## Component Contract Assessment

No component spec update is required. The external Skill Space metadata contract already allows `TosPath` to carry the location returned by AgentKit; this change only fixes local materialization of one returned shape. Public Python APIs, Harness request schema, and user-facing configuration remain unchanged.

## Tasks

- Add a failing regression test for a cloud-returned pre-signed TOS URL in `TosPath`.
- Add a failing regression test for object-key `TosPath` falling back to a sharing signed URL after direct TOS download denial.
- Classify signed TOS URL metadata during Skill construction.
- Add a materializer download path that allows signed query keys only for cloud-returned TOS URLs.
- Reuse that signed URL download path for sharing signed URL fallback.
- Run targeted Skill tests and whitespace checks.

## Tests

- `uv run --extra dev pytest tests/skills/test_adk_skill_materializer.py`
- `uv run --extra dev pytest tests/skills/test_adk_skill_registry.py tests/skills/test_skill_space_policy.py`
- `git diff --check`

## Risks

- Signed URLs contain credentials in query parameters; logs and error messages must not echo raw URLs.
- URL cache keys may change when a refreshed signed URL changes. This is acceptable when no stable version is provided; `version_id` remains authoritative when available.
- Sharing signed URL generation may fail for skills with incomplete backend metadata; such skills still fail closed and should be diagnosed separately.

## Acceptance Criteria

- A Skill Space skill whose `TosPath` is a pre-signed HTTPS TOS ZIP URL downloads and loads successfully.
- Existing readable object-key Skill Space downloads still pass.
- Object-key Skill Space downloads that are denied by direct TOS access can load through the sharing signed URL fallback.
- Harness `tos_public_url` tests that reject signed query credentials still pass.
- No real credentials or production signed URLs are committed.

## Design Review

Direct review completed because no repository-local `review-spec` skill is available in this checkout. The design is bounded to cloud-returned metadata, preserves Harness user-input validation, fails closed on unsafe URL shapes, and has targeted regression coverage.
