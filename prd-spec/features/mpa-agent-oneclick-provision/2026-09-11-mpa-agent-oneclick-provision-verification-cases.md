# mpa-agent One-Click Provisioning — Functional Verification Cases

> Related design: `2026-09-10-mpa-agent-oneclick-provision-design.md` (`approved`)
> Purpose: dev-loop step 2 up-front design and step 7 execution — executable verification cases.
> Status: `executed-with-blockers` (unit/CLI green; real results recorded in §3.1).

## 1. Evidence retention

- Unit-test evidence: `uv run pytest` output + covered assertions, saved under `prd-spec/features/mpa-agent-oneclick-provision/evidence/<case-id>.log`.
- CLI-behavior evidence: command stdout/stderr (secrets masked) in the same directory.
- Real Studio E2E evidence: request/response summary, SSE snippets, screenshot paths in the same directory; must contain no real secrets.

## 2. Coverage matrix (requirement → case)

| Requirement | Case | Level |
| --- | --- | --- |
| FR-1 | VC-1 | unit/CLI |
| FR-2 | VC-2, VC-3 | unit/CLI |
| FR-3 | VC-4 (key-auth deploy), VC-5 (AC-10 compat guard) | unit |
| FR-4 | VC-6, VC-7, VC-8, VC-9 | unit |
| FR-5 | VC-10, VC-23 | unit + real |
| FR-6 | VC-11, VC-12 | unit |
| FR-7 | VC-13 (output guidance), VC-18 (real Studio chat) | unit + real |
| FR-8 | VC-3 (hidden input), VC-14 (dry-run masking) | unit/CLI |
| FR-9 | VC-15 (mpa-agent unchanged), VC-16 (existing-command regression) | gate/regression |
| FR-10 | VC-10 (IDENTITY_STARTUP_ENABLED=false + csi-<account_id>) | unit |
| FR-11 | VC-7 (private mirrors public) | unit |
| key regression | VC-16, VC-19 (distinct sessions → distinct sandboxes), VC-20 (Feishu group chat) | regression + real |
| FR-12/13 | VC-21 (generated identity + dedicated Tool/Runtime), VC-22 (missing Tool input has no writes), VC-24 (retry idempotency) | unit/CLI |
| FR-18 | VC-25 (APIG id resolution fails closed) | unit + real |

Every P0/P1 requirement (FR-1..FR-19) is covered by at least one case.

## 3. Case details

### Happy path

- **VC-1 (FR-1 command registration)**
  - Command: `uv run veadk mpa --help` and `uv run veadk --help`
  - Precondition: none
  - Expected: the `mpa` group lists `create`; `veadk --help` still lists all existing commands (deploy/init/create/frontend/studio/agentkit/kb, ...).
  - Pass: both exit 0; no subcommand missing.
  - On fail: return to T-12/T-1.

- **VC-4 (FR-3 key-auth deploy + resource capture)**
  - Command: `uv run pytest tests/cli/test_cli_mpa.py -k deploy`
  - Precondition: stub `VeFaaS`/`APIGateway`; stub release returns `framework.url.system_url` and `framework.triggers[0].DetailedConfig.GatewayId`.
  - Input: `enable_key_auth=True` path.
  - Expected: orchestration calls `deploy_image(..., enable_key_auth=True)`; captures `public_endpoint`, `apig_instance_id` (=GatewayId), `runtime_api_key`.
  - Pass: the four/five-tuple return is destructured correctly; `_create_application` receives `EnableKeyAuth=True`.
  - Evidence: `evidence/VC-4.log`.

- **VC-10 (FR-5/10/11 env assembly)**
  - Command: `uv run pytest tests/cli/test_cli_mpa.py -k env`
  - Input: omit `--claw-space-id`, omit `IDENTITY_STARTUP_ENABLED`.
  - Expected: assembled env contains all mpa-agent startup keys; `IDENTITY_STARTUP_ENABLED=false`; `A2A_TIP_VERIFY_ENABLED=false` (no TIP issuer, APIG key auth remains mandatory); `MPA_CODEX_WORKER_DEFAULT_MODEL=<model-name>`; `CLAW_SPACE_ID=csi-<account_id>`; endpoint keys use public.
  - Pass: key set equals the expected set; no secret appears in any log string.
  - Evidence: `evidence/VC-10.log`.

- **VC-13 (FR-7 Studio guidance output)**
  - Command: `uv run pytest tests/cli/test_cli_mpa.py -k guidance` (or dry-run output assertion)
  - Expected: success path stdout includes `public_endpoint`, `<endpoint>/.well-known/agent-card.json`, and how the runtime API key is handled.
  - Pass: all three present; the key value itself is masked.

### Error path

- **VC-2 (FR-2 missing required → named error)**
  - Command: `uv run pytest tests/cli/test_cli_mpa.py -k params` (one case each for missing `--image`/`--mpa-agent-id`/`--pg-*`/`--model-*`)
  - Expected: each exits with an error **naming the missing option** (not a generic traceback).
  - Pass: error message contains the concrete option name; exit != 0; no cloud/DB write.

- **VC-11 (FR-6 verification fails on any probe failure)**
  - Command: `uv run pytest tests/cli/test_cli_mpa.py -k verify`
  - Input: stub `/health` 200 but `/readiness` non-200; and agent-card 404.
  - Expected: verification result is fail, reporting which probe failed.
  - Pass: any failed probe fails the whole check; report text contains no secret.

- **VC-8 (FR-4 abort before write on unresolved field)**
  - Command: `uv run pytest tests/cli/test_cli_mpa.py -k seed_abort`
  - Input: `runtime_api_key` resolves to empty.
  - Expected: raise a named error before seeding; **write no row**.
  - Pass: DB has no inserted/updated row; error names the missing field.

- **VC-17 (PostgreSQL unreachable)**
  - Command: `uv run pytest tests/cli/test_cli_mpa.py -k pg_unreachable`
  - Input: connection string to an unreachable port.
  - Expected: fail fast **before deploy**; no cloud deploy call triggered.
  - Pass: VeFaaS deploy stub is called zero times; error is a connection error.

### Boundary

- **VC-6 (FR-4 empty row writes 7 fields)**: `-k seed` subcase, empty table → 7 fields written complete and correct.
- **VC-7 (FR-4/11 private mirrors public)**: assert `private_endpoint == public_endpoint`.
- **VC-9 (FR-4 idempotency)**: complete row not overwritten; partial row only fills empty fields, non-empty preserved.
- **VC-14 (FR-8 dry-run masking)**: `--dry-run` output contains the plan but all secrets masked; no cloud/DB write.
- **VC-5 (FR-3 AC-10 compat guard)**: `deploy_image()` without `enable_key_auth` → returns the original three-tuple `(url, app_id, function_id)`; `_create_application` receives `EnableKeyAuth=False`.

### Permission / environment isolation

- **VC-3 (FR-2/8 Feishu secret hidden input)**
  - Command: `uv run pytest tests/cli/test_cli_mpa.py -k feishu_prompt`
  - Input: pass `--feishu-app-id` without a secret.
  - Expected: triggers `click.prompt(hide_input=True)`; secret not echoed, not logged.
  - Pass: prompt invoked with `hide_input=True`; captured output has no secret plaintext.

### Cross-module / key regression (real, run in step 7/10)

- **VC-15 (FR-9 mpa-agent unchanged)**
  - Command: `git -C ~/workspace/bytedance/mpa/mpa-agent status --porcelain`
  - Pass: empty output.

- **VC-16 (FR-9 existing-command regression)**
  - Command: `uv run pytest tests/cli`
  - Pass: existing CLI tests all green (new cases do not break existing).

- **VC-18 (FR-7 real Studio chat)**
  - Steps: `veadk studio` → connect the instance agent-card as a remote A2A agent → send one message.
  - Expected: streamed reply renders.
  - Evidence: request/response summary + SSE snippet (redacted) in `evidence/VC-18.md`.

- **VC-19 (key regression: distinct sessions → distinct sandboxes)**
  - Steps: two distinct sessions each trigger `sandbox_task`.
  - Expected: the two sandbox_session_ids differ (derived from `sha256(app_name:user_id:session_id)`).
  - Evidence: two recorded sandbox ids (redacted).

- **VC-20 (key regression: Feishu group chat)**
  - Precondition: provide `FEISHU_APP_ID/SECRET` (or QR binding).
  - Steps: @ the bot in a group → observe the IM Gateway reply.
  - Expected: group session reused; reply delivered.
  - Evidence: inbound/outbound envelope summary (redacted).

### Generated identity and dedicated resources

- **VC-21 (FR-12/13 generated identity and per-agent resources)**
  - Command: `uv run pytest tests/cli/test_cli_mpa.py -k generated_identity`
  - Input: omit `--mpa-agent-id` and `--agentkit-tool-id`; provide `--tool-image`.
  - Expected: `mi-<12 lowercase alnum>` is used in output/env; Tool name maps `-` to `_`; Runtime name equals the generated id; CreateTool precedes CreateRuntime; two invocations differ.
  - Pass: all assertions hold and each invocation binds its own returned `t-*`.

- **VC-22 (FR-12 missing Tool input has no writes)**
  - Command: `uv run pytest tests/cli/test_cli_mpa.py -k missing_tool_input`
  - Input: runtime mode with neither `--tool-image` nor `--agentkit-tool-id`.
  - Expected: named CLI error before SkillSpace, database, Tool, or Runtime calls.
  - Pass: every side-effect stub is called zero times.

- **VC-23 (FR-5 delegated worker model selection)**
  - Steps: create an instance with `--model-name <model>` and trigger one real `sandbox_task`.
  - Expected: worker usage events report `<model>` instead of `auto`; the model proxy returns 2xx and the command reaches terminal `completed`.
  - Pass: the binding has `last_run_status=completed`, no `codex_turn_failed`, and at least one usage event has the configured model and `statusCode=200`.
  - Evidence: redacted binding/event summary; never persist the model API key.

- **VC-24 (FR-13 retry idempotency)**
  - Command: `uv run pytest tests/integrations/test_mpa_tool.py tests/integrations/test_mpa_runtime.py`.
  - Expected: an exact-name Tool/Runtime is reused and converged; a non-Ready Tool is awaited; duplicate exact names fail instead of selecting arbitrarily; Runtime updates wait for a newer Ready version.
  - Pass: no duplicate create call and all assertions hold.

- **VC-25 (FR-18 APIG id integrity)**
  - Command: `uv run pytest tests/cli/test_cli_mpa.py -k gateway`.
  - Expected: an endpoint-derived gateway is accepted only when it embeds exactly one listed gateway id; AgentKit shared-gateway endpoints fail closed unless `--apig-instance-id` supplies the dedicated customer APIG used for IM routing.
  - Pass: no arbitrary account gateway or `pending` placeholder is finalized into `mpa_meta`.

## 3.1 Real E2E result (2026-09-11)

- Runtime `r-yeuugf44qob21078l38i`, Tool `t-yeuugdts00zn6n5iqhin`, mpa-agent image tag `20260908154102-d34fdab`.
- VC-23 passed after setting `MPA_CODEX_WORKER_DEFAULT_MODEL`: two fresh contexts used the configured model, returned model HTTP 200, executed `printf` with exit code 0, and persisted `invocation.completed`.
- VC-19 isolation passed at the resource layer: contexts `a2ce8ec0-...` and `e7279624-...` mapped to distinct worker sessions `cw_sess_872f64f2f00b` and `cw_sess_bdf3758b4ddd`.
- VC-18 remains **blocked at the protocol result boundary**: both A2A requests returned `failed` with `The session has been modified in storage since it was loaded`, even though their worker bindings and commands completed. The selected image lets Codex durable events advance the PostgreSQL ADK session while the A2A runner still owns a stale session snapshot. This is an mpa-agent image/session-projection defect, not a Tool creation or model-routing failure.
- VC-20 was not run because Feishu credentials/bot installation were not provided; the existing `arkclaw:ListResources` denial also remains a documented permission risk for MCP discovery.
- VC-25 exposed a second VC-20 blocker: the real Runtime reports `GatewayMode=Shared` and an empty `GatewayInstanceId`; its public endpoint prefix does not match any customer APIG id. The previous row therefore retained `apig_instance_id=pending`. The CLI now fails closed and accepts an explicit dedicated `--apig-instance-id`; automatic customer-gateway allocation remains unresolved.

## 4. Execution plan

1. Unit level (VC-1..VC-14, VC-17): stub cloud SDK + SQLite/in-memory `mpa_meta`, run per TDD task.
2. Regression (VC-15, VC-16): run once after implementation.
3. Real (VC-18, VC-19, VC-20, VC-23): after one real `veadk mpa create` deploy, verify in Studio and a Feishu group; retain redacted evidence.
4. On failure: P0/P1 case failure returns to T-8..T-12 to fix implementation, or to this list to fix the case (recording the reason), then rerun affected cases.

## 5. Exit gate

- All unit/CLI P0/P1 cases mapped to FR-1..FR-19 pass.
- VC-15/VC-16 regression passes (does not break mpa-agent or existing commands).
- Real VC-18 and VC-20 remain blocked as documented in §3.1; VC-19 and VC-23 pass.
