# Recover terminal PG Workspace creation failures

[中文版](2026-10-10-terminal-create-failure.zh.md)

- Change ID: `mpa-pg-terminal-create-failure`
- Date: 2026-10-10
- Status: implemented
- Component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-13

## Background and evidence

Automatic PG bootstrap is shared by account, region and project. CreateWorkspace can fail after leaving a cloud Workspace in `CreateFailed`, while SQLite retains an intent without a resource ID. Discovery validates ownership tags before checking status, outside the readiness loop. Missing tags therefore immediately fail every later agent request. An outer provider InternalError can contain a purchasing rejection; its outer code alone cannot establish whether a resource exists.

## Goals, non-goals and scenarios

Restore creation after a confirmed terminal creation failure, without deleting cloud resources or changing healthy reuse. Apply the same recovery contract to Volcengine and BytePlus. Do not alter manual/explicit adoption, databases, VPC, APIG, Runtime, images, frontend, or chat. No live cloud mutations are needed for implementation verification.

Scenarios: initial failure with or without an ID; retry after permissions are corrected; failed old resource alongside a healthy replacement; replacement request timeout; concurrent agents; partial metadata; conflicting ownership; explicit IDs and deleted/unknown/operationally failed resources.

## Requirements and design

- **FR-1:** Only exact `CreateFailed` is a recoverable terminal creation status. `Failed`, deleted/deleting, unknown statuses and service errors retain fail-closed semantics. A newly dispatched create that reaches `CreateFailed` fails that task; do not repeatedly purchase in the same attempt.
- **FR-2:** Before retiring a failed candidate, require complete matching account, region, project, name, engine and nonempty ID; reject present conflicting ownership tags. Missing ownership tags are allowed only when classifying `CreateFailed`, never when adopting a ready resource. Explicit configured IDs never change automatically.
- **FR-3:** Add a nonsecret `failed_workspaces` SQLite table keyed by scope, purpose and ID. Retire a confirmed failed managed binding and its active intent atomically. Preserve old cloud resources. Ignore retired IDs only while they remain `CreateFailed`; reject a changed status. Existing tables are retained and upgraded additively.
- **FR-4:** With an ID-less uncertain intent, one newly observed confirmed failed candidate and no live candidate permits retirement. Multiple unretired failed candidates remain ambiguous. Previously retired failures must never resolve a newer uncertain create. No candidates still means uncertain; no blind CreateWorkspace retry. A healthy/creating candidate remains subject to existing identity/tag checks and duplicate protection.
- **FR-5:** Discovery of incomplete owned metadata enters the existing bounded readiness loop instead of failing outside it. Present conflicts still fail immediately. Use the existing per-scope OS lock and PG/task deadline; cancellation retains durable identity/intent.
- **FR-6:** Initial healthy creation, shared reuse, successful response-loss recovery and downstream failure remain compatible. Generic API/UI failure categories and sanitized diagnostics remain unchanged. An already recorded Workspace that is missing or has an operational failure is never replaced.

Affected files: `managed/pg_bootstrap.py`, `tests/integrations/mpa_managed/test_auto_pg.py`, paired component specs, managed module READMEs and this design. No new dependency, browser field, provider request format or cloud delete API.

## Tasks, tests and acceptance

- **T-1 / AC-1:** Regression tests first: both providers, admin/business purposes, missing tags, stored IDs, explicit adoption, concurrent recovery and healthy reuse.
- **T-2 / AC-2:** Implement additive durable retirement and state-first recovery; at most one new create per purpose per request. Failed cloud resources remain untouched.
- **T-3 / AC-3:** Verify unknown outcomes, retired-resource history, ambiguity, changed retired status, foreign scope/tags, API errors, missing details, timeout and cancellation prevent duplicate or destructive operations.
- **T-4 / AC-4:** Run targeted and managed integration regressions, Python default regression with two workers, changed-file Ruff/Pyright, paired-document and whitespace checks. No frontend change, so frontend build/browser gates are not applicable. Do not commit/push or perform live cloud creation without authorization.

## Risks and review

CreateFailed classification relies on a cloud terminal creation status and verified scope. Missing tags on failed resources do not authorize adoption or deletion. Preserve failed IDs durably so an old failure cannot authorize repetition of a later timed-out request. Independent hosts still require shared bootstrap state; this fix does not introduce distributed locking. Retained failed cloud resources may need operator cleanup. Old stores with unknown outcomes and multiple candidates deliberately require manual recovery.

User approved the recovery rule with “改下” on 2026-10-10 after the normal/failure/unknown behavior was explained. `review-spec` is unavailable; direct review covered feasibility, additive schema, state transitions, cancellation, locking, explicit-ID boundaries, secrets, domestic compatibility and bilingual equivalence. No blockers; production/test edits may proceed.

## Verification record

Verification date: 2026-10-10. Tested revision: working tree based on `5644e146c9dfff6d2e290b1663cb2ea41dbb6b91`, including the previously approved BytePlus adaptation. This recovery change modifies one production module and one test module, plus paired design/spec/module documentation. Existing adaptation edits are preserved. The normal/failure/concurrency tests use disposable SQLite files and fake cloud adapters, not user state or live cloud resources.

| Check | Outcome | Evidence / limitation |
| --- | --- | --- |
| Failing regression before implementation | pass | 14 of 16 initial recovery cases failed for missing-tag recovery, retired-history absence and failure-state handling; two ownership guards already passed. Additional present-conflict cases failed before their corrections. |
| `uv run --extra dev pytest tests/integrations/mpa_managed -q --tb=short` | pass | 782 tests, 5 existing warnings; 30 new recovery/compatibility cases. Both providers, both Workspace purposes, interleaved concurrent requests, unchanged healthy reuse, unknown/cancelled outcomes, migration and explicit-ID guards covered. |
| `uv run --with ruff==0.11.12 ruff check <changed-python-files>` and `ruff format --check` | pass | `pg_bootstrap.py` and `test_auto_pg.py`; temporary tooling, no global installation. |
| `uv run --with pyright pyright <changed-python-files>` | pass | Same two files; 0 errors, warnings or information diagnostics. |
| `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" --tb=short` | fail | 6,985 passed, 1 failed, 53 skipped, 4 xfailed in 411.61 seconds. Existing `test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes` expects `text/markdown`; local MIME detection returns `application/octet-stream`. The same failure was reproduced on unmodified HEAD during the prior BytePlus verification. Production recovery code was unchanged during this run; the two final compatibility tests were additionally verified in the final 782-test managed run. |
| Paired documents, identifiers, relative links and `git diff --check` | pass | Reviewed both language versions and maintained CON-13; no credentials or production logs in the change. |
| Frontend/browser/build, harness coverage, Codex smoke | not_applicable | No UI/generated release asset, chat, sidecar or Codex runtime change. |
| Pre-commit, branch synchronization, commit/push | not_run | No commit or push authorized; these gates apply before a subsequent commit. |
| Live creation/replacement | not_run | This code fix was verified offline; no new cloud mutation authorized for its verification. The earlier explicitly authorized cleanup is a separate operation. |

Final direct review: creation count is bounded to one new purchase per purpose per request, failed identities survive restarts, state release is atomic under the existing lock, explicit IDs and unrelated scope/purpose records are preserved, terminal operational failures are not replaced, and missing metadata cannot hide a present conflict. Failed resource cleanup and distributed/multi-host coordination remain operator responsibilities.


## Commit preparation verification (2026-10-10)

The user authorized committing and pushing the local changes. Fetched `origin` and `upstream`, then ran `git rebase --autostash upstream/main` on `feat/mpa-account-fixes-upstream-clean-20261010`. The branch was already current; all 159 pre-existing changed file states matched after synchronization. The baseline remains `5644e146c9dfff6d2e290b1663cb2ea41dbb6b91`. The only subsequent production adjustment is Ruff formatting of the creation-route registration in the CLI.

- **pass:** `uv run --extra dev pre-commit run --all-files`: Ruff check/format and both secret scanners. The first run reformatted the CLI call; the repeat passed.
- **pass:** post-synchronization `uv run --extra dev pytest tests/integrations/mpa_managed -q --tb=short`: 782 passed, 5 existing warnings.
- **pass:** post-synchronization `npm --prefix frontend test`: 1,377 Node tests and 67 Vitest tests.
- **pass:** post-synchronization `npm --prefix frontend run check:i18n` and `npm --prefix frontend run test:webui-assets`: 2 locales / 21 namespaces and 113 files / 350 references.
- **not_run:** repeated full Python regression, frontend build/browser and Pyright. Synchronization preserved their previously tested source; the CLI adjustment changes formatting only. Existing full-regression MIME and CLI Pyright baseline failures remain documented above. No new cloud creation, publication or deployment is part of this commit request; overseas end-to-end readiness remains unverified.

The commit includes BytePlus adaptation, terminal PG creation-failure recovery, paired documents, tests and matching generated frontend assets. No credentials, local state databases or production logs are included.
