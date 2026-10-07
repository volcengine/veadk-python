# Agent-derived MPA sandbox template names

- Change ID: `mpa-worker-naming`; created/revised: 2026-09-28; status: implemented.
- [中文](2026-09-28-agent-derived-worker-name.zh.md)
- Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-3.

## Evidence, goals and scope

`managed/worker.py` currently names tools `mpa_worker_` plus a scoped hash. The inspected ArkClaw implementation instead derives its formal tool name from the trimmed agent ID, replacing hyphens with underscores. Operators need to identify templates by agent ID. Change only managed MPA tool creation; do not rename existing cloud tools, change Runtime names/IDs, images, networks, tags, database names, general agents, or create debug tools.

## Requirements and scenarios

- FR-1 / AC-1: A fresh `mi-example` agent creates/discovers the template `mi_example`; trim surrounding whitespace and replace every `-` with `_`.
- FR-2 / AC-2: Registered worker IDs and explicitly supplied existing IDs retain their bindings without discovery, creation or renaming.
- FR-3 / AC-3: A pre-change unfinished intent retains its hashed name, full payload hash and ClientToken for retry, whether the provider already created the tool or not. A changed payload still fails before discovery/creation.
- FR-4 / AC-4: Name collisions cannot authorize adoption. Preserve ownership verification, scoped tags, timeout, cancellation and terminal-state handling.

## Design and compatibility

Build the fresh request with the agent-derived Name. When a persisted worker_hash differs, calculate the request hash with the former hashed Name. Only an exact match permits that legacy request to continue; otherwise retain the existing configuration-change error. No schema or API additions, migrations, dependencies, new permissions, or secret persistence. Registered IDs bypass request-name construction as before. The existing account lock remains responsible for serialization. Name normalization can collide, so the existing collision refusal and ownership checks remain mandatory. Rollback after a new unfinished intent requires completing that intent with the new code; existing bound IDs remain usable.

## Tasks and affected files

- T-1 (FR-1–FR-4): Add isolated regression coverage in `tests/integrations/mpa_managed/test_worker.py`; demonstrate fresh naming fails before implementation.
- T-2 (FR-1, FR-3): Update `veadk/integrations/mpa/managed/worker.py` minimally.
- T-3: Synchronize this pair, Studio creation CON-3, and the managed integration README pair; run worker/managed regression, Ruff, Pyright and whitespace checks.

## Review and approval

2026-09-28: The user approved the proposed agent-derived naming with existing-resource/retry compatibility by saying “改为旧规则”. `review-spec` is unavailable; direct design review checked boundaries, failure semantics, ownership, security, rollback, testability and language equivalence. No blockers. Production edits follow this review.

## Verification

Scope: working-tree worker naming diff atop the current branch; unrelated shared-network changes are preserved. T-1–T-3 results are recorded below. Live cloud creation: `not_run` (not required for this name/payload-only change; no cloud mutations authorized here). Browser/build: `not_applicable` (no frontend or browser API changes). Commit gates: `not_run` (no commit requested).

### Verification record, 2026-09-28

T-1–T-3 / AC-1–AC-4 complete for the working-tree naming change. Pre-implementation naming regression: expected `fail` (2 failed, 14 passed). After implementation:

- `uv run --extra dev pytest tests/integrations/mpa_managed/test_worker.py tests/integrations/mpa_managed/test_worker_recovery.py tests/integrations/mpa_managed/test_worker_metadata.py -q --tb=short`: `pass`, 67 passed.
- `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py tests/cli/test_frontend_deploy_iam.py -q --tb=short`: `pass`, 422 passed, 5 existing dependency deprecation warnings.
- `uv run --with ruff --with pyright ruff check veadk/integrations/mpa/managed/worker.py tests/integrations/mpa_managed/test_worker.py`: `pass`; initial import-order failure corrected.
- `uv run --with ruff --with pyright pyright veadk/integrations/mpa/managed/worker.py tests/integrations/mpa_managed/test_worker.py`: `pass`, 0 errors.
- `git diff --check`: `pass`.

Final code review: only an exact legacy payload hash permits the legacy name; idempotency tokens and ownership markers are preserved; existing IDs bypass creation. Requirements/contracts are synchronized across languages. Initial uv cache access was sandbox-blocked; checks completed after approved access. Per the user's existing preference, record this verification only, without changing environment guidance. No commit, push or cloud mutation.

Additional checks: repository-pinned Ruff lint/format, PRD relative links, bilingual counterparts, and changed-file `gitleaks dir --redact` scanning all `pass`. Frontend documentation updated; no generated assets changed.

## Rebase validation — 2026-10-07

Reconciled with main `e0448a4d` for PR #17. The original functional patch is retained; upstream discovery/authentication and Worker recovery changes are preserved. See the [combined reconciliation and verification record](../mpa-shared-network-bootstrap/2026-09-28-registry-owned-network.md#pr-17-rebase-reconciliation--2026-10-07).
