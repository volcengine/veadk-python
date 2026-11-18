# Agent Instructions

VeADK includes a Python SDK, CLI/runtime integrations, and AgentKit Studio with a TypeScript/React frontend and supporting Python services. Base decisions on the relevant implementation, tests, and existing contracts rather than assumptions from another repository.

## Language and document ownership

- Keep this repository-wide development standard in English. Use English for new code identifiers, comments, and docstrings; user-facing text follows the owning area's localization rules.
- Do not create standalone PRD or component-spec files, or recreate the root `prd-spec/` and `specs/` directories, as part of routine development. Create such documents only when the user explicitly requests them; generic skills or workflow templates do not make them mandatory.
- Discuss change-specific intent, scope, design decisions, and acceptance criteria in the conversation or PR description. Update existing maintained documentation when an affected interface or behavior needs clarification.
- When updating existing bilingual documentation, keep its language counterparts semantically equivalent in the same change, including identifiers, commands, examples, limits, and acceptance criteria.
- Before modifying frontend code, read `frontend/SPEC.md`; also apply it to its supporting backend interfaces as specified there. It remains the Studio development standard and is not replaced or translated by this document.
- Preserve existing user-documentation conventions: the documentation site uses Chinese `.mdx` and English `.en.mdx`; bilingual module/example READMEs use English `README.md` and Chinese `README.zh.md`.

## Required development workflow

1. **Inspect and agree on scope.** Read the affected implementation, tests, and contracts. When the user describes a requirement, propose an implementation plan and wait for the user to be satisfied before making edits. Distinguish verified facts from assumptions.
2. **Plan before implementation.** Explain the implementation approach, affected areas, risks, and verification plan in the conversation. Scale the detail to the change; no separate design document is required.
3. **Assess component contracts.** Check affected ownership, APIs, configuration, state/data, events, permissions, security, compatibility, runtime behavior, and observability. Update relevant existing documentation when necessary; do not generate separate component specs or no-impact reports by default.
4. **Review the approach.** Check feasibility, boundaries, errors, security, compatibility, and testability before editing. Resolve blockers and obtain user agreement for material scope changes. No standalone design review artifact or PRD/spec approval gate is required.
5. **Implement within the agreed scope.** Write a failing regression or contract test first for bugfixes, then implement and refactor within scope. Reassess the plan when contracts or scope change.
6. **Verify and review.** Run affected tests first, then required repository and component gates. Review both implementation correctness and edge cases, resource handling, security, test quality, and contract alignment. Fix blocking findings and rerun affected checks.
7. **Reconcile and deliver.** Update affected existing user docs/examples, their applicable language counterparts, and required generated artifacts. Summarize actual verification commands, results, unverified areas, and remaining risks in the conversation or PR description. All agreed tasks and acceptance criteria must be satisfied before declaring completion; deferred scope requires user agreement.

Documentation, translation, formatting, and development-guideline changes require an agreed approach, applicable updates to existing language counterparts, and proportionate checks. They do not require a separate design document.

## Implementation boundaries

- Make the smallest complete change that satisfies the approved requirement. Reuse existing modules and dependencies; avoid unrelated cleanup, speculative abstractions, and partially wired features.
- Treat public Python imports/signatures, CLI/configuration behavior, generated projects, Studio API types, and runtime/event contracts as consumer-facing boundaries. Breaking changes require explicit approval and a plan for affected callers and data; do not copy another project's blanket no-compatibility policy.
- Cover asynchronous cancellation, timeouts, late responses/events, terminal states, and resource cleanup where affected. Do not turn errors into silent success or empty results.
- Keep real credentials, signed URLs, personal data, and unredacted production logs out of source, design documents, reports, test fixtures, and generated artifacts.
- Isolate tests from real user state and external services by default. Real cloud/provider operations need explicit authorization and an isolated smoke/E2E procedure; report simulated and live verification separately.

## Dependency metadata guidelines

- Do not treat `uv.lock` success as proof that published package metadata is installable. PyPI users resolve from `pyproject.toml` metadata, not this repository's lock file.
- When changing runtime dependencies in `pyproject.toml`, consider both direct use and shared transitive constraints from key upstream packages such as `google-adk`, `agentkit-sdk-python`, OpenTelemetry, `mcp`, `fastmcp`, `litellm`, and storage/cloud SDKs.
- High-risk upstream dependencies must declare an explicit tested upper bound. Do not leave them open-ended when an unadapted future version could break installation or runtime behavior.
- Avoid exact pins for shared base dependencies unless there is a concrete compatibility reason. If an exact pin is necessary, document the reason in the dependency comment, PR/MR description, linked issue, or external design document.
- Before widening a high-risk dependency range, check whether the highest allowed version still resolves with the current runtime pins. Use `scripts/check_dependency_e2e.py declared-range` or the release workflow's manual dispatch when the check is too heavy for ordinary PR iteration.
- If a dependency upgrade only works by relying on another package's current transitive dependency, declare the required direct dependency explicitly in `pyproject.toml` rather than depending on accidental resolver behavior.
- If a heavy dependency E2E check is intentionally not run before merge, record the risk and the expected tag/manual workflow coverage in the PR/MR description, linked issue, or external design document.

## Verification gates

Use the repository-local Python environment and current `pyproject.toml`, `pytest.ini`, package scripts, and CI workflows as command references. Do not invent `make` targets, copy another repository's coverage thresholds, or treat an unavailable check as passing.

| Change area | Required verification |
| --- | --- |
| Python SDK, CLI, and backend | Targeted tests via `uv run --extra dev pytest <test-paths>`; broader regression tests when shared contracts or dependencies are affected. |
| Default parallel Python regression | `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`; adjust worker count to available resources and record the selection. Explicit smoke runs are separate. |
| Codex runtime smoke | When affected and the environment is prepared: `CODEX_RUN_SMOKE=1 uv run --extra dev pytest -m codex_smoke -p no:xdist -rs`. This test starts real processes and binds ports; never run it under parallel pytest. Verify it actually ran rather than skipped. |
| Studio frontend | `npm --prefix frontend test` and `npm --prefix frontend run build`, plus real browser checks of the normal flow and affected loading, empty, error, cancellation, retry, keyboard/IME, and narrow-window cases. Follow `frontend/SPEC.md` for additional checks and release asset requirements. |
| Studio backend or generated Python | Targeted Python tests plus Ruff and Pyright for changed Python files, as required by `frontend/SPEC.md`; verify generated code, dependencies, configuration, and deployment payloads together. |
| Harness/sidecar contracts | The affected checks and existing coverage thresholds in `.github/workflows/harness-sidecar-release-gate.yaml`, including `npm --prefix frontend run test:harness-sidecar-coverage` when frontend sidecar contracts change. |
| Guideline-only changes | Check document consistency, relative links, referenced paths/commands, and diff whitespace. No runtime test result may be claimed from documentation checks. |
| User documentation site | The affected Markdown/MDX checks and build/type checks defined in `docs/package.json`; do not apply site-specific tooling to unrelated plain Markdown without checking its scope. |

- Before committing, run `uv run --extra dev pre-commit run --all-files` and unit tests after synchronizing the branch as described below. Pre-commit includes Ruff and secret scanning; it does not replace browser, integration, or runtime verification.
- Prefer targeted checks during iteration. Expand to affected integration/E2E and regression gates for shared or high-risk changes and final delivery; explain any omitted required check.
- Record check outcomes as `pass`, `fail`, `blocked`, `not_run`, or `not_applicable`, with reasons for the last three. Include the tested revision/diff scope and execution date. Skipped tests do not prove the relevant behavior.
- Keep change-specific review and verification summaries in the conversation or PR/MR description by default, with links to existing issues or external documentation when useful. Do not generate PRD/spec files, OpenSpec records, or a multi-report hierarchy unless the user requests them.

## Git and execution safety

- Do not use `codex/` as a branch name prefix. Use semantic prefixes such as `feat/`, `fix/`, `chore/`, or `docs/`, with a name reflecting the requirement.
- After creating or switching to a new branch, run `git pull` before development. If no upstream exists or synchronization fails, resolve the target explicitly rather than guessing or bypassing the requirement.
- Before committing, fetch the latest remote code, rebase the branch onto the intended remote base, then run pre-commit and unit tests. Preserve unrelated user changes and stop if safe synchronization requires a user decision.
- Before committing, check whether the change affects public Python imports/signatures, CLI/configuration, generated projects, Studio API types, runtime/event contracts, user-visible behavior, documentation, dependency policy, or compatibility. If it does, make sure the GitHub PR, linked issue, release notes, or user documentation records the impact, compatibility notes, verification, and remaining risks; if it does not, state that no public GitHub-facing record is required in the PR/MR or handoff.
- Commit only changes related to the current feature or fix. Commit, push, PR creation, publication, and deployment require user authorization; approval of a design does not authorize them.
- Never commit real security-sensitive information or private data to GitHub. This includes API keys, access keys, secret keys, bearer/session/refresh tokens, cookies, signed URLs, private certificates, production logs with credentials, personal data dumps, and cloud account secrets. Use placeholders, environment variables, secret references, or documented local-only setup instead.
- The repository pre-commit configuration must reject hardcoded API key and token material before a commit is created. If secret scanning reports a finding, stop and remove or redact the value rather than bypassing the hook.
- When execution hits a pitfall such as insufficient permissions or missing dependencies, ask the user whether to document that pitfall. Report blocked checks honestly and do not alter machine-global configuration or bypass gates to hide the issue.
