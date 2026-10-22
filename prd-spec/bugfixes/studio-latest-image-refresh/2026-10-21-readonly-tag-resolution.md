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
| All | Deploy exact tested source and create a fresh Studio MPA | Supported Studio update, deployed module hashes, UI success, native ready state and selected tags, application readiness, actual Worker source/image ID, bounded completed Worker task | pass for deployment/creation/image adoption and fresh-session smoke; initial functional failure retained below |

## Risks and recovery

Read access and tag policies may change. Missing matching tags or registry access must produce a safe diagnostic rather than create a stale deployment. The finite enumeration/time budgets may reject a very large or slow repository. Tags are not cryptographically immutable; publisher discipline remains necessary and retry revalidation detects changes. Public network egress is required; discovery uses direct HTTPS and deliberately ignores environment proxies and netrc. Preserve failed cloud resources and the original persisted intent; rollback Studio through its supported release path if necessary. Do not claim cache invalidation or a fix for the earlier unrelated completion exception. Leave live outcomes unverified until observed.

## 2026-10-21 local and anonymous live verification

The first three GET-only regressions failed against the previous credential-dependent implementation before production changes. The updated suite has **93 passed**; resolver line and branch coverage is **100%**. Relative to origin/main, all **173/173 added executable production lines** (resolver plus service integration) are covered. Coverage execution preloads `pydantic_settings` and SDK Runtime types before pytest to avoid the already-established upstream import-identity issue; no dependency or business-code workaround was introduced.

- pass: `.venv/bin/python -m pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q`, **1266 passed**.
- pass: frontend tests **118 passed**, production build, changed-file Pyright (0 errors), all-files pre-commit including Ruff/format/secret scanning, and `git diff --check`.
- pass: the production resolver performed real anonymous selection and saved-tag revalidation for Agent and Worker on both providers, with cloud credential access replaced by a function that raises. BP selected the existing digest-named tags; domestic selected the existing master tags described above. No tag was created or modified. Safe evidence is stored locally outside Git.
- pass: updated BP Studio deployment, new MPA creation, actual Worker code and a fresh-session command smoke, with the initial functional failure preserved below. Full A2A, Codex/Pi/Harness suites, domestic deployment, calendar and human IM remain outside this bounded validation.

## 2026-10-21 deployed source, new MPA and functional limits

Commit `09e124e8be59ae379c6f1a7e87aba2d568cc1282` was pushed to the existing PR #1178 and deployed using the supported BP Studio update path with `--skip-cronjob-scheduler`. Application `3463b27bd210` / function `cst7puxr` reached stable function revision **12**, release status `done`, at 17:46:56 Asia/Shanghai. All existing environment values and scheduler settings were preserved. The deployed wheel resolver hash is `5028f8feb77cadd5b615f0248a23783c5f7798fdb31ccda3d3f8196a6448cc06`; service hash is `a1e21d2dab3e34bcd5d05860eb4d98b3e1e22ef4f8b3e38a4ce5546c423688d1`; both match the tested checkout.

The existing authorized Chrome session created **`studio-readonly-1021-a`** and displayed creation success. Native state is `ready` and retains both requested latest references plus their selected existing tags:

| Resource | Observed result |
| --- | --- |
| Agent | `mi-5c74df2575dc5e89ad445d76` |
| Runtime | `r-yexqmg6z9cy9bkt9hm42`, Ready, version 2; authenticated health/readiness HTTP 200 |
| Worker Tool | `t-yexqlmcetcy9bkt9ihdf`, Ready; created at 17:48 and reused on the same-request retries |
| Agent selected tag | `mpa_agent:mpa-sha256-63d32384da817cb38b55b6dfeda7d2cd8a851e9d119d18abb30ee8632aec599f` |
| Worker selected tag | `mpa_codex_worker:mpa-sha256-1e40dd91e8c10b067a31ef4113eb9829575baf9101cf9d5e6103144b9491f862` |
| Worker function / revision / actual image ID | `ptlrrzjl` / 1 / **`ayk6eadc2t`**, not old `vollyz6n0i` |
| Actual Worker source | 215 Python files; fingerprint `30c2b491f1fe460e731627bda9f40f160a6d26f4d7d8398ff91a3056a2943490`, matching the published Worker; private-user module present |
| Business PG / SkillSpace / OV | `sunny-bluet-3db026cb`, aidb ready / `ss-yexqmg5kowdlwzgmqn9d` / `ov-f54074c915387e15`, READY |
| Successful bounded smoke | Fresh Studio session `8606260b-eeb7-4752-9782-0a860fc6fd07` ran `/bin/bash -lc 'printf STUDIO_READONLY_1021_FRESH_OK'`; actual stdout matched, exit 0, and the completed answer displayed both |

The two image references use `agentkit-platform-3001037806-ap-southeast-1.cr.bytepluses.com/mpa/`. These tags already existed; discovery published nothing. The dedicated source-probe session `s-yexqlugkxsuexbvqjn6i` was deleted. Safe native/deployment/API evidence and creation/functional screenshots are retained locally outside Git; no secrets or raw cloud records were committed.

Two independent conditions were observed and must not be hidden by the successful fresh-session smoke:

1. Creation task `49556dec-276c-4053-9507-ed08cdb98bf3` initially hit OV `InvalidParameter`. Overseas CloudTrail records for requests `2026102109482052668D9A8D2903007881` and `20261021095118D4C86EA35A3890F6A34D` establish that collection count exceeded the account maximum **20**; the existing UI generalized this as a model/configuration rejection. After explicit user approval, only the previous test `studio-snapshot-1021-a` library `ov-4dcc6e25514a5979` was ownership-checked and deleted; deletion succeeded and a subsequent Get confirmed collection-not-found. That old test MPA now has no usable OV memory library. The same creation request then succeeded, retaining its Worker and both image selections. No OV code, model setting, quota or Runtime configuration workaround was introduced.
2. Initial Studio session `de1ce841-0f42-4087-be22-8845b1014798` did **not** execute the requested printf. Its UI reported `inactive_worker_dispatch` and `harness invocation plan update was not persisted`; it ended with a failure explanation. The durable harness/control state reported `completed`, which does not prove command execution. Source inspection locates the former in the Agent MainRuntime active-grant check and the latter in guarded plan persistence; the root cause remains unproven and neither path was changed here. No pause mutation was issued because inspection found the task already completed. A separate fresh session with a bounded stop-on-error prompt subsequently executed the command successfully. This is a creation/image/fresh-session smoke pass, **not** proof that all initial-session or explicit Worker-dispatch paths are reliable.

Remaining limits: full A2A/calendar/IM and domestic Runtime deployment are unverified; publisher tag retention/non-overwrite remains required. The successful new MPA and both functional conversations are retained for review. Existing MPAs are not upgraded.
