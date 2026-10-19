# Code Package Upload Validation

[中文版](2026-10-19-code-package-upload-validation.zh.md)

## Metadata

- Change ID: `code-package-upload-validation`
- Created: 2026-10-19
- Revised: 2026-10-19
- Status: implemented
- Related component specs: none changed. This bugfix preserves the existing Studio code package deployment contract and only moves known validation failures earlier in the upload flow.
- User approval: confirmed in chat on 2026-10-19 for three checks: require `app.py` and `requirements.txt` when no Dockerfile is provided, warn about missing `0.0.0.0:8000` listening evidence, and reject Python cache/binary files.

## Background and Evidence

Studio's code package upload page currently validates ZIP structure, safe paths, duplicate paths, and whether the declared `agentkit.yaml common.entry_point` file exists. A package with `agentkit.yaml` pointing at `main.py` can pass upload validation.

For ordinary uploaded packages without a custom Dockerfile, Studio later adds its default Dockerfile. That Dockerfile runs `CMD ["python", "-m", "app"]` and installs `requirements.txt`. Therefore a package that has `main.py` but no root `app.py`, or no root `requirements.txt`, may fail only during cloud build or Runtime startup. This is later than users expect and gives weaker remediation guidance.

The upload ZIP reader decodes files as text. Python caches such as `__pycache__/` and `*.pyc`, as well as other binary files, are not deployable source files and can corrupt or pollute the browser-provided project.

## Goals

- `G-1`: Reject packages that cannot satisfy Studio's default Dockerfile assumptions when no custom `Dockerfile` is present.
- `G-2`: Warn users when the package does not show clear evidence that it listens on `0.0.0.0:8000`.
- `G-3`: Reject Python cache and binary-looking package entries before deployment.
- `G-4`: Provide concise bilingual messages that explain the problem and the recommended fix.

## Non-Goals

- Do not change cloud deployment, AgentKit SDK launch behavior, or generated Dockerfile behavior.
- Do not perform full Python, shell, or Dockerfile static analysis.
- Do not add a new UI component or redesign the upload panel.
- Do not update component specs because no public API, route, runtime contract, or ownership boundary changes.

## Scenarios and Requirements

- `FR-1`: Given an uploaded package without a root `Dockerfile`, when it lacks root `app.py`, Studio must reject it with a message explaining that the default startup uses `python -m app` and suggesting root `app.py` or a custom Dockerfile.
- `FR-2`: Given an uploaded package without a root `Dockerfile`, when it lacks root `requirements.txt`, Studio must reject it with a message explaining that the default build installs `requirements.txt` and suggesting root `requirements.txt` or a custom Dockerfile.
- `FR-3`: Given an uploaded package containing `__pycache__/`, `*.pyc`, or binary-looking entries, Studio must reject it and tell the user to remove caches and binary build artifacts.
- `FR-4`: Given an uploaded package that otherwise passes validation, when Studio cannot find evidence of listening on `0.0.0.0:8000`, Studio must show a non-blocking warning that explains the Runtime reachability risk and gives a `uvicorn.run` example.
- `FR-5`: Existing ZIP size, file-count, path, duplicate, and `agentkit.yaml` entry point checks must continue to behave as before.

## Design and Contract Impact

The change adds browser-side validation in `frontend/src/create/CodePackageCreate.tsx` after ZIP entries are normalized and before the project is accepted for deployment. The checks reuse the normalized root-relative file list that the deployment API already receives.

Validation policy:

- Root `Dockerfile` disables the strict `app.py` and `requirements.txt` defaults because the package owns its build and startup commands.
- Without root `Dockerfile`, root `app.py` and root `requirements.txt` are required.
- `__pycache__/`, `*.pyc`, and entries containing replacement characters or NUL bytes after UTF-8 decoding are rejected as cache or binary-like files.
- `0.0.0.0:8000` listening evidence is a warning, not a blocker. Static detection checks package text for `0.0.0.0` plus `8000` or `PORT`, and Dockerfile text for port/listening hints. False negatives are acceptable because the message is advisory.

Security and privacy: The checks reduce accidental binary/cache uploads and do not inspect external systems or transmit new data. Messages must not echo large file content.

Compatibility: Packages that previously deployed successfully and include `app.py` and `requirements.txt` are unchanged. Packages relying on a custom Dockerfile remain allowed. Packages that passed upload but would fail under Studio defaults now fail earlier with remediation.

## Implementation Tasks

- `T-1`: Add package validation helpers and warning state in `frontend/src/create/CodePackageCreate.tsx`. Covers `FR-1` through `FR-4`.
- `T-2`: Add synchronized English and Chinese strings in `frontend/src/i18n/resources/en-US/create.json` and `frontend/src/i18n/resources/zh-CN/create.json`. Covers `FR-1` through `FR-4`.
- `T-3`: Extend focused frontend tests in `frontend/tests/codePackageDeploy.test.mjs`. Covers `FR-1` through `FR-5`.
- `T-4`: Run targeted frontend tests and record results. Covers all acceptance criteria.

## Verification and Acceptance

- `AC-1`: Upload validation rejects missing `app.py` without a Dockerfile and shows a message with the problem and recommendation.
- `AC-2`: Upload validation rejects missing `requirements.txt` without a Dockerfile and shows a message with the problem and recommendation.
- `AC-3`: Upload validation rejects Python cache and binary-like entries.
- `AC-4`: Upload validation can show a non-blocking `0.0.0.0:8000` warning for packages without listening evidence.
- `AC-5`: Existing package upload validations remain covered by tests.

| Requirement | Task | Acceptance criterion | Test or verification command | Result/evidence |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`, `T-2`, `T-3` | `AC-1` | `node --test frontend/tests/codePackageDeploy.test.mjs` | pass, 2026-10-19, 12 tests passed |
| `FR-2` | `T-1`, `T-2`, `T-3` | `AC-2` | `node --test frontend/tests/codePackageDeploy.test.mjs` | pass, 2026-10-19, 12 tests passed |
| `FR-3` | `T-1`, `T-2`, `T-3` | `AC-3` | `node --test frontend/tests/codePackageDeploy.test.mjs` | pass, 2026-10-19, 12 tests passed |
| `FR-4` | `T-1`, `T-2`, `T-3` | `AC-4` | `node --test frontend/tests/codePackageDeploy.test.mjs` | pass, 2026-10-19, 12 tests passed |
| `FR-5` | `T-3`, `T-4` | `AC-5` | `npm --prefix frontend test`; `npm --prefix frontend run check:i18n`; `npm --prefix frontend run build` | pass, 2026-10-19. Frontend test: 1389 node tests and 118 Vitest tests passed. i18n: 2 locales and 21 namespaces consistent. Build completed with existing Vite chunk/dynamic-import warnings. |

Browser checks were not run because this change only adds upload-time validation text and does not introduce a new interaction surface beyond the existing upload panel. Repository pre-commit was not run because no commit was requested.

## Risks and Open Questions

- Static listening detection can produce false warnings. This is accepted because the warning is non-blocking and explains the deployment risk.
- A custom Dockerfile can still be invalid in ways the upload page cannot fully detect. This change only adds lightweight preflight hints.

## Review and Delivery Record

- Design review: performed directly because no `review-spec` skill is available in this session. The scoped fix is feasible, security impact is positive, compatibility impact is limited to earlier failure of packages that do not satisfy existing default build assumptions, and bilingual requirements are aligned.
- Implementation status: implemented.
- Verification status: pass for targeted code package test, full frontend tests, i18n consistency, and frontend build. `npm --prefix frontend run build` refreshed generated `veadk/webui` assets as expected.
