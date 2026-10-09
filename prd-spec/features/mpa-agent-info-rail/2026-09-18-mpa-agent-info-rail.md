# MPA conversation information rail

- Change ID: `mpa-agent-info-rail`
- Date: 2026-09-18
- Status: implemented; real-browser verification blocked
- Chinese: [Chinese design](2026-09-18-mpa-agent-info-rail.zh.md)
- Contract: [Studio MPA control plane](../../../specs/studio-mpa-control-plane/README.md)

## Background and evidence

`frontend/src/ui/AgentTopology.tsx` labels generic graph/draft instructions as AGENTS.md and combines generic skills with Session selections. The A2A adapter in `veadk/cli/cli_frontend.py` returns an empty skills list. The inspected local agentkit-mpa-agent revision `f14fa39` exposes `GET /api/v1/agents` with `agentsMd`; its Agent Card resource-topology extension advertises configured Skill Space resource IDs. Studio already exposes paginated `/web/skill-spaces/{space_id}/skills`. No live Runtime was queried.

## Goals and non-goals

Show authoritative MPA configuration and bound-space skills in the existing conversation rail. Hide the entire rail for non-MPA or unclassified agents. Preserve Session environment controls and remove temporary Session skill mounting. Allow permission-aware SKILL.md editing and add the required MPA read-only authentication endpoint. No editing of AGENTS.md, change of Skill Space bindings, provider deployment, or new dependency.

## Requirements and scenarios

- FR-1: Only a Runtime tagged `veadk:agent-type=mpa` receives MPA rail metadata. Generic/local/unknown agents have no rail or reserved rail width.
- FR-2: Read the current MPA `agentsMd` through the authenticated Runtime connection. Preserve document text; never substitute generic instructions. Empty content, unavailable API, denied access, and failed requests have distinct states and retry.
- FR-3: Read configured `skill-space` nodes from the advertised topology and enumerate their skills with the existing account-authorized SkillSpace API. Respect Runtime region, pagination, resource identity, and degraded results. Show name, description, count; temporary Session additions are hidden and excluded from MPA messages.
- FR-4: Switching Runtime cancels outstanding list requests and discards late results. Refresh retains current readable data where possible; access revocation clears it. Failures never become an empty-success list. Long text scrolls within the existing rail.
- FR-5: Preserve existing model/lifecycle capabilities, Session environment controls, normal chat, and non-MPA API behavior. Requests use existing server-managed credentials; only allowlisted fields enter the UI, never arbitrary upstream errors/configuration.

## Design and contract impact

The Runtime proxy recognizes tagged MPA metadata requests, including native app names and `a2a-default`, and extends its normalized AgentInfo with `agentCategory` and an optional typed `mpa` payload. A focused backend helper reads `/api/v1/studio/agent-info` with the server-resolved Runtime key and supports the legacy `/api/v1/agents` fallback, classifies failures, and extracts only configured space IDs from the Agent Card. Missing topology is unsupported, not an empty binding list. Existing generic A2A capability normalization remains in place. The browser's MPA rail controller owns paginated SkillSpace loading and refresh/cancellation; AgentInfoPanel remains presentation-only. AGENTS.md is rendered as escaped text with preserved line breaks. MPA detail retry reloads metadata. Existing skill-page clients gain an optional AbortSignal. The authenticated Skill document editor uses the existing version publication path; see the follow-up design and [document contract](../../../specs/studio-skill-document/README.md). No public SDK or generated Agent contract changes. CON-16/17 are implemented in the existing bilingual control-plane spec.

## Tasks and acceptance

| Task | Requirements | Acceptance | Verification |
| --- | --- | --- | --- |
| T-1 backend metadata | FR-1/2/5 | AC-1 native/A2A MPA tagged metadata, content and classified failures; generic A2A unchanged | Targeted Python metadata and Runtime proxy tests |
| T-2 frontend data/state | FR-2/3/4 | AC-2 multi-page skills, no stale data, partial/degraded/error/empty states and retry | Vitest API/controller tests |
| T-3 UI integration | FR-1/3/5 | AC-3 MPA-only rail, no temporary mounting, preserved environment controls | Panel tests, frontend regression, browser |
| T-4 reconcile | all | AC-4 bilingual docs, production assets, no new lint/type errors | i18n/build/assets, Ruff/Pyright, secret scan |

## Risks and review

SkillSpace region follows the selected Runtime's region, matching the current MPA deployment contract. Old Runtime images may lack the read API or topology; the UI explains unsupported data without inventing it. Existing SkillSpace authorization is retained. User approved the concrete plan with “帮我改”. Direct design review checked boundaries, cancellation, errors, compatibility, permission safety and bilingual equivalence; no blockers. The referenced frontend-design/ui-ux-pro-max and review-spec skills are not installed; use frontend/SPEC.md and direct review. No graphify index exists; implementation inspected directly.

## Affected files

`frontend/server/mpa_agent_info.py`, `veadk/cli/cli_frontend.py`, `frontend/src/adk/client.ts`, `frontend/src/create/skills/skillspace.ts`, `frontend/src/App.tsx`, `frontend/src/ui/AgentTopology.tsx`, `frontend/src/ui/mpa-agent-info/MpaAgentInfoRail.tsx`, `frontend/src/styles.css`, both workspaceTools locale catalogs, corresponding Python/Node/Vitest tests, `frontend/package.json`, `frontend/README.md`, this PRD pair, the control-plane spec pair, and `veadk/webui` generated assets.

## Initial verification record (before the follow-up)

Tested on 2026-09-18: working diff against `f497cc6d` on `feat/from-main`, including the metadata helper/proxy, client, rail/controller, locale strings, docs and generated assets.

| Check | Result | Evidence |
| --- | --- | --- |
| Test-first regression | pass | New helper/controller tests first failed because their modules did not exist, then passed after implementation. |
| `uv run --extra dev pytest tests/frontend/server/test_mpa_agent_info.py tests/cli/test_frontend_runtime_proxy.py` | pass | 91 passed; HTTP failures, malformed data, timeout, allowlist, tagged/native/virtual MPA and generic A2A compatibility. |
| `npm --prefix frontend test` | pass | 1208 Node tests and 11 MPA Vitest tests; the new suite is included in the standard test command. Covers pagination, cancellation/late results, partial/error retry, revoked access, degraded data and escaped document text. |
| `npm --prefix frontend run check:i18n` | pass | Both locales and 21 namespaces consistent. |
| `npm --prefix frontend run build` | pass | TypeScript and both production bundles built; existing bundle-size warning remains. |
| `npm --prefix frontend run test:webui-assets` | pass | 104 packaged files, 248 internal references. |
| Ruff for four changed Python files | pass | `uv run --extra dev --with 'ruff==0.11.12' ruff check ...`; uses repository hook version. |
| Pyright for four changed Python files | fail (baseline) | `uv run --extra dev --with pyright pyright --pythonpath .venv/bin/python ...`; 56 diagnostics, identical to HEAD by file/rule/message (36 in cli_frontend, 20 in existing proxy tests), no new diagnostics. New helper and its tests have none. |
| Gitleaks changed-file snapshot, including untracked code and generated assets | pass | `gitleaks dir <snapshot> --config .gitleaks.toml --redact`; no leaks found. |
| Source whitespace and paired docs/links | pass | `git diff --check -- ':!veadk/webui'`; paired identifiers and relative links reviewed. |
| Real-browser normal/loading/empty/error/retry/keyboard/narrow-window verification | blocked | Local isolated preview prepared; browser rejected access because the admin-enforced safety policy could not be verified. No bypass attempted. Temporary preview and server removed. Component tests do not replace visual/browser evidence. |
| IME; harness coverage; generated Python/deployment; full SDK regressions | not_applicable | No input, sidecar, code generation, deployment or SDK changes; full frontend and Runtime proxy suites cover the affected shared surface. |
| Real cloud/provider smoke | not_run | No live service authorized or invoked; all network regression tests use mocks. |
| Pre-commit all-files; remote synchronization; commit/push | not_run | No commit requested. These remain required before a later authorized commit; targeted Ruff and changed-file secret scanning ran now. |

Direct implementation review found no unresolved code blockers after checking MPA gating, native/virtual app compatibility, text escaping, credential allowlisting, empty/error distinctions, multi-page skill loading, abort cleanup and bilingual contract alignment. T-1/T-2 are verified; T-3 browser evidence and final acceptance remain blocked as above. T-4 documents/assets are synchronized, with baseline Pyright failures recorded rather than hidden. No production Runtime result is claimed.

## Approved follow-up: authentication and Skill document editing

On 2026-09-18 the user requested: complete authenticated AGENTS.md reads, remove temporary mounting, and support editing bound Skill Space SKILL.md. The requirements above reflect this updated scope. Direct design review approves the following bounded implementation; existing JWT authorization and SkillSpace ownership rules remain unchanged.

- Add a read-only `/api/v1/studio/agent-info` in agentkit-mpa-agent, authenticating a dedicated `X-MPA-Studio-Key` against the current MPA's stored Runtime key with constant-time comparison. Missing/invalid keys fail closed; return only name, description, model and agentsMd. Studio supplies only its server-resolved Runtime key. Never copy an API key into a JWT header. Old images can use the existing JWT endpoint when available; otherwise require upgrade.
- Remove the MPA temporary-skill list and picker, and exclude previously persisted temporary selections from MPA outgoing messages. Keep environment controls and generic Agent behavior.
- Bound skill rows retain space/region/skill/version identity. Open a dialog for the latest SKILL.md with server-provided write permission. Save creates and publishes a new version to the selected space through the existing version service, retaining all other archive members, binary bytes and file attributes. Shared/review spaces remain read-only. Show that this updates shared configuration and may require runtime cache refresh/new sessions.
- New authenticated GET/PUT `/web/skill-management/spaces/{space_id}/skills/{skill_id}/document` returns `content`, `baseVersion`, `canUpdate`; PUT accepts `content` and `baseVersion`, rejects stale versions with 409 under the existing process-local upload lock, and validates archive size/frontmatter/unchanged name. There is no provider compare-and-swap; external writers can still race after validation. Do not claim distributed transaction isolation.
- Dialog supports cancel, keyboard focus/Escape, read-only, error/retry and retained unsaved text. Save is explicit, guarded against duplicate clicks; closing is disabled while saving. Switching agents unmounts editor and ignores late responses. No automatic provider writes or deployments are performed during implementation.
- Affected additional files: MPA router/new metadata route and tests; Studio skill document service/routes and version upload guard, new editor client/UI/tests, existing rail/panel/App, locales, docs and assets. Required tests: missing/wrong credential and allowlist, no MPA temporary selections, editor permission/save/error, byte-preserving archive edit, stale version/name denial. Re-run affected backend, frontend, type/build, lint, secret checks; record browser/service limitations.

The MPA Runtime image must be updated for this endpoint; changing only Studio cannot deploy the authentication fix. No deployment or commit is authorized by this implementation request.

## Follow-up verification and delivery

Tested 2026-09-18 against Studio `f497cc6d` (`feat/from-main`) and MPA `f14fa39` (`feat/mcp-skill-adap`), including all uncommitted changes described above. The user explicitly approved authentication completion, removal of temporary mounts and skill editing; direct review covered auth boundaries, ownership, ZIP integrity, permission denial, stale versions, cancellation and bilingual equivalence.

- **pass**: `npm --prefix frontend test` — 1208 Node tests and 17 component tests. `npm --prefix frontend run check:i18n`, `npm --prefix frontend run build`, and `npm --prefix frontend run test:webui-assets` (104 files / 248 references).
- **pass**: `uv run --extra dev pytest tests/frontend/server/test_mpa_agent_info.py tests/frontend/server/skills tests/cli/test_frontend_runtime_proxy.py` — 290 passed; covers the full Skill service and Runtime proxy suites.
- **pass**: In MPA, `.venv/bin/python -m pytest tests/test_studio_metadata.py tests/test_auth.py tests/test_channels_auth.py -q` — 29 passed. New metadata endpoint, optional null fields, missing/wrong keys, no write route and existing auth compatibility.
- **pass**: Repository-pinned Ruff 0.11.12 on changed Python code/tests in both repositories. MPA Pyright on its three changed Python files: zero diagnostics. Studio Pyright: **fail (baseline)**, same 56 existing diagnostics in cli_frontend/proxy tests; no diagnostics in the new or edited Skill/metadata modules.
- **pass**: Redacted Gitleaks scan of both repositories' changed files including untracked additions and generated assets; no leaks. Source whitespace and bilingual relative links checked.
- **blocked**: Real browser verification remains unavailable following the browser's admin-policy verification rejection. Automated component tests cover editing, retry, readonly, duplicate-save lock, cancellation and IME/Escape, but are not visual/browser evidence.
- **not_run**: Live cloud editing, MPA deployment and production end-to-end verification. Tests use isolated simulated services. Both repos remain uncommitted; pre-commit all-files and branch synchronization are still required before any later authorized commit. No SDK or sidecar contract change requires their broader gates.

Acceptance: code for authenticated reads, bound-only skill display and permission-aware editing is implemented and covered by local tests. Browser acceptance and live Runtime verification are outstanding. To enable AGENTS.md on a running agent, publish the updated MPA image while preserving `mpa_meta.runtime_api_key`, then upgrade Studio; old Runtime images receive an explicit upgrade message if their legacy JWT route cannot be used. Save errors can have uncertain provider outcomes; check the latest version before retrying. No live Runtime was changed by this task.
