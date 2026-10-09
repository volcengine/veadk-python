# Preserve IAM Timeout Semantics on Python 3.10

[中文版](2026-10-09-python310-timeout.zh.md)

## Metadata

- Change ID: `mpa-iam-timeout-compat`
- Created: 2026-10-09
- Revised: 2026-10-09
- Status: implemented
- Related component specs: none; the existing IAM failure contract is preserved

## Background and Evidence

PR #23 fails the Python 3.10 unit-test job in
`test_readback_timeout_and_cancellation_keep_resources`. The managed MPA IAM
reconciler wraps `asyncio.wait_for()` with `except TimeoutError`. On Python
3.10, `asyncio.wait_for()` raises `asyncio.TimeoutError`, which is not caught by
the built-in `TimeoutError` handler. Python 3.11 and newer alias these exception
types, which hid the compatibility defect in newer local environments.

The CI result was 6,497 passed and one failed. The uncaught timeout escapes
instead of being translated to the existing `IamError` with
`iamVerificationFailed`.

## Goals and Non-goals

### Goals

- Preserve the existing IAM verification failure behavior on Python 3.10.
- Keep cancellation propagation and resource retention unchanged.
- Make the existing regression test pass on Python 3.10 and current Python.

### Non-goals

- Change IAM resources, permissions, retry timing, or reconciliation order.
- Change the public error contract or add a new fallback.
- Modify unrelated MPA behavior.

## Requirements and Design

- `FR-1`: A timeout from `asyncio.wait_for()` must be translated to the existing
  `IamError`.
- `FR-2`: Caller cancellation must continue to propagate as
  `asyncio.CancelledError`.
- `FR-3`: The fix must work on Python 3.10 and Python 3.12 without changing
  functional IAM logic.

Use `except asyncio.TimeoutError` at the existing translation boundary. This is
the exception raised by `asyncio.wait_for()` on Python 3.10 and remains
compatible with newer Python versions.

Component contract impact: none. The implementation is corrected to satisfy the
already-tested timeout and cancellation contract. No interfaces, configuration,
permissions, persistence, security boundaries, or user documentation change.

## Tasks and Acceptance

| Requirement | Task | Acceptance | Verification | Result |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`: reproduce before the fix | Python 3.10 exposes the uncaught timeout | Python 3.10 targeted pytest | pass: reproduced the uncaught `asyncio.TimeoutError` |
| `FR-1`, `FR-3` | `T-2`: use `asyncio.TimeoutError` | Existing timeout translation passes | Python 3.10 and 3.12 targeted pytest | pass: 13 tests on each version |
| `FR-2` | `T-2` | Existing cancellation assertion passes | Same targeted pytest | pass |
| `FR-3` | `T-3`: static verification | Changed Python file is clean | Ruff and Pyright | pass |

## Risks and Open Questions

- Risk is limited to the exception selector at the existing timeout boundary.
- No open questions remain.

## Review and Delivery Record

- 2026-10-09: CI traceback confirmed the Python 3.10 exception mismatch.
- 2026-10-09: Design review found no contract, security, or compatibility
  blocker.
- 2026-10-09: The user approved a compatibility-only fix and explicitly
  requested no functional behavior change.
- 2026-10-09: Python 3.10 reproduced the failure before the fix. After the
  one-line exception qualification, the IAM tests passed on Python 3.10.20 and
  Python 3.12.13 (13 tests each), the Python 3.12 managed MPA suite passed (664
  tests), and Ruff 0.11.12 and Pyright passed.
- Commit and push require separate authorization.
