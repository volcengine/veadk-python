# BytePlus Runtime Tag Endpoint Fix

- Change ID: `studio-byteplus-tag-endpoint`
- Status: `implemented`
- Created: 2026-10-15
- Revised: 2026-10-15
- Chinese: [2026-10-15-byteplus-tag-endpoint.zh.md](2026-10-15-byteplus-tag-endpoint.zh.md)
- Component: [Studio MPA control plane](../../../specs/studio-mpa-control-plane/README.md)

## Background and evidence

A source deployment of Studio to BytePlus `ap-southeast-1` returns HTTP 502 from
`GET /web/runtimes`. The nested Tag `GetResources` response is HTTP 400
`InvalidEndpoint`. Runtime SDK clients already select a BytePlus host, but the
generated Tag SDK clients leave `Configuration.host` empty. The SDK then falls
back to the Volcengine endpoint for this region.

The same read-only `GetResources` request succeeds when sent to
`open.byteplusapi.com`, confirming that the request shape, credentials, and IAM
permissions are valid.

## Goals and non-goals

### Goals

- Send BytePlus Runtime Tag reads to `open.byteplusapi.com`.
- Preserve the existing Volcengine endpoint behavior.
- Add a regression test that inspects the generated SDK configuration used by
  the Runtime listing route.
- Preserve existing fail-closed Tag error handling.

### Non-goals

- Changing Runtime list schemas, filters, authorization, or pagination.
- Adding endpoint input controlled by the browser.
- Changing or recreating cloud Runtime resources.
- Modifying frontend UI behavior.

## Scenarios and requirements

- `FR-1`: Given a BytePlus Studio deployment, when `/web/runtimes` performs a
  Tag-filtered lookup, the Tag SDK host must be
  `https://open.byteplusapi.com`.
- `FR-2`: Given a Volcengine Studio deployment, existing generated-SDK endpoint
  resolution must remain unchanged.
- `FR-3`: Tag failures must remain explicit errors and must not become empty
  Runtime lists.

## Design and contract impact

Introduce a provider-specific Tag OpenAPI host helper. Configure each Runtime
Tag read client with the BytePlus host before constructing `TAGApi`; leave the
Volcengine configuration host unset so its current SDK resolution remains
unchanged.

The public HTTP contract is unchanged. The maintained `CON-15`/`CON-31`
provider-boundary contract is clarified to require provider-correct Tag
endpoints. No state, persistence, concurrency, credential, permission, or
frontend type changes are introduced. Credentials remain server-side and the
browser cannot choose the endpoint.

## Affected files and tasks

- `T-1` (`FR-1`, `FR-2`): Add a failing BytePlus Runtime-list Tag host test.
- `T-2` (`FR-1`, `FR-2`): Add provider-specific Tag host selection and apply it
  to Runtime Tag reads.
- `T-3` (`FR-3`): Update the bilingual component contract.
- `T-4`: Run targeted Python tests, Ruff, Pyright, frontend tests/build, and an
  isolated live BytePlus read after redeployment.

## Verification and acceptance

| Requirement | Task | Acceptance criterion | Verification | Result |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`, `T-2` | `AC-1`: BytePlus Tag SDK receives `https://open.byteplusapi.com` | Targeted pytest | `pass`: BytePlus host regression passed |
| `FR-2` | `T-1`, `T-2` | `AC-2`: Volcengine behavior is unchanged | Targeted pytest | `pass`: existing Runtime Tag suite passed |
| `FR-3` | `T-3` | `AC-3`: Existing fail-closed behavior remains covered | Targeted pytest | `pass`: Runtime proxy suite passed |
| `FR-1` | `T-4` | `AC-4`: Redeployed BytePlus `/web/runtimes` no longer fails with `InvalidEndpoint` | Live browser/API check | `blocked`: VeFaaS new-revision pod readiness timed out before traffic switched |

Required commands:

```bash
uv run --extra dev pytest tests/cli/test_frontend_runtime_proxy.py
uv run --extra dev ruff check veadk/utils/cloud_provider.py veadk/cli/cli_frontend.py tests/cli/test_frontend_runtime_proxy.py
uv run --extra dev pyright veadk/utils/cloud_provider.py veadk/cli/cli_frontend.py
npm --prefix frontend test
npm --prefix frontend run build
git diff --check
```

## Risks and recovery

An incorrect host would keep Runtime discovery unavailable. The focused
configuration assertion and live read cover that risk. Rollback removes the
BytePlus host assignment; no data migration or cloud cleanup is required.

## Review and delivery record

Review on 2026-10-15 confirmed the failure is endpoint selection rather than
credentials, IAM, Runtime state, or request shape. The design preserves
Volcengine behavior and fail-closed errors. The user approved implementation in
the conversation.

Implementation verification on 2026-10-15:

- `pass`: `tests/cli/test_frontend_runtime_proxy.py`, 120 tests.
- `pass`: focused Ruff over the three changed Python files.
- `pass`: `npm --prefix frontend test`, 1389 Node tests and 116 Vitest tests.
- `pass`: `npm --prefix frontend run build`.
- `pass`: paired-document and `git diff --check` checks.
- `blocked`: Pyright reports 37 existing errors in `cli_frontend.py`; no error
  references the new Tag host lines.
- `blocked`: the live BytePlus update created Application revision 2 and
  Function revision 3, but VeFaaS failed the release with
  `internal_system_error` / `check new revision's pod ready timeout`. Stable
  traffic remained on the preceding revision, so `/web/runtimes` acceptance
  could not exercise this fix.


### Post-rebase verification (2026-10-15)

Scope: the Tag endpoint diff on remote branch revision `65cb4f50`.

- `pass`: rebased onto `origin/feat/mpa-lifecycle-upstream-20261013` without conflicts.
- `pass`: `uv run --extra dev pre-commit run --all-files`, including Ruff,
  secret scanning, dependency policy, and YAML scanning.
- `fail`: `uv run --extra dev pytest -q tests/cli/test_frontend_runtime_proxy.py tests/integrations/mpa_managed -n 2`:
  1268 passed, 3 failed. Two workers were used for this scoped regression run.
  All three failures are existing `test_creation_images.py` assertions that
  `tosBucket` is absent; the remote recovery change now preserves that field.
  Running the three cases on clean `65cb4f50` reproduces the same failures.
  This Tag fix does not modify those creation contracts or tests.
- `blocked`: Pyright over all three changed Python files reports 57 errors.
  Baseline files from `65cb4f50` produce identical diagnostic messages and counts;
  this diff introduces no additional diagnostic.
- `not_run`: frontend build/browser and cloud deployment were not repeated for
  this backend-only submission; the earlier live deployment limitation remains.
