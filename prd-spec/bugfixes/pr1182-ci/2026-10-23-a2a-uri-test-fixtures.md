# Remove Password-shaped A2A URI Test Fixtures

[中文版](2026-10-23-a2a-uri-test-fixtures.zh.md)

## Scope and Evidence

- Change ID: `pr1182-ci`
- Created/Revised: 2026-10-23
- Status: implemented and history repaired; publication authorized, CI confirmation pending.
- PR #1182 head: `0e71e4aa`; base: `cb9975df`.

Secret Scan run `39893501693` failed with exit 183. TruffleHog 3.99.4 reported 0 verified and 3 unverified URI results. GitHub annotations locate two fixtures in `tests/cli/test_a2a_center_actions.py` and one in `tests/cli/test_a2a_center_registration.py`; their current line numbers are 403, 484, and 109. These are deliberately invalid test inputs containing fake passwords, not verified credentials.

## Requirements and Design

- `FR-1`: Preserve API rejection and display filtering of URLs with userinfo.
- `FR-2`: Remove password-shaped test literals while retaining existing assertions.
- `FR-3`: Keep scanner enforcement and all production behavior unchanged.

Replace the three password-bearing inputs with username-only URLs. Keep `private-value` or `secret` as the username so existing non-disclosure assertions remain meaningful. `_card_url` and `_display_url` already reject nonempty usernames. Endpoint filtering must still return only the expected safe endpoint. Tests use FastAPI TestClient and mocked cloud calls; no real provider operation is needed.

No component contract changes: registration validation, `CON-CARD-VIEW`, `CON-ENDPOINTS`, authentication, permissions, state, concurrency and runtime behavior remain unchanged. See [A2A Center specification](../../../specs/mpa-collaborating-agents/README.md). UI, generated assets, dependencies, scanner rules and user documentation are unaffected.

Reject exclusions, encoded passwords and string splitting: fix unnecessary test data rather than hide credential-shaped material. The CI workflow scans commit history; a follow-up commit alone will still include the old fixtures. Remote remediation must separately remove these literals from the introducing commit while preserving later changes, merge structure and authorship.

## Tasks and Acceptance

| Requirement | Task | Acceptance | Verification | Result |
| --- | --- | --- | --- | --- |
| `FR-1`, `FR-2` | `T-1`: change three fixtures | `AC-1`: same response/filter assertions pass | `uv run --extra dev pytest tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py -q` | pass: 88 tests before and after |
| `FR-2` | `T-2`: compare scanner results | `AC-2`: original fixture scan reports URI results; repaired files do not | TruffleHog 3.99.4 filesystem scan with verification disabled, URI detector only | pass: 3 findings/exit 183 before; 0 findings/exit 0 after |
| `FR-3` | `T-3`: verify/review | `AC-3`: only fixtures and bilingual evidence change | Ruff, Pyright, `uv run --extra dev pre-commit run --all-files`, `git diff --check` and manual review | pass locally |

Execute baseline verification, T-1, T-2 and T-3 in order, then report remaining history remediation. Recovery is restoring the two test files from HEAD after preserving subsequent user changes.

## Review, Risks and Authorization

- User requested diagnosis and repair of PR #1182 CI, then approved the proposed history repair and PR update with "帮我提交" on 2026-10-23. This authorizes commit, preserving authors and merge topology during history rewrite, and publication with an explicit force-with-lease. Merge and deployment remain outside scope.
- `review-spec`: feasible, minimal, no API or contract impact; username-only inputs still exercise the stated userinfo boundary and preserve sensitive-text assertions. Password-specific input coverage is intentionally replaced by userinfo coverage; production checks for passwords remain unchanged.
- The existing failed CI is the scanner red baseline. Existing API tests establish behavior before/after; additional tests of literal formatting would not establish product correctness.
- These are API route tests, outside the unit-test generation skill's stated scope. No new test cases are required.
- Local macOS scanning without verification establishes detector behavior, not a clean CI history scan. Final CI confirmation requires the authorized history repair and rerun.
- Other checks currently pending must not be reported as passing. Record actual verification below.

## Verification Record

2026-10-23, tested scope `0e71e4aa` plus this local repair on `fix/pr1182-ci` (created from the PR branch and synchronized using `git pull --ff-only`).

- Target tests: pass before (88 in 2.62s) and after (88 in 1.15s), using repository Python 3.10. The two dependency deprecation warnings are unchanged.
- Scanner: downloaded TruffleHog 3.99.4 for macOS ARM64 into `/tmp/veadk-pr1182-tools`, with SHA-256 verified against the release checksum; no global installation. Baseline copies are outside the repository.
- Baseline command: `/tmp/veadk-pr1182-tools/trufflehog filesystem /tmp/veadk-pr1182-fixtures-before --include-detectors=URI --no-verification --no-update --json --fail`; fail/183 with exactly 3 URI findings. This expected failure is the negative control.
- Repaired command: `/tmp/veadk-pr1182-tools/trufflehog filesystem tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py --include-detectors=URI --no-verification --no-update --json --fail`; pass/0 with 0 URI findings.
- All-files pre-commit: pass, including Ruff check/format and both secret gates. `uvx pyright --pythonpath .venv/bin/python tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py`: pass, 0 errors and warnings.
- Diff/paired-language review: pass; only three fixture lines change, assertions and production files unchanged. No product defect is inferred from scanner detection.
- Broader local Python/frontend/browser/cloud tests: not_applicable to this fixture-only change. Existing remote frontend/backend gates, release verification, smoke, license and Python 3.12 checks passed; remote Python 3.10 remains pending at the last check.
- Repository helper plan returned `onboarding_required` because there is no Manifest; use the native contracts and checks above rather than introduce onboarding changes.
- History remediation: pass locally. Rebased onto fetched `upstream/main` (`c662cc8d`) using `--rebase-merges`, amended introducing commit `46f60e12` to `497f4b65`, and preserved subsequent changes, merge topology, author identities and author dates. Rewritten pre-documentation head is `f44063d4`. A local backup ref retains the old history for recovery and is not published.
- Synchronization: the only additional tree differences from old PR head are upstream PR #1181's six-file skill telemetry correction; there were no conflicts or manual changes to those files. Target tests plus `tests/skills/test_skill_telemetry.py`: pass, 101 tests in 6.92s after synchronization.
- History scanner: pass, 0 findings, using `/tmp/veadk-pr1182-tools/trufflehog git file:///Users/bytedance/Desktop/github-code/veadk-python --since-commit=c662cc8d --branch=fix/pr1182-ci --skip-additional-refs --include-detectors=URI --no-verification --no-update --json --fail`. Only the rewritten PR history was scanned; this does not replace CI's full detector configuration.
- Publication: authorized; expected old remote head is `0e71e4aa4888d8b7a79b4a59919d7b7a4289af62`. New remote CI results remain pending until publication.
