# Studio-created MPA Runtime filtering

[中文版](2026-09-28-studio-mpa-source-filter.zh.md)

- Change ID: `studio-mpa-source-filter`
- Created/Revised: 2026-09-28
- Status: `approved`
- Owner repository: `veadk-python`
- Components: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), [Studio MPA control plane](../../../specs/studio-mpa-control-plane/README.md)
- Approval: the user selected progressive source filtering (approach 1) on 2026-09-28.

## 1. Background and evidence

Studio currently classifies MPA Runtimes only through `veadk:agent-type=mpa`. Administrators receive `runtimeScope=all`, so MPA Runtimes created by other products or operations can appear in Studio. `scope=mine` is an ownership filter based on `veadk:owner`; it does not prove Studio provenance.

The generic Studio deployment path writes `veadk:managed=true`, `veadk:owner`, and `veadk:author`, but its MPA branch has no dedicated provisioner marker. Managed one-click creation persists `studio_owner` in its registry yet currently projects only `veadk:agent-type=mpa` into Runtime tags. Names, image references, `mi-` prefixes, and ownership alone are therefore not safe provenance signals.

## 2. Goals and non-goals

Goals:

- Show only Studio-managed MPA Runtimes in Studio's MPA list.
- Filter through the server-side Tag query before hydration and pagination.
- Make both Studio MPA creation paths write consistent provenance and ownership tags.
- Preserve generic Studio-created MPA Runtimes that already have `veadk:managed=true`.
- Keep Runtime authorization independent from provenance filtering.

Non-goals:

- No name, image, artifact URL, Runtime ID prefix, environment-value, or registry heuristic.
- No automatic cloud mutation or unattended bulk backfill. A one-time, explicitly authorized and verified operator backfill may designate known historical MPA Runtimes as Studio-managed and must be recorded in this PRD.
- No change to general-agent listing, authorization, enterprise visibility, deletion permissions, response schemas, or UI layout.
- `veadk:managed=true` is not an authorization credential.

## 3. Alternatives and decision

1. **Progressive source filtering — selected.** Write existing compatibility marker `veadk:managed=true` plus `veadk:provisioner=studio-mpa`; filter current MPA lists by `agent-type=mpa + managed=true`.
2. **Strict new-tag filtering.** Require `veadk:provisioner=studio-mpa` immediately; exact for new resources but hides all legacy Studio MPA before backfill.
3. **Registry join.** Recover legacy provenance from the deployment registry; this adds data-source coupling, cost, and availability failure modes to every list request.

Approach 1 is the smallest safe change. A future explicit migration may backfill `veadk:provisioner`; until then `veadk:managed=true` is the compatibility admission marker.

## 4. Requirements

### FR-1: Creation provenance

Both Studio MPA creation paths write:

- `veadk:agent-type=mpa`
- `veadk:managed=true`
- `veadk:provisioner=studio-mpa`
- `veadk:owner=<trusted Studio owner id>`; Studio creation fails before cloud mutation if this identity is unavailable
- `veadk:mpa-instance-id=<MPA instance id>` when that path owns the identity

Reconciliation replaces these owned keys, preserves unrelated non-system tags, and never copies `sys:*` tags into create/update payloads.
The managed provisioning service is also used by `veadk mpa create`, so Studio provenance is injected only when the Studio route explicitly supplies a trusted Runtime owner. The task database and native deployment registry retain their hashed owner for private task scoping; the raw trusted owner is passed only to the fixed child process and Runtime tag payload, not persisted in local task state. CLI-created MPA Runtimes keep only their MPA category tag and are not admitted by the Studio-managed filter.

### FR-2: Server-side source filter

`GET /web/runtimes?agentCategory=mpa` queries the Tag service with both `veadk:agent-type=mpa` and `veadk:managed=true` before hydration and pagination. `scope=mine` additionally requires `veadk:owner=<current principal owner id>`. Administrator `scope=all` returns all Studio-managed MPA Runtimes, not every account MPA Runtime.

### FR-3: Compatibility

An MPA Runtime carrying only `veadk:agent-type=mpa` is hidden. An existing generic Studio MPA with `veadk:managed=true` remains visible without the new provisioner tag. Existing managed one-click Runtimes without `veadk:managed=true` remain hidden until an explicit supported update/retry writes the tags. No heuristic fallback is allowed.

### FR-4: Security and failures

Filtering controls discovery only. Existing role, owner, enterprise visibility, Runtime authorization, and mutation checks remain authoritative. Tag-service failure remains fail-closed and must not fall back to an unfiltered scan. Browser parameters cannot disable the managed-MPA filter.

## 5. Design and tasks

- Add one internal MPA Runtime-tag module for the category, managed, provisioner, owner, and MPA-instance tag constants. This is not a new public Python API.
- Extend generic Studio MPA deployment with the provisioner marker; retain existing managed/owner/author/instance tags.
- Reconcile trusted owner and provenance tags into the managed one-click Runtime template only when the Studio route explicitly supplies the trusted Runtime owner. Keep task/registry ownership hashed and keep CLI provisioning outside Studio provenance.
- Make `_list_mpa_region` always add category and managed positive filters; owner filters remain additive.
- Keep `CloudRuntime`, cache keys, paging tokens, response payloads, and frontend rendering unchanged.

| Task | Work | Files |
| --- | --- | --- |
| `T-1` | Add failing creation/list filtering tests. | `tests/cli/test_frontend_runtime_proxy.py`, `tests/cli/test_studio_rbac.py`, `tests/integrations/mpa_managed/` |
| `T-2` | Add internal shared tag constants and generic Studio MPA provisioner tag. | `veadk/integrations/mpa/tags.py`, `veadk/cli/cli_frontend.py` |
| `T-3` | Add Studio-only one-click managed/provisioner/owner/instance tags while preserving hashed task/registry ownership and excluding CLI provisioning. | `frontend/server/mpa_creation.py`, `veadk/integrations/mpa/managed/tasks.py`, `runner.py`, `service.py`, `runtime.py` |
| `T-4` | Enforce managed MPA Tag-service filtering. | `veadk/cli/cli_frontend.py` |
| `T-5` | Reconcile docs and verification; rebuild WebUI only if frontend source changes. | PRD/spec pair and generated assets if applicable |

## 6. Acceptance and verification

| Requirement | Acceptance criterion | Verification | Result |
| --- | --- | --- | --- |
| `FR-1` | `AC-1`: both Studio creation paths emit exact managed/provisioner/owner tags and the MPA instance tag; missing trusted owner fails before cloud mutation; CLI provisioning does not emit Studio provenance. | Exact create/update tag payload, missing-owner, owner-propagation, and CLI-negative tests. | `pass` — targeted creation/service/task tests, 2026-09-29 |
| `FR-2` | `AC-2`: MPA Tag lookup always includes category and managed; mine also includes owner. | Admin/all and owner/mine route tests. | `pass` — targeted Runtime-list tests, 2026-09-29 |
| `FR-3` | `AC-3`: agent-type-only external MPA is absent; managed legacy Studio MPA remains visible. | Positive/negative pagination fixtures. | `pass` — targeted Runtime-list tests, 2026-09-29 |
| `FR-4` | `AC-4`: failure is fail-closed and general Runtime behavior is unchanged. | Tag failure/general-category regressions. | `pass` — targeted and repository regression tests, 2026-09-29 |

```bash
uv run --extra dev pytest -q tests/cli/test_frontend_runtime_proxy.py tests/cli/test_studio_rbac.py tests/integrations/mpa_managed
uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"
npm --prefix frontend test
npm --prefix frontend run build
uv run --extra dev pre-commit run --all-files
```

Browser verification is required: use the local Studio against read-only Runtime discovery to prove an untagged external MPA is absent, a managed MPA is present, loading/error/empty states remain distinct, and general-agent discovery is unchanged. No screenshot or raw provider response is committed. A later explicitly authorized one-time backfill is recorded below and does not enable automatic migration behavior in the product.

Verification record for the uncommitted diff from base `69dd24cd15b2372b76d1666246fc40fbac27235e` on 2026-09-29:

- `pass`: targeted MPA backend tests after the final code review — 506 passed, 6 warnings.
- `pass`: repository Python regression after the final code review — 6142 passed, 18 skipped, 2 xfailed, 84 warnings; smoke markers were excluded by the repository command above.
- `pass`: frontend tests — 1367 Node tests and 39 Vitest tests passed.
- `pass`: frontend production build; existing Vite chunk-size/dynamic-import warnings only, with no generated-asset diff.
- `pass`: Ruff and format checks for all changed Python/test files; `git diff --check` passed.
- `pass`: Pyright for the six changed/new focused backend modules outside `cli_frontend.py` — 0 errors.
- `fail` (pre-existing baseline): direct Pyright of changed `veadk/cli/cli_frontend.py` reports 36 existing errors outside this change's added lines; this change does not broaden into unrelated type cleanup.
- `pass`: repository pre-commit — Ruff, format, hardcoded-secret detection, and concrete-YAML-secret detection all passed.
- `pass`: two-round implementation/spec review corrected CLI provenance admission and raw-owner/hashed-owner separation. The first code review fixed three medium findings: legacy pending create replay now retains its exact original payload before upgrading tags, non-NotFound hydration failures remain error states instead of empty success, and task ownership must match the hash of the raw Studio Runtime owner. The post-backfill review fixed one medium cross-region hydration amplification issue by filtering authoritative Runtime TRNs before `GetRuntime`, plus one low verification-record ambiguity. No blocking finding remains.
- `pass`: restarted local Studio from this worktree; `/`, `/web/ui-config`, filtered MPA discovery, and general Runtime discovery returned successfully. Before the authorized backfill, the filtered MPA response contained one item and the general first page contained five items; no raw provider response was persisted.
- `not_run`: real-browser read-only discovery verification, pending the user's local Studio validation after restart.
- `pass`: explicitly authorized one-time tag backfill — 18 live Beijing Runtimes carrying `veadk:agent-type=mpa` and missing the managed marker were designated with only `veadk:managed=true`; all 18 writes succeeded, the post-write managed set contained 19 unique live Runtimes, and comparison found no other tag changes. Cross-region duplicate tag mappings that did not resolve through `GetRuntime` were not mutated.
- `not_applicable`: Runtime deployment, image rollout, environment mutation, and automated migration.

## 7. Risks and delivery record

- Any future MPA Runtime without `veadk:managed=true` remains hidden until explicit update/retry or another authorized controlled backfill. This is intentional fail-closed behavior.
- Privileged external operators can alter tags; tags are discovery metadata, never authorization.
- Server-side filtering preserves pagination correctness; browser-only filtering is prohibited.
- 2026-09-28: approach 1 approved. Implementation, commit, push, PR, deployment, and cloud backfill remain separately authorized.
- 2026-09-29: implementation and automated/local API verification completed in the independent worktree. No commit, push, PR, deployment, or backfill was performed.
- 2026-09-29: the user explicitly authorized historical MPA tag backfill. Eighteen verified live Beijing MPA Runtimes received only `veadk:managed=true`; the Studio MPA list then returned 19 unique items. No Runtime deployment, image/environment change, commit, push, or PR was performed.
