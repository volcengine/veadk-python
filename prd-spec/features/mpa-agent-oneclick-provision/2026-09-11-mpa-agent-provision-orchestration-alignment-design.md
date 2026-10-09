# mpa-agent Provisioning Orchestration Alignment (CreateTool + SkillSpace + Runtime) Design

## Metadata

- **Change ID:** `mpa-agent-oneclick-provision`
- **Created / Revised:** 2026-09-11 / 2026-09-11
- **Lifecycle status:** `approved`
- **Language counterpart:** [2026-09-11-mpa-agent-provision-orchestration-alignment-design.zh.md](2026-09-11-mpa-agent-provision-orchestration-alignment-design.zh.md)
- **Predecessor:** [2026-09-10-mpa-agent-oneclick-provision-design.md](./2026-09-10-mpa-agent-oneclick-provision-design.md) (`approved`, implemented) — this version extends its scope; it does not replace the delivered pieces.
- **Related component specs:** none created yet; CLI contract surface extended (see §6).
- **Reference implementation:** `~/workspace/bytedance/mpa/mpa-runtime/docs/runtime-manager-openapi-map.md` (Runtime Manager creation chain).

## 1. Overview

### 1.1 Problem / Background

The delivered route A (`2026-09-10` design, commit `18fa2485`) provisions a veadk-version mpa-agent by: `deploy_image` (VeFaaS + APIG, key auth) → seed `mpa_meta` → inject env → verify. It treats the Codex sandbox **Tool id** and any **Skill Space** as pre-existing external parameters.

The Runtime Manager reference chain (`runtime-manager-openapi-map.md`) shows the full orchestration a provisioner is expected to own, in order:

```text
... -> CreateSkillSpace/GetSkillSpace -> CreateTool -> tool_id
    -> CreateRuntime(ArtifactUrl, RoleName, ToolId, Envs=PG*+SkillSpaceId+ToolId)
    -> ReleaseRuntime -> GetRuntime Ready -> /run_sse verify -> persist bindings
```

Two gaps versus that reference remain in route A:

- **CreateTool is not orchestrated.** The Codex sandbox `Tool` (`t-*`, built from the `mpa_codex_worker` image) must be created and its id obtained **before** the agent is created. Route A requires the caller to pass an existing `t-*`.
- **Skill Space is not orchestrated.** The reference creates/selects a Skill Space and injects `SKILL_SPACE_ID`; route A only forwards `--skill-space-id` if given.

There is also a **compute-plane modeling difference**: the reference uses AgentKit `CreateRuntime` (produces an `r-*` runtime; mpa-agent's own `agentkit.yaml` ships as `runtime_id: r-yerdk5srnk54ppxtxy25`), while route A uses `VeFaaS.deploy_image` (VeFaaS App + self-created APIG). Both run the image, but only `CreateRuntime` matches the reference resource model and mpa-agent's native delivery shape.

### 1.2 Goals

Bring `veadk mpa create` up to the reference orchestration so it can stand up an mpa-agent end to end from an image, owning Tool and Skill Space creation, while keeping PostgreSQL/OpenViking as external parameters and requiring no control-plane `mi-*` record.

- **G1 — Orchestrate a per-agent CreateTool.** By default, create one dedicated Codex sandbox `Tool` from the provided worker image for every newly generated mpa-agent id and obtain its `tool_id` before runtime creation. An existing `--agentkit-tool-id` remains an explicit debug/migration escape hatch.
- **G2 — Orchestrate Skill Space.** Optionally create or select an AgentKit Skill Space and inject `SKILL_SPACE_ID`.
- **G3 — Align the compute plane.** Provision the agent through AgentKit `CreateRuntime` (`r-*`) to match the reference and mpa-agent's native runtime model, while keeping the existing `deploy_image` path available as a fallback selected by a flag.
- **G4 — Preserve route A guarantees.** `mpa_meta` seeding, identity adaptation (`IDENTITY_STARTUP_ENABLED=false`, `CLAW_SPACE_ID=csi-<account_id>`), public-endpoint authority, verification, secret masking, and non-regression of mpa-agent all remain.

### 1.3 Non-Goals

- Not creating PostgreSQL instances/databases or OpenViking `ov-*` resources (external preconditions, unchanged from route A).
- Not building the image itself; `--image`/`--tool-image` are inputs (artifact-first, per the reference "Artifact 来源" section).
- Not implementing AIDAP Workspace/Branch/Database/DBAccount creation (the reference does this for RDS; our DB is external).
- Not a control-plane `mi-*` record; the veadk-version mpa-agent runs without one.

## 2. Scenarios

### Scenario 1: Full orchestration from images

**Given** an mpa-agent image, a Codex worker image, an existing external PostgreSQL, model credentials, and account/region.
**When** the operator runs `veadk mpa create` with `--tool-image <worker-image>`, no `--mpa-agent-id`, and no `--agentkit-tool-id`.
**Then** the CLI generates a globally unique `mi-<12 lowercase alnum>` id, derives the Tool name by replacing `-` with `_`, creates that dedicated Tool (obtains `t-*`), optionally creates/selects a Skill Space, provisions a Runtime named from the generated id, seeds `mpa_meta`, verifies, and prints Studio A2A connection guidance.

### Scenario 2: Reuse an existing Tool

**Given** an existing Codex worker Tool `t-*` (e.g. `t-yeslt9bv9ckgnctgwaaf`).
**When** the operator passes `--agentkit-tool-id t-*` and omits `--tool-image`.
**Then** the CLI skips CreateTool, reuses the id, and proceeds. (This preserves route A behavior.)

### Scenario 3: Runtime readiness and verification

**Given** a provisioned runtime.
**When** creation completes.
**Then** the CLI waits for the runtime to reach Ready (or the VeFaaS app to release), then probes `/health`, `/readiness`, and the A2A agent-card before reporting success.

### Scenario 4: Idempotent re-run and rollback

**Given** a previous partial run.
**When** the operator re-runs with the same names/ids.
**Then** the exact-name Tool/Skill Space/Runtime is reused. A non-Ready Tool is awaited, a reused Runtime is updated and released to converge image/Tool/env, and the CLI waits for the newer Ready version. Duplicate exact names fail as ambiguous instead of selecting an arbitrary resource. The two-phase `mpa_meta` row may remain with placeholders after a post-create failure and is never presented as finalized.

## 3. Functional Requirements

Route A requirements FR-1..FR-11 (previous design) remain in force. This version adds:

- **FR-12 — Per-agent CreateTool orchestration.** The CLI generates `mpa_agent_id` as `mi-` plus 12 lowercase alphanumeric characters when omitted. Without `--agentkit-tool-id`, `--tool-image` is required and the CLI creates a Codex sandbox Tool via `CreateTool`, using the agent id with hyphens replaced by underscores as its default name, then obtains `tool_id`. The verified Tool contract remains unchanged. An explicit `--agentkit-tool-id` skips CreateTool as a debug/migration escape hatch.
- **FR-13 — Per-agent identity and idempotency.** A normally generated agent id is unique per invocation and maps to a distinct Tool name and Runtime name. An explicit `--mpa-agent-id` makes a retry idempotent by reusing a Ready Tool with that derived name. `--tool-name` and `--runtime-name` remain explicit debug overrides.
- **FR-14 — Skill Space orchestration.** When `--skill-space-name` is provided, the CLI creates or selects an AgentKit Skill Space via `agentkit.sdk.skills` (`list_skill_spaces`/`create_skill_space`/`get_skill_space`) and injects the resolved `SKILL_SPACE_ID` into the runtime env. When only `--skill-space-id` is provided it is used directly; when neither is provided, Skill Space is omitted.
- **FR-15 — Compute-plane selection.** A `--compute-plane {runtime,vefaas}` option selects provisioning: `runtime` (default) uses AgentKit `CreateRuntime`/`ReleaseRuntime` (`r-*`, matching the reference and mpa-agent's native model); `vefaas` uses the existing `deploy_image` path (route A). Both must yield the same downstream contract: a public endpoint, an APIG-backed key-auth API key, and an APIG instance id for `mpa_meta`.
- **FR-16 — Runtime path env and binding.** For `--compute-plane runtime`, `CreateRuntime` is called with `ArtifactType`/`ArtifactUrl=<mpa-agent image>`, `ToolId`, `RoleName`, key-auth authorizer, and `Envs` = the route A runtime env plus `SKILL_SPACE_ID` (when resolved) and `AGENTKIT_TOOL_ID`. Env changes go in `CreateRuntime`/`UpdateRuntime` (never `ReleaseRuntime`, which has no `Envs`), per the reference constraint.
- **FR-17 — Ordered idempotent orchestration with rollback.** The CLI runs SkillSpace → Tool → **pre-seed `mpa_meta` (FR-19)** → compute-plane create → **finalize `mpa_meta` (FR-19)** → verify, in that order. Each creation is idempotent by name/client-token; a failure after a resource is created surfaces the created ids for cleanup.
- **FR-18 — `mpa_meta` fields from either plane.** `runtime_id` is the AgentKit runtime id (`r-*`) in runtime mode or the VeFaaS app id in vefaas mode; `apig_instance_id`, `runtime_api_key`, `public_endpoint` are resolved from the selected plane. `private_endpoint` mirrors `public_endpoint` (FR-11 unchanged).
- **FR-19 — Two-phase seeding before first container start (verified by smoke).** The mpa-agent container starts as soon as the runtime is released, and on startup it calls `GetMpaInstanceConf` unless the `mpa_meta` row is already complete. On the test account this call returns `403 AccessDenied` for `arkclaw:GetMpaInstanceConf`, so startup fails if seeding happens after release. Therefore seeding is two-phase, keyed by the caller-known `mpa_agent_id`:
  - **Phase 1 (before compute-plane create):** seed the `mpa_meta` row with real `account_id`/`resource_account_id` and **non-empty placeholders** for `runtime_id`/`public_endpoint`/`private_endpoint`/`runtime_api_key`/`apig_instance_id`, so `mpa_instance_conf_ready()` is already true at first container start and the runtime skips `GetMpaInstanceConf`.
  - **Phase 2 (after Ready):** overwrite the placeholder fields with the real deploy-resolved values. This requires the seeder to support an explicit overwrite update (distinct from route A's fill-empty), applied only to the phase-1 placeholder fields.
  - Placeholders do not affect A2A chat startup (the agent-card URL comes from `A2A_PUBLIC_URL`, injected separately); real endpoint/apig/key values matter for IM-gateway paths and are finalized in phase 2.
- **FR-20 — APIG binding integrity.** Finalization requires a real non-empty `runtime_id`, `public_endpoint`, `runtime_api_key`, and `apig_instance_id`. Runtime mode accepts an APIG id only when explicitly supplied with `--apig-instance-id`, returned by the compute plane, or uniquely embedded in/mapped from the public endpoint. It must not fall back to an unrelated account gateway. AgentKit shared-gateway responses with `GatewayInstanceId=""` fail closed and leave phase-1 placeholders unfinalized.

## 4. Design and Contract Impact

### 4.1 Orchestration order (matches the reference)

```text
resolve params and generate mpa_agent_id when omitted
  -> [FR-14] ensure SkillSpace (create/select) -> skill_space_id
  -> [FR-12/13] derive Tool/Runtime names from mpa_agent_id
  -> ensure Tool (reuse same-agent Ready Tool or CreateTool from --tool-image) -> tool_id
  -> assemble runtime env (route A env + SKILL_SPACE_ID + AGENTKIT_TOOL_ID)
  -> [FR-19 phase 1] pre-seed mpa_meta (real account + non-empty placeholders)
                     so first container start skips GetMpaInstanceConf (403 on test account)
  -> [FR-15/16] compute plane:
       runtime : CreateRuntime(ToolId, ArtifactUrl, Envs) -> ReleaseRuntime -> GetRuntime Ready
       vefaas  : deploy_image(enable_key_auth=True)   (route A)
     -> public_endpoint, apig_instance_id, runtime_api_key, runtime_id/app_id
  -> require real non-placeholder runtime/endpoint/key/APIG binding; shared gateway without a
     customer APIG id fails closed (or use explicit --apig-instance-id)
  -> [FR-19 phase 2] finalize mpa_meta (overwrite placeholders with real values)
  -> [route A] verify /health /readiness /agent-card
  -> print Studio A2A guidance
```

### 4.2 Chosen approach vs. alternatives

- **Chosen — extend the CLI to own SkillSpace + Tool + Runtime, default to `CreateRuntime`.** Matches the reference resource model and mpa-agent's native `r-*` delivery; keeps `deploy_image` as a `--compute-plane vefaas` fallback so the delivered route A path is not lost.
- **Alternative — keep Tool/SkillSpace external (route A only).** Rejected for this iteration: the user asked to align with the reference where the provisioner creates the Tool and obtains its id before creating the agent.
- **Alternative — drop `deploy_image` entirely.** Rejected: it is delivered, tested, and useful where an AgentKit Runtime is not desired; retained behind a flag.

### 4.3 Interfaces (additive to route A)

```text
veadk mpa create \
  ... (all route A options) ... \
  [--compute-plane runtime|vefaas]        # default runtime \
  [--tool-image <codex-worker-image>]     # create Tool when set and no --agentkit-tool-id \
  [--mpa-agent-id mi-*]                   # omitted => generate mi-<12 lowercase alnum> \
  [--tool-name <name>]                    # debug override; default mi-* with '-' mapped to '_' \
  [--tool-role-name IDRoleForArkClawShareAgent] \
  [--skill-space-name <name>] [--skill-space-id ss-*] \
  [--runtime-role-name <role>] [--runtime-name <name>] # default mpa-agent-id \
  [--min-instance 1] [--max-instance 1] \
  [--apig-instance-id <gateway-id>]       # explicit dedicated customer APIG for IM routing \
  [--agentkit-tool-id t-*]                # when set, skip CreateTool (route A reuse)
```

`--dry-run` extends to print the planned SkillSpace/Tool/compute-plane actions and the resolved env (secrets masked), performing no cloud or DB writes.

### 4.4 SDK facts (verified live in account 2112682748)

- Tools: `agentkit.sdk.tools.client.AgentkitToolsClient` — `create_tool`, `get_tool`, `list_tools`; `CreateToolRequest` accepts `image_url`, `command`, `port`, `tool_type`, `role_name`, `skill_space_id`, `authorizer_configuration`, `network_configuration`, `envs`, `client_token`.
- Runtime: `agentkit.sdk.runtime.client.AgentkitRuntimeClient` — `create_runtime`, `release_runtime`, `get_runtime`, `list_runtime_instances`, `update_runtime`; `CreateRuntimeRequest` has `artifact_type`, `artifact_url`, `tool_id`, `role_name`, `authorizer_configuration`, `network_configuration`, `envs`, `min_instance`, `max_instance`, `client_token`.
- Skills: `agentkit.sdk.skills.client.AgentkitSkillsClient` — `create_skill_space`, `get_skill_space`, `list_skill_spaces`.
- Existing Codex worker Tool contract (from `t-yeslt9bv9ckgnctgwaaf`, image `mpa_codex_worker:apihelpers-b3818f5-...`): `ToolType=Private`, `command=/opt/gem/run.sh`, `port=8000`, `cpu 2000/mem 4096`, `role IDRoleForArkClawShareAgent`, public+private APIG endpoints, key auth.

### 4.5 State, data, idempotency, rollback

- Idempotency keys: SkillSpace by name; Tool and Runtime by exact name. A single match is reused, non-Ready Tool state is awaited, and Runtime configuration is converged through `UpdateRuntime(..., ReleaseEnable=True)` before waiting for a newer Ready version. Multiple exact matches are an explicit ambiguity error.
- `mpa_meta`: phase 1 writes all seven required fields with placeholders; phase 2 overwrites only the deploy-bound fields after all real values pass completeness checks. `runtime_id` source depends on `--compute-plane`.
- Rollback: on post-creation failure, surface created `ss-*`/`t-*`/`r-*` ids. Full auto-teardown is out of scope; phase-1 placeholders may remain for an idempotent retry but are never reported as a completed binding.

### 4.6 Permissions and security

- Adds AgentKit Tools/Skills/Runtime create permissions to the route A credential set (VeFaaS + APIG + CR). RDS remains `Describe`-only and unused.
- Secret handling unchanged: hidden prompts, `--dry-run` masking, never logged; no control-plane credentials injected into the runtime.

### 4.7 Compatibility and affected callers

- Additive CLI options; `--compute-plane runtime` becomes the default, which **changes default behavior** versus route A (which always used `deploy_image`). This is a deliberate, approved behavior change scoped to `veadk mpa create`; `--compute-plane vefaas` reproduces route A exactly.
- `VeFaaS.deploy_image` signature is unchanged from route A (already extended and compatibility-guarded by AC-10).
- No mpa-agent source/image/API change.

## 5. Edge Cases

| Scenario | Handling |
| --- | --- |
| Neither `--tool-image` nor `--agentkit-tool-id` in runtime mode | Fail validation before any cloud or database write. |
| `--tool-image` and `--agentkit-tool-id` both set | Prefer the explicit `--agentkit-tool-id`; warn that `--tool-image` is ignored. |
| Tool with target name exists but not Ready | Wait for Ready up to a bounded timeout; fail with the tool id if it never readies. |
| Multiple exact-name Tools or Runtimes exist | Fail as ambiguous; never bind an arbitrary resource. |
| Neither `--skill-space-name` nor `--skill-space-id` | Omit `SKILL_SPACE_ID`; runtime runs without skill space. |
| `--compute-plane runtime` but artifact type unknown | Fail before create with a clear message; do not create a half-wired runtime. |
| Runtime never reaches Ready | Fail with runtime id and last status; leave phase-1 placeholders unfinalized for explicit retry/cleanup. |
| Re-run after partial failure | Reuse existing SkillSpace/Tool/Runtime by name/token; phase-1 pre-seed is fill-empty, phase-2 finalize overwrites placeholder fields. |
| Runtime startup fails with `GetMpaInstanceConf 403` | Root cause of the smoke failure: seeding after release. Fixed by FR-19 phase-1 pre-seed before compute-plane create. |
| Runtime reports shared gateway and empty `GatewayInstanceId` | Fail closed before phase-2 finalization unless a dedicated customer gateway is supplied through `--apig-instance-id`; never choose another listed gateway. |
| `--dry-run` | Print SkillSpace/Tool/compute-plane plan + masked env; no writes. |

## 6. Affected Files

- `veadk/cli/cli_mpa.py` — add `--compute-plane`, `--tool-image`, `--tool-name`, `--skill-space-name`, runtime options; orchestrate SkillSpace → Tool → pre-seed → compute-plane → finalize-seed → verify (FR-19).
- `veadk/integrations/mpa/mpa_tool.py` (new) — CreateTool/reuse-by-name helper mirroring the verified Codex worker Tool contract.
- `veadk/integrations/mpa/mpa_skill_space.py` (new) — create/select Skill Space helper.
- `veadk/integrations/mpa/mpa_runtime.py` (new) — `CreateRuntime`/`ReleaseRuntime`/wait-Ready helper (`ArtifactType="image"`, verified) and result normalization to `(public_endpoint, apig_instance_id, runtime_api_key, runtime_id)`.
- `veadk/integrations/mpa/mpa_meta_seed.py` — add an overwrite update path (`overwrite_fields`) for FR-19 phase 2, distinct from fill-empty.
- `veadk/integrations/mpa/mpa_provision.py` — extend params/env for skill space + tool image; provide placeholder values for phase-1 pre-seed.
- `veadk/integrations/ve_faas/ve_faas.py` — unchanged (vefaas fallback reused).
- `tests/cli/test_cli_mpa.py`, `tests/integrations/test_mpa_tool.py`, `test_mpa_skill_space.py`, `test_mpa_runtime.py`, `test_mpa_meta_seed.py` (new/extended) — stubbed SDK unit tests.
- `prd-spec/features/mpa-agent-oneclick-provision/` — this bilingual design.

## 7. Acceptance Criteria and Tracking

Route A AC-1..AC-10 remain green (unchanged code paths). New:

| Requirement | Task | Acceptance Criterion | Test / Verification | Result |
| --- | --- | --- | --- | --- |
| FR-12/13 | T-10 | `AC-11`: With `--tool-image` and no tool id, CreateTool is invoked with the verified contract and returns `t-*`; a single exact-name tool is reused/awaited and duplicate exact names fail. | `uv run pytest tests/integrations/test_mpa_tool.py` | pass (2026-09-11) |
| FR-12/13 | T-10b | `AC-11b`: Omitting agent/tool ids generates a valid unique `mi-*`, derives a dedicated `mi_*` Tool name and agent-derived Runtime name, and invokes CreateTool before CreateRuntime; missing Tool input fails before DB/cloud writes. | `uv run pytest tests/cli/test_cli_mpa.py -k generated_identity` | pass (2026-09-11) |
| FR-14 | T-11 | `AC-12`: `--skill-space-name` creates or selects a space and injects `SKILL_SPACE_ID`; absent both options, it is omitted. | `uv run pytest tests/integrations/test_mpa_skill_space.py` | pass (2026-09-11): test_mpa_skill_space 3/3 |
| FR-15/16 | T-12 | `AC-13`: `--compute-plane runtime` creates or converges the exact-name Runtime, releases it, waits for the current/newer Ready version, and normalizes endpoint/apig/key/runtime_id; duplicate exact names fail; `ArtifactType="image"`. | `uv run pytest tests/integrations/test_mpa_runtime.py` | pass (2026-09-11); ArtifactType=image verified live |
| FR-15 | T-12b | `AC-14`: `--compute-plane vefaas` reproduces route A exactly (deploy_image path). | `uv run pytest tests/cli/test_cli_mpa.py -k vefaas` | pass (2026-09-11) |
| FR-17/19 | T-13 | `AC-15`: Order SkillSpace→Tool→pre-seed→plane→binding completeness→finalize-seed→verify; pre-seed occurs before compute-plane create. | `uv run pytest tests/cli/test_cli_mpa.py -k orchestration` | pass (2026-09-11) |
| FR-18/20 | T-14 | `AC-16`: runtime/app id is plane-correct; APIG id is endpoint-derived or explicitly supplied; shared gateway without an id fails closed and does not finalize placeholders. | `uv run pytest tests/cli/test_cli_mpa.py -k gateway` | pass (2026-09-11) |
| FR-19 | T-17 | `AC-19`: Phase-1 seed writes a complete placeholder row; phase-2 overwrites only deploy-bound fields with real values. | `uv run pytest tests/integrations/test_mpa_meta_seed.py` | pass (2026-09-11) |
| all | T-15 | `AC-17`: Real E2E provisions Tool/Runtime, reaches Ready, and exercises Studio A2A plus two contexts. | Manual real run + Studio | partial/blocked: runtime and two distinct worker sessions passed; A2A final result fails on the selected image's ADK session revision conflict; Feishu also lacks a dedicated customer APIG id/credentials |
| all | T-16 | `AC-18`: pre-commit + CLI/unit regression pass; mpa-agent repo unchanged by this implementation. | `uv run pre-commit run --files <feature files>`; targeted MPA suite; `uv run pytest tests/cli` | pass: 57 MPA tests; 1282 CLI passed/4 skipped; pre-commit hooks passed |

## 8. Risks and Open Questions

- **OQ-4 — Default compute plane — RESOLVED.** Default to `--compute-plane runtime` (`CreateRuntime` → `r-*`) to match the reference and mpa-agent's native model; `--compute-plane vefaas` reproduces route A.
- **OQ-5 — CreateTool env completeness — RESOLVED.** Clone the env set from a reference Codex worker Tool (e.g. `t-yeslt9bv9ckgnctgwaaf`) as the template, allowing per-key overrides. This is the most reliable path to a Ready sandbox.
- **OQ-6 — ArtifactType value — RESOLVED (verify in implementation).** The user approved a real smoke `CreateRuntime` during implementation on the test account (2112682748) to confirm the image `ArtifactType`/`ArtifactUrl` contract; findings are recorded back into this design.
- **Risk — real-resource cost.** Runtime/Tool/APIG creation is billable and not trivially reversible; `--dry-run` first, then confirm before real create. The test account (2112682748) is authorized for verification runs.
- **Blocker — selected mpa-agent image A2A result.** The runtime and delegated workers complete, but A2A replies fail with `The session has been modified in storage since it was loaded`; Studio cannot yet complete an interactive chat until the image fixes ADK session revision coordination.
- **Blocker — shared APIG cannot identify the customer IM gateway.** The verified Runtime reports `GatewayMode=Shared` and empty `GatewayInstanceId`; the endpoint does not map to an account APIG id. `--apig-instance-id` is the explicit adapter, but automatic dedicated gateway allocation is outside this implementation.
- **Blocker — Feishu verification.** Feishu credentials/bot installation and a dedicated customer APIG id were not available, so group-chat behavior remains unverified.
- Route A open items (control-plane `CreateMpaInstance` out of scope; CLI-side seeding accepted) remain as decided.

## 9. Review and Delivery Record

- Review status: reviewed via `review-spec` on 2026-09-11; OQ-4/OQ-5/OQ-6 resolved with the user. Status advanced to `approved` on 2026-09-11.
- Decisions: default compute plane `runtime`; CreateTool env cloned from a reference worker Tool; `ArtifactType` confirmed by a smoke `CreateRuntime` during implementation on test account 2112682748.
- Predecessor route A remains delivered and unchanged; this version is additive except the default compute plane.
- Review fixes: exact-name Tool/Runtime retries are deterministic; non-Ready Tool and newer Runtime versions are awaited; APIG resolution fails closed instead of selecting an unrelated gateway.
- Open blockers: Studio A2A final responses are blocked by the selected image's ADK session revision conflict; Feishu group chat is blocked by missing credentials/bot installation and a dedicated customer APIG id.
- Remaining scope: final local gates, commit, and push. The image/APIG/Feishu blockers are recorded as external residual risks, not reported as passing.
