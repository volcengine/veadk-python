# Studio Skill document editing

[中文](README.zh.md) · [Design](../../prd-spec/features/mpa-agent-info-rail/2026-09-18-mpa-agent-info-rail.md)

## Ownership and interface

The existing Skill management identity resolver and version repository own authorization and publication. The MPA rail supplies exact region/space/skill IDs; the editor never chooses another space or changes a Runtime binding.

GET `/web/skill-management/spaces/{space_id}/skills/{skill_id}/document?region=...` returns `{content, baseVersion, canUpdate}` for the latest visible version. PUT on that path accepts `{content, baseVersion}` and creates/publishes a new native version in the selected space using existing version-upload behavior. Content is limited to 262144 characters; baseVersion to 64 characters; neither may be empty. Ownership is checked server-side. Shared and review spaces remain read-only even for admins; other personal spaces follow existing owner/admin rules.

## Integrity and concurrency

Only the validated archive's root (or single wrapper's) SKILL.md is replaced. All other members, binary bytes and attributes are retained. Existing ZIP limits and frontmatter validation apply; changing the Skill name is rejected with 422. The editor receives escaped plain text, never executable document markup.

Save validates baseVersion before reading the source archive and again inside the existing process-local upload lock. A stale version returns `SKILL_DOCUMENT_CONFLICT` (409) before cloud mutation. External writers can still race after the check because the provider has no compare-and-swap. This is not a distributed lock. Save failures/pending outcomes do not mean rollback; preserve edits and advise checking the current version before retrying.

## UI lifecycle

Loading/error/retry, read-only, unsaved-change confirmation, IME-safe Escape, keyboard focus trapping/restoration and disabled controls during save are explicit states. Duplicate saves are locked. Unmount aborts browser requests and ignores late results; it cannot roll back an already accepted server publication. Saving refreshes the bound list. Runtime cache refresh/new sessions may be needed before execution uses the new version. No automatic live edit is part of local verification.

## Verification

Backend document tests cover identity, read/write permissions, name preservation, binary/mode preservation, and version conflicts. Component tests cover read-only, read retry, save failure with retained draft, duplicate saves, unmount cancellation, and Escape/IME. See the bilingual design for dated results and browser limitations.
