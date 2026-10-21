# Studio read-only latest tag resolution

[中文版](2026-10-21-readonly-tag-resolution.zh.md)

- Change ID: `studio-latest-image-refresh`; revised 2026-10-21.
- Status: approved for implementation/deployment/live verification by the user's instruction to change and verify the read-only matching scheme.
- Supersedes the registry-writing part of [the original snapshot design](2026-10-20-latest-image-snapshots.md). Existing deployment selections and historical evidence remain valid.
- Component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-1/3/6/8/9.

## Evidence and scope

An anonymous, credential-free probe of both built-in public registries confirmed that Agent and Worker repositories support repository-scoped anonymous pull tokens, complete tag listing, and exact manifest-digest matching. BP matches include `master-a72afa274fe5-20261020` and `master-31fc42b4c521-20261021-1205`; domestic matches include `master-d8665d03578a-20261016` and `master-a63685214d07-20261016`. This proves read access and matching at probe time, not Runtime adoption or a registry-enforced immutability policy.

The original implementation requires source-registry write permission and therefore is unsuitable for ordinary users of platform-owned public repositories. Replace publication with anonymous, read-only selection of an existing tag in the same repository. Do not introduce CI, image copies, dependencies, frontend fields, IAM changes, or changes to existing MPAs/standalone CLI. Authenticated private `latest` repositories are outside this public-discovery contract; explicit fixed tags retain their behavior.

## Requirements and design

- **RO-1:** Read latest, verify raw Docker/OCI manifest or index bytes against `Docker-Content-Digest`, and list existing tags using only HTTPS GET and anonymous `repository:<repo>:pull` tokens. Never read cloud credentials, netrc, or Docker configuration; disable ambient requests authentication. Authentication challenges must use the same registry host/HTTPS/default port without userinfo or redirects.
- **RO-2:** Read all bounded tag pages before selection. Accept only valid tag names. Prefer an already-published `mpa-sha256-<digest>` tag, then consider other non-latest tags in descending lexical order. Verify candidate manifest bytes; a removed candidate (404) may be skipped, but invalid/authentication/transport responses fail. Use the first exact digest match. A tag's non-overwrite policy is the publisher's responsibility; a name alone does not prove immutability.
- **RO-3:** Fail explicitly if no existing version tag matches; never publish a tag or silently fall back to latest. A publisher must retain a corresponding non-overwritten version tag whenever latest changes. Selection means the latest observed at initial resolution; movement afterward does not change that deployment intent.
- **RO-4:** Keep native `image_snapshots.requested/selected` and both-image persistence under the existing lock. New selection accepts any validated same-repository non-latest tag. Existing digest-named selections remain compatible. Retry reads only the saved tag and verifies its digest; changed/missing saved content fails, never reselects. Keep old unfinished-intent rejection and standalone CLI/fixed-tag compatibility.
- **RO-5:** Bound each response to 1 MiB, enumeration to 20 pages / 1000 tag entries, and resolution to a 120-second budget checked before HTTP calls and while consuming bodies (an in-flight read can run until its bounded read timeout). Per-call connect/read limits remain 10/30 seconds or the remaining budget. Pagination must remain on the exact same repository tags-list endpoint, have only `n`/`last` parameters, no credentials/fragments, and no cycles; malformed or cross-origin links fail. Cancellation retains no partial persisted selection; the existing subprocess supervisor handles termination. Errors remain sanitized.

The owning production module remains `managed/image_snapshot.py` for compatibility; service integration and native schema do not change. Update its protocol tests, bilingual component/operator docs, the frontend operator note, and PR description. The initial snapshot design is retained as historical evidence, explicitly superseded.

## Review and approval

No review-spec skill is available; reviewed directly before code changes: public/ordinary-user permission boundary, anonymous token scope, host/path/pagination validation, raw digest integrity, malformed/large responses, deadlines, cancellation, mutable/deleted tags, legacy saved selections, retry idempotency, CLI isolation, test mapping, and English/Chinese equivalence. User approval covers implementation, update of PR #1178, BP Studio deployment, and a new isolated MPA test. No additional permission expansion or repository writes are part of discovery.

## Tasks, acceptance and verification

| Requirement | Task / acceptance | Verification | Result |
| --- | --- | --- | --- |
| RO-1/2/3/5 | Anonymous exact-match selection, strict bounded GET-only protocol, explicit failures | First write failing regression; fake HTTP protocol/security/deadline cases; live anonymous resolution | pass; evidence below |
| RO-4 | Persist both selections under lock; retry old/new saved tags; preserve CLI and fixed tags | Managed service/integration and CLI regressions | pass; evidence below |
| All | Incremental coverage above 95%; quality/security gates and synchronized docs | Focused branch coverage, managed/CLI regression, changed-file Ruff/Pyright, all-files pre-commit, frontend test/build | pass; evidence below |
| All | Deploy exact tested source and create a fresh Studio MPA | Supported Studio update, deployed module hashes, UI success, native ready state and selected tags, application readiness, actual Worker source/image ID, bounded completed Worker task | pending |

## Risks and recovery

Read access and tag policies may change. Missing matching tags or registry access must produce a safe diagnostic rather than create a stale deployment. The finite enumeration/time budgets may reject a very large or slow repository. Tags are not cryptographically immutable; publisher discipline remains necessary and retry revalidation detects changes. Public network egress is required. Preserve failed cloud resources and the original persisted intent; rollback Studio through its supported release path if necessary. Do not claim cache invalidation or a fix for the earlier unrelated completion exception. Leave live outcomes unverified until observed.

## 2026-10-21 local and anonymous live verification

The first three GET-only regressions failed against the previous credential-dependent implementation before production changes. The updated suite has **93 passed**; resolver line and branch coverage is **100%**. Relative to origin/main, all **173/173 added executable production lines** (resolver plus service integration) are covered. Coverage execution preloads `pydantic_settings` and SDK Runtime types before pytest to avoid the already-established upstream import-identity issue; no dependency or business-code workaround was introduced.

- pass: `.venv/bin/python -m pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q`, **1266 passed**.
- pass: frontend tests **118 passed**, production build, changed-file Pyright (0 errors), all-files pre-commit including Ruff/format/secret scanning, and `git diff --check`.
- pass: the production resolver performed real anonymous selection and saved-tag revalidation for Agent and Worker on both providers, with cloud credential access replaced by a function that raises. BP selected the existing digest-named tags; domestic selected the existing master tags described above. No tag was created or modified. Safe evidence is stored locally outside Git.
- not_run yet: updated Studio deployment and fresh MPA/runtime/Worker UI verification; append after observing completion. Full A2A, Codex/Pi/Harness suites, domestic deployment, calendar and human IM are outside this bounded validation.
