# mpa-agent One-Click Provisioning — Functional Verification Cases

> Related design: `2026-09-10-mpa-agent-oneclick-provision-design.md` (`approved`)
> Purpose: dev-loop step 2 up-front design and step 7 execution — executable verification cases.
> Status: `designed` (not executed yet; step 7 fills the results back into this table).

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
| FR-5 | VC-10 | unit |
| FR-6 | VC-11, VC-12 | unit |
| FR-7 | VC-13 (output guidance), VC-18 (real Studio chat) | unit + real |
| FR-8 | VC-3 (hidden input), VC-14 (dry-run masking) | unit/CLI |
| FR-9 | VC-15 (mpa-agent unchanged), VC-16 (existing-command regression) | gate/regression |
| FR-10 | VC-10 (IDENTITY_STARTUP_ENABLED=false + csi-<account_id>) | unit |
| FR-11 | VC-7 (private mirrors public) | unit |
| key regression | VC-16, VC-19 (distinct sessions → distinct sandboxes), VC-20 (Feishu group chat) | regression + real |

Every P0/P1 requirement (FR-1..FR-11) is covered by at least one case.

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
  - Expected: assembled env contains all mpa-agent startup keys (`MODEL_AGENT_*`, `PG*`, `MPA_SESSION_MEMORY_BACKEND`, `OPENVIKING_*` if provided, `AGENTKIT_TOOL_ID`, `MPA_AGENT_ID`); `IDENTITY_STARTUP_ENABLED=false`; `CLAW_SPACE_ID=csi-<account_id>`; endpoint keys use public.
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

## 4. Execution plan

1. Unit level (VC-1..VC-14, VC-17): stub cloud SDK + SQLite/in-memory `mpa_meta`, run per TDD task.
2. Regression (VC-15, VC-16): run once after implementation.
3. Real (VC-18, VC-19, VC-20): after one real `veadk mpa create` deploy, verify in Studio and a Feishu group; retain redacted evidence.
4. On failure: P0/P1 case failure returns to T-8..T-12 to fix implementation, or to this list to fix the case (recording the reason), then rerun affected cases.

## 5. Exit gate

- All P0/P1 cases mapped to FR-1..FR-11 pass.
- VC-15/VC-16 regression passes (does not break mpa-agent or existing commands).
- Real VC-18 passes; VC-19/VC-20 pass or carry an explicit risk note with user confirmation.
