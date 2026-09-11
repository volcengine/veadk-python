# One-Click mpa-agent Provisioning from a Prebuilt Image Design

## Metadata

- **Change ID:** `mpa-agent-oneclick-provision`
- **Created / Revised:** 2026-09-10 / 2026-09-10
- **Lifecycle status:** `approved`
- **Language counterpart:** [2026-09-10-mpa-agent-oneclick-provision-design.zh.md](2026-09-10-mpa-agent-oneclick-provision-design.zh.md)
- **Related component specs:** none created yet; a new CLI contract surface is introduced by this change (see §6). No existing component contract under `specs/` is modified.
- **Predecessor / Successor:** none.

## 1. Overview

### 1.1 Problem / Background

`mpa-agent` (`~/workspace/bytedance/mpa/mpa-agent`) is a FastAPI + veadk enterprise agent that ships as an AgentKit image (`Dockerfile` `CMD ["python", "main.py"]`, `agentkit.yaml`). Standing up one runnable instance today requires an out-of-band control-plane record: at startup `app/services/mpa_meta.py` calls the Arkclaw TOP action `GetMpaInstanceConf` (`app/client/arkclaw.py`, service `arkclaw`, version `2026-03-01`) to resolve a `mi-*` instance config (`account_id`, `resource_account_id`, `runtime_id`, `public_endpoint`, `private_endpoint`, `runtime_api_key`, `apig_instance_id`, and optional `ov_resource_id` / `ov_api_key`).

A repository-wide search across `arkclaw`, `mpa`, and `veadk-python` confirms the **create side of that record does not exist in any local checkout** — only the read client, its consumer (`app/services/mpa_meta.py`), tests, and `docs/mpa-agent-api.md` reference `GetMpaInstanceConf`. Consequently there is no self-contained way to provision a working `mpa-agent` from the veadk side.

At the same time the required backing resources are already externally managed:

- **PostgreSQL:** veadk never creates an RDS instance or database. `veadk/memory/short_term_memory_backends/postgresql_backend.py` only runs `CREATE SCHEMA IF NOT EXISTS`; the deploy IAM policy (`veadk/cli/frontend_deploy_policy.py`) grants `rds_postgresql:DescribeDBInstances/DescribeDBAccounts/DescribeDatabases` and no create action. The database is a precondition; the runtime auto-creates its tables.
- **OpenViking:** `mpa-agent` consumes an OpenViking Server over HTTP via `OPENVIKING_URL` / `OPENVIKING_RESOURCE_ID` / `OPENVIKING_API_KEY` (`app/core/config.py`); it does not create the `ov-*` resource. veadk has no Python `CreateMemorydbInstance` implementation (`veadk/integrations/ve_viking_db_memory/ve_viking_db_memory.py` exposes only collection/message/search actions). The resource is a precondition.

### 1.2 Goals

Provide a self-contained, control-plane-independent way to stand up one `mpa-agent` instance and chat with it from AgentKit Studio, using a prebuilt `mpa-agent` image plus externally supplied PostgreSQL and OpenViking parameters, without modifying the `mpa-agent` image or code.

- Add a `veadk mpa` CLI command group with `veadk mpa create` that deploys a specified image and wires all runtime configuration from external parameters.
- Remove the hard dependency on the unavailable `GetMpaInstanceConf` create side by seeding the `mpa_meta` table so the runtime's own startup skips the TOP call.
- Verify the deployed instance is healthy and Studio-connectable, and that existing `mpa-agent` capabilities (REST sessions, per-session Codex sandboxes, IM/Feishu group chat) continue to work.

### 1.3 Non-Goals

- Not creating PostgreSQL RDS instances/databases or OpenViking `ov-*` resources (external preconditions; see §1.1).
- Not implementing or calling a control-plane `CreateMpaInstance` action (deferred; tracked as an open question in §8).
- Not modifying `mpa-agent` source, image, or its public HTTP API.
- Not creating identity resources. In the veadk provisioning scenario the `arkclaw-{space}-userpool/-client/-workload` resources are **not used**: startup identity init is disabled with `IDENTITY_STARTUP_ENABLED=false`, and `CLAW_SPACE_ID` is adapted from the account id (see FR-10).
- Not building OpenViking collection creation into this command (the OpenViking Server path is consumed as-is).

## 2. Scenarios

### Scenario 1: Operator provisions an instance from an image

**Given** a prebuilt `mpa-agent` image URL, an existing PostgreSQL database (host/port/db/user/password), an existing OpenViking resource (`url`/`resource_id`/`api_key`), model credentials, and identity/AgentKit identifiers.
**When** the operator runs `veadk mpa create` with those parameters.
**Then** the CLI deploys the image to VeFaaS behind APIG, seeds the `mpa_meta` row, injects the runtime env, and reports the public endpoint, the A2A agent-card URL, and the runtime API key location, with `/health` and `/readiness` passing.

### Scenario 2: Chat from Studio

**Given** a successfully provisioned instance with a reachable A2A agent-card at `<endpoint>/.well-known/agent-card.json`.
**When** the operator connects it as a remote agent in AgentKit Studio (`veadk studio`) and sends a message.
**Then** Studio exchanges A2A `message/send` / `message/stream` with the instance and renders the streamed reply, reusing the same veadk Agent/Runner and PostgreSQL session store.

### Scenario 3: Different sessions get different sandboxes

**Given** a provisioned instance with the Codex sandbox tool enabled (`AGENTKIT_TOOL_ID` set, `DISABLE_CODEX_SANDBOX` not `true`).
**When** two distinct sessions each trigger a `sandbox_task` delegation.
**Then** each session gets its own Codex Worker sandbox derived from `sha256(app_name:user_id:session_id)` (`app/integrations/agentkit_sandbox.py:derive_sandbox_session_id`), unchanged by this feature.

### Scenario 4: Feishu bot group chat

**Given** `FEISHU_APP_ID` / `FEISHU_APP_SECRET` supplied interactively (or omitted for later QR binding).
**When** the instance starts.
**Then** if supplied, the runtime auto-upserts a Feishu channel binding and registers the IM Gateway bot (`app/services/channel/service.py`); if omitted, QR binding remains available; group chat works via `POST /api/v1/channels/events`.

### Scenario 5: Existing veadk commands unaffected

**Given** the new `mpa` command group is registered.
**When** the operator runs any existing command (`veadk deploy`, `veadk frontend`, `veadk studio`, `veadk agentkit`, `veadk kb`, ...).
**Then** behavior is identical to before this change.

## 3. Functional Requirements

- **FR-1 — New `mpa` command group, additive.** A new `veadk mpa` `click` group is registered in `veadk/cli/cli.py` alongside existing commands without altering any of them; the console entry point (`pyproject.toml` `veadk = "veadk.cli.cli:veadk"`) is unchanged.
- **FR-2 — External parameters.** `veadk mpa create` accepts, via options and/or env fallbacks: image URL and container registry; provider/region; PostgreSQL connection (`PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD/PGSSLMODE/PGCHANNELBINDING`) or an equivalent DSN; OpenViking (`OPENVIKING_URL`, `OPENVIKING_RESOURCE_ID`, `OPENVIKING_API_KEY`); model (`MODEL_AGENT_PROVIDER/API_BASE/API_KEY/NAME`); identity (`CLAW_SPACE_ID`, `MPA_AGENT_ID`, `IDENTITY_REGION`); AgentKit (`AGENTKIT_TOOL_ID`, `AGENTKIT_TOOL_REGION`, `SKILL_SPACE_ID`); auth method; and optional Feishu (`FEISHU_APP_ID`, `FEISHU_APP_SECRET`).
- **FR-3 — Image deployment with key auth.** The command deploys the specified image to VeFaaS behind APIG by reusing `veadk/integrations/ve_faas/ve_faas.py:VeFaaS.deploy_image()` with key auth enabled. Because `deploy_image()` today neither enables key auth nor returns the gateway/key, it is extended in a backward-compatible way (new optional `enable_key_auth: bool = False` parameter; unchanged default behavior) so that, when requested, it enables key auth in `_create_application` and returns the public URL, application id, function id, plus the APIG gateway id and the key-auth API key. Existing callers that omit the new parameter are unaffected (AC-10).
- **FR-4 — `mpa_meta` seeding to skip the TOP call.** Using the provided PostgreSQL connection, the command writes the `mpa_meta` row so that `app/services/mpa_meta.py:mpa_instance_conf_ready()` is satisfied and `GetMpaInstanceConf` is skipped at startup. Required fields and their veadk-scenario sources:
  - `account_id`: resolved from the deploy credentials' account id.
  - `resource_account_id`: same account id (single-account veadk scenario).
  - `runtime_id`: the VeFaaS application id returned by `deploy_image`.
  - `public_endpoint`: the released application system URL (`framework.url.system_url`).
  - `private_endpoint`: set equal to `public_endpoint` in the veadk scenario (public endpoint is authoritative; see FR-11). This keeps the field non-empty so `mpa_instance_conf_ready()` passes and the runtime's `choose_endpoint` resolves a usable base.
  - `runtime_api_key`: the key-auth API key from FR-3.
  - `apig_instance_id`: the APIG gateway id that veadk auto-creates/reuses together with the function (obtained from the release `CloudResource` `framework.triggers[0].DetailedConfig.GatewayId`, mirroring `VeFaaS.get_application_route`). Confirmed: veadk provisions APIG alongside the function; the gateway id is not an external precondition.

  Seeding is idempotent (fill-empty semantics equivalent to the runtime's `MpaMetaStore.fill_empty`), must not overwrite non-empty fields, and must assert all seven fields are non-empty before writing (otherwise abort without leaving a half-usable instance).
- **FR-5 — Runtime env injection.** All resolved configuration is set as VeFaaS function environment variables (create + release), matching the keys `mpa-agent` reads at startup (`.env.example`, `docs/mpa-agent-api.md` §9). This includes `IDENTITY_STARTUP_ENABLED=false` (FR-10), `MPA_CODEX_WORKER_DEFAULT_MODEL=<model-name>` so delegated Codex turns do not fall back to the literal `auto`, and `MPA_CODEX_WORKER_ENDPOINT_PREFERENCE`/endpoint choice consistent with the public-endpoint decision (FR-11).
- **FR-6 — Post-deploy verification.** After release the command probes `GET /health` and `GET /readiness` and confirms the A2A agent-card is reachable at `<public_endpoint>/.well-known/agent-card.json`; failures are reported with actionable detail and do not leave secrets in logs.
- **FR-7 — Studio chat enablement.** The command prints the exact endpoint, agent-card URL, and API-key handling needed to connect the instance as a remote A2A agent in `veadk studio`. Chat, multi-session/multi-sandbox, and IM group chat rely only on the runtime and are not gated by this command.
- **FR-8 — Interactive, optional Feishu secret.** When `--feishu-app-id` is provided without a secret, the CLI prompts for `FEISHU_APP_SECRET` with hidden input; Feishu is fully optional; the secret never appears in stdout or logs.
- **FR-9 — Non-regression of `mpa-agent`.** No change to `mpa-agent` source or image is performed by this feature. The selected image remains responsible for its REST/A2A session consistency, Codex event projection, scheduled-task, and IM behavior. Provisioning must not claim full compatibility when real E2E exposes an image-level failure; it reports the image/tag and the blocking evidence instead.
- **FR-10 — Identity adaptation (no arkclaw identity resources).** The veadk scenario does not use `arkclaw-{space}-userpool/-client/-workload`. The command injects `IDENTITY_STARTUP_ENABLED=false` so startup identity initialization short-circuits, derives `CLAW_SPACE_ID` from the account id, and sets `A2A_TIP_VERIFY_ENABLED=false` because no TIP issuer exists in this topology. The Runtime remains protected by mandatory APIG key auth; disabling the inner TIP gate permits Studio's server-side authenticated proxy to chat without exposing the Runtime key to the browser.
- **FR-11 — Public endpoint in veadk scenario.** The provisioning flow treats the released public application URL as authoritative for `public_endpoint`, `private_endpoint` (mirrored), the agent-card base, and the Codex worker endpoint preference. No private-network endpoint is required.

## 4. Design and Contract Impact

### 4.1 Responsibilities and boundaries

The feature is a veadk-side **orchestration + configuration** command. It owns: parameter collection/validation, image deployment via the existing VeFaaS/APIG integrations, `mpa_meta` seeding, env assembly, and verification. It does **not** own: creating PostgreSQL/OpenViking/identity resources, or the `mi-*` control-plane record.

### 4.2 Startup contract that drives the design

`mpa-agent` startup (`app/main.py` lifespan → `get_mpa_meta_service().initialize()`):

1. `ensure_schema()` creates the `mpa_meta` table if absent.
2. Requires non-empty `MPA_AGENT_ID`.
3. If the cached `mpa_meta` row already has all seven required fields (`mpa_instance_conf_ready`), it **skips `GetMpaInstanceConf`**; otherwise it calls the TOP action, which fails without a control-plane `mi-*` record.
4. Lazily ensures the IM Gateway service from `apig_instance_id` (`ensure_im_gateway_service`).

Seeding the row (FR-4) is therefore the mechanism that makes provisioning self-contained under the current architecture.

### 4.3 Chosen approach vs. alternatives

- **Chosen — seed `mpa_meta` + inject env (this design).** Uses only locally available capabilities; no dependency on an unavailable control-plane action. The CLI computes the seven fields from the deploy result plus provided parameters. The seeding step is written behind a small internal function boundary so a future control-plane backend can replace it without touching the command flow.
- **Alternative A — call a control-plane `CreateMpaInstance`.** Rejected for now: the action is absent from every local checkout; its name, fields, version, and IAM requirements are unknown. Tracked in §8 as the eventual "正统" path.
- **Alternative B — patch `mpa-agent` to make `GetMpaInstanceConf` optional.** Rejected: violates the non-goal of not modifying `mpa-agent`.

### 4.4 Interfaces

New CLI surface (additive):

```text
veadk mpa create \
  --image <cr-image-url> \
  --registry-name <cr-registry> \
  [--provider volcengine|byteplus] [--region cn-beijing] \
  --mpa-agent-id mi-xxxx \
  [--claw-space-id csi-xxxx]   # optional; defaults to csi-<account_id> (FR-10) \
  --pg-host ... --pg-port 5432 --pg-database ... --pg-user ... --pg-password ... \
  [--pg-sslmode require] [--pg-channel-binding require] \
  --model-provider openai --model-api-base ... --model-api-key ... --model-name ... \
  [--openviking-url ...] [--openviking-resource-id ov-xxx] [--openviking-api-key ...] \
  --agentkit-tool-id ... [--agentkit-tool-region cn-beijing] [--skill-space-id ...] \
  [--auth-method none|api-key|oauth2] \
  [--feishu-app-id cli_xxx] [--feishu-app-secret ...] \
  [--app-name mpa-agent] [--gateway-name ...] [--dry-run]
```

`--dry-run` resolves and prints the plan (deploy target, env keys, `mpa_meta` fields — secrets masked) without mutating cloud or database state.

### 4.5 State, data, and idempotency

- The only datastore this command writes is the external PostgreSQL `mpa_meta` table (one row keyed by `mpa_agent_id`), using fill-empty semantics equivalent to `app/stores/mpa_meta.py:MpaMetaStore.fill_empty`, with a pre-write assertion that all seven required fields are non-empty.
- The veadk-side `mpa_meta` table definition (columns, types, server defaults) mirrors `app/stores/mpa_meta.py` exactly. A comment records that a change to the runtime's table shape must be synchronized here.
- Re-running `veadk mpa create` with the same `--app-name` reuses the existing VeFaaS application (deploy is idempotent by app name in `VeFaaS.deploy`/`deploy_image`) and does not overwrite non-empty `mpa_meta` fields.

### 4.6 Permissions and security

- Requires cloud credentials able to deploy VeFaaS + APIG and reach the container registry (see `frontend_deploy_policy.py` for the reference action set; RDS is `Describe`-only and unused here).
- Secrets (`--pg-password`, `--model-api-key`, `--openviking-api-key`, `--feishu-app-secret`, runtime API key) are prompted with hidden input when interactive, masked in `--dry-run` output, and never logged. This aligns with the `secretless runtime` intent in `arkclaw-mpa`: the CLI injects only what the runtime needs and does not write control-plane credentials into the runtime.

### 4.7 Compatibility and affected callers

- Additive CLI command; no existing veadk command, public import, or generated project changes (FR-1, FR-9).
- `VeFaaS.deploy_image` gains one optional keyword parameter `enable_key_auth: bool = False` and an extended return value; the default preserves the current three-tuple behavior for existing callers (`CloudAgentEngine`, Studio). This is verified by a compatibility guard test (AC-10). The change is additive-only: no positional parameter is reordered.
- No `mpa-agent` API or image change.
- Studio connects via the already-exposed A2A surface (`app/a2a/app.py`, agent-card at `/.well-known/agent-card.json` with `A2A_MOUNT_PATH=/`).

## 5. Edge Cases

| Scenario | Handling |
| --- | --- |
| `mpa_meta` row already complete | Skip seeding; log skip; proceed to verification (idempotent). |
| Partial `mpa_meta` row exists | Fill only empty required fields; never overwrite non-empty values. |
| Any required field unresolved before seeding | Abort with a specific message; do not write a partial row. |
| PostgreSQL unreachable | Fail fast before deploy with a clear connection error; no cloud mutation. |
| OpenViking params omitted | Allowed; runtime runs without OpenViking tools (they mount only when URL+key set). |
| Feishu secret omitted | Allowed; skip auto-bind; QR binding remains available at runtime. |
| `--claw-space-id` omitted | Derive `csi-<account_id>` (FR-10); `IDENTITY_STARTUP_ENABLED=false` keeps identity init off, so no arkclaw identity pool is required. |
| Image sync still in progress on release | Reuse `deploy_image` bounded retry (`_release_application` retry loop). |
| Deploy fails midway | Report the failure with redacted logs; resources created before the failure are surfaced for manual cleanup (parity with `deploy`'s cleanup is a follow-up if `deploy_image` lacks it). |
| Re-run with same app name | Reuse existing application; update code/env; do not duplicate the function. |
| `--dry-run` | Print resolved plan with masked secrets; perform no cloud or DB writes. |
| Missing required parameter | Fail with a specific message naming the missing option/env. |

## 6. Affected Files

- `veadk/cli/cli_mpa.py` — new `mpa` command group and `create` command (orchestration, parameter handling, `mpa_meta` seeding for the first version, verification).
- `veadk/cli/cli.py` — import and `veadk.add_command(mpa)` (single additive registration).
- `veadk/integrations/ve_faas/ve_faas.py` — extend `deploy_image` with `enable_key_auth` + extended return (backward compatible); reuse `_create_application`, `get_application_route`, release `CloudResource` parsing.
- `veadk/integrations/ve_apig/ve_apig.py` — reused, not modified.
- `tests/cli/test_cli_mpa.py` — new unit tests with stubbed cloud SDK and in-memory/SQLite `mpa_meta`.
- `prd-spec/features/mpa-agent-oneclick-provision/` — this bilingual design.
- Component spec: no existing `specs/<component>/` contract changes; if a durable CLI contract is desired later, add `specs/mpa-provisioning/` in a follow-up (out of scope here).

## 7. Acceptance Criteria and Tracking

| Requirement | Task | Acceptance Criterion | Test / Verification Command | Result / Evidence |
| --- | --- | --- | --- | --- |
| FR-1 | T-1 | `AC-1`: `veadk mpa --help` lists `create`; all pre-existing top-level commands still resolve. | `uv run veadk mpa --help` and `uv run veadk --help` | pass (2026-09-11): mpa lists create; `veadk --help` shows mpa + existing commands |
| FR-2, FR-8 | T-2 | `AC-2`: Missing required params fail with a named error; `--feishu-app-id` without secret prompts hidden input; secrets masked in `--dry-run`. | `uv run pytest tests/cli/test_cli_mpa.py -k params` | pass (2026-09-11): test_cli_mpa 6/6 |
| FR-3 | T-3 | `AC-3`: With a stubbed VeFaaS/APIG client, deploy is invoked via `deploy_image(enable_key_auth=True)` and public endpoint, apig gateway id, and key are captured. | `uv run pytest tests/cli/test_cli_mpa.py -k deploy` | pass (2026-09-11): full_flow_orchestration + deploy_image key-auth |
| FR-3 | T-3b | `AC-10`: `deploy_image()` called without `enable_key_auth` returns the unchanged three-tuple and enables no key auth (compatibility guard). | `uv run pytest tests/ -k deploy_image_compat` | pass (2026-09-11): test_deploy_image_compat_returns_three_tuple_without_key_auth |
| FR-4, FR-11 | T-4 | `AC-4`: Seeding writes the seven required fields (`private_endpoint` mirrors `public_endpoint`); a pre-complete row is left unchanged; a partial row is filled only in empty fields; any unresolved field aborts before write. | `uv run pytest tests/cli/test_cli_mpa.py -k seed` | pass (2026-09-11): test_mpa_meta_seed 6/6 |
| FR-5, FR-10 | T-5 | `AC-5`: Assembled env contains every key `mpa-agent` reads at startup, including `IDENTITY_STARTUP_ENABLED=false` and `CLAW_SPACE_ID=csi-<account_id>` when not supplied; no secret is logged. | `uv run pytest tests/cli/test_cli_mpa.py -k env` | pass (2026-09-11): test_mpa_provision_env 6/6 |
| FR-6 | T-6 | `AC-6`: Verification passes only when `/health`, `/readiness`, and the agent-card all respond; failures are reported without secrets. | `uv run pytest tests/cli/test_cli_mpa.py -k verify` | pass (2026-09-11): test_mpa_verify 4/4 |
| FR-7 | T-7 | `AC-7`: Command output includes the agent-card URL and Studio connection guidance; documented manual Studio chat succeeds against a real instance, with distinct sessions getting distinct sandboxes and Feishu group chat working. | Manual: `veadk studio` connect + one message | partial/blocked: guidance and distinct session→sandbox mapping verified; selected image fails the final A2A result on an ADK session revision conflict; Feishu lacks credentials/bot installation and a dedicated customer APIG id |
| FR-9 | T-8 | `AC-8`: No file under the `mpa-agent` repo is modified by this change; existing veadk command tests pass. | `git -C ~/workspace/bytedance/mpa/mpa-agent status --porcelain` empty; `uv run pytest tests/cli` | pass (2026-09-11): mpa-agent porcelain empty; tests/cli 1273 passed, 4 skipped |
| all | T-9 | `AC-9`: Repository gates pass (pre-commit + unit tests). | `pre-commit run -a` and `uv run pytest` | pass (2026-09-11): pre-commit on changed files (ruff-check/format/gitleaks) Passed; new suites 25/25 |

Check states use `pass` / `fail` / `blocked` / `not_run` / `not_applicable`. Record execution date, tested diff range, and brief results when run.

## 8. Risks and Open Questions

- **OQ-1 — Control-plane `CreateMpaInstance` (not required for this design).** The create side of the `mi-*` record is absent from all local checkouts. It is intentionally out of scope: the veadk-version `mpa-agent` needs no control-plane record. Route A (CLI-side `mpa_meta` seeding) is the accepted delivery path. Kept only as a note for a future non-veadk deployment.
- **OQ-2 — CLI-side `mpa_meta` seeding — RESOLVED (accepted).** The user approved having the CLI deliver the `mi-*` meta configuration directly; the veadk-version `mpa-agent` runs without a control-plane record. This is the accepted mechanism.
- **Resolved — APIG instance id source.** Confirmed in code: veadk provisions/reuses the APIG serverless gateway together with the function during deploy (`VeFaaS._create_application` + `ve_apig` create/reuse; gateway id readable from release `CloudResource` `framework.triggers[0].DetailedConfig.GatewayId`, per `get_application_route`). `apig_instance_id` is therefore produced by the deploy flow, not an external input.
- **Resolved — Endpoint choice.** In the veadk scenario `public_endpoint` is authoritative and `private_endpoint` mirrors it (FR-11); no private network endpoint is required.
- **Resolved — Identity.** The veadk scenario sets `IDENTITY_STARTUP_ENABLED=false` and derives `CLAW_SPACE_ID=csi-<account_id>`, so `arkclaw-{space}-userpool/-client/-workload` are not used (FR-10); startup identity init short-circuits at `app/identity/service.py:166`.
- **Risk — secretless runtime.** Injected env carries model/OpenViking/runtime keys; keep control-plane credentials out of the runtime and mask all secrets, consistent with `arkclaw-mpa` guidance.
- **Risk — `deploy_image` failure cleanup.** Unlike `deploy`, `deploy_image` lacks `keep_failed_deploy`/rollback. Either add parity cleanup when extending it, or surface created resources for manual cleanup (edge-case table).

## 9. Review and Delivery Record

- Review status: reviewed via `review-spec` on 2026-09-10; P0 findings folded back into FR-3/FR-4/FR-10/FR-11, AC-10, and §4.7. Status advanced to `approved` on 2026-09-10.
- Resolved during review: APIG instance id source (deploy-produced), endpoint choice (public), identity adaptation (`IDENTITY_STARTUP_ENABLED=false` + `csi-<account_id>`).
- User approval: granted on 2026-09-10 — CLI delivers the `mi-*` meta configuration directly (route A); the veadk-version `mpa-agent` requires no control-plane record. OQ-2 accepted; OQ-1 out of scope.
- Open blockers: Studio A2A final response in the selected image; Feishu credentials/bot installation and dedicated customer APIG id. The orchestration-alignment design records the current details.
- Executed checks: route A unit/CLI coverage passed; later alignment verification is tracked by the 2026-09-11 design and evidence reports.
- Remaining scope: see the 2026-09-11 orchestration-alignment design.
