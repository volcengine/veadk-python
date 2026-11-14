# AIO sandbox skills and basic tools

[中文版](2026-10-26-aio-sandbox-skills.zh.md)

Change ID: `aio-sandbox-skills` · Date: 2026-10-26 · Status: implemented, with full-regression limitations below.

## Background and scope

VeADK's `aio_sandbox` branch previously returned no tools, while Skill initialization still resolved sources on the Runtime host. The goal is to retain `Agent(skills_mode="aio_sandbox", skills=[...])` and the existing `SkillsToolset`, with inference in Runtime and Skill files, commands and file operations in the sandbox. No new Agent field or execution-mode value is introduced. HTTP App/session APIs, Skill installation, other runtimes and additional discovery APIs are outside scope.

## Requirements and design

- **FR-1 — Entry point:** Mount `SkillsToolset` even with empty `skills`. In AIO mode, `skills` contains absolute sandbox directories; an empty list uses the sandbox's default directory. Construction must not read host Skill files or load cloud SkillSpace sources. `local` and `skills_sandbox` retain their behavior; AIO callers using SkillSpace IDs must migrate to sandbox directories.
- **FR-2 — Session binding:** Before inference, create or reuse an AgentKit sandbox for the ADK app/user/session identity. Store only tool/session identifiers and the identity digest in ADK state. Subsequent turns reuse that sandbox; expired or non-Ready bindings fail without replacement or local fallback. The application owns instance lifecycle; idle instances expire by TTL.
- **FR-3 — Skill loading:** Obtain names, descriptions and instruction-file paths through `GET /v1/skills`, passing repeated `path` parameters for multiple directories. Read instructions lazily through the sandbox file API. Tool descriptions and closures belong to the execution context; do not rewrite shared Agent instructions or share another Session's Skill catalog.
- **FR-4 — Basic tools:** Route `skills_tool`, `bash_tool`, `read_file_tool`, `write_file_tool` and `edit_file_tool` to the same sandbox. Preserve existing tool names and model-visible arguments. Reads retain line numbering; edits require a unique match unless replacing all occurrences. Caller-supplied custom tools remain the caller's responsibility.
- **FR-5 — Failures and isolation:** Never forward the host environment to commands. Preserve endpoint query parameters and existing authentication; keep credentials out of session state and diagnostics. Reject failed/malformed responses and redirects. Bash has a finite timeout, bounded output and remote kill/close on interruption; cleanup failures remain visible. Do not automatically retry mutations. Applications serialize concurrent turns of one ADK Session.

Component-contract impact is limited to Agent Skill initialization and the AIO toolset branch described above; no Studio, model configuration or HTTP API contract changes. The implementation uses the existing lease resolver and a small data-plane helper, without monkey patching or a new backend hierarchy.

## Tasks and acceptance

| Requirement | Task | Acceptance criterion | Result |
| --- | --- | --- | --- |
| FR-1 | T-1: update Agent initialization and mode dispatch | AC-1: AIO mounts with empty skills and never loads host/cloud Skill sources | pass |
| FR-2/3 | T-2: add session binding and remote discovery/loading | AC-2: isolated catalogs, multiple directories, lazy instruction reads and stable multi-turn binding | pass |
| FR-4/5 | T-3: forward tools and handle failures/cleanup | AC-3: remote file roundtrip, edit semantics, timeout/cancellation, safe transport errors and no local fallback | pass |
| FR-1–5 | T-4: run authorized live acceptance | AC-4: a new Session using `doubao-seed-evolving` calls bash and returns the configured `AGENTKIT_TOOL_ID`; host-only environment is absent; all five tools execute successfully | pass |

Affected files: `veadk/agent.py`, `veadk/skills/check_skills_callback.py`, `veadk/tools/skills_tools/skills_toolset.py`, `veadk/tools/skills_tools/aio_sandbox.py`, `tests/skills/test_aio_sandbox_skills.py` and the paired Skills user documentation.

## Review and verification

The user approved the mode/toolset approach and authorized real model and sandbox acceptance. Direct review covered session isolation, compatibility, cancellation, cleanup and credential handling; no `review-spec` skill was available. The English/Chinese documents carry the same requirements and results. The user authorized commit, push and PR creation; no deployment is included.

Verification date: 2026-10-26; scope: the working diff on `feat/newapi`, rebased onto `upstream/main` at `23014771`.

| Check | Command or procedure | Outcome |
| --- | --- | --- |
| Related Python tests | `uv run --extra dev pytest tests/skills tests/tools/test_skills_bash_tool.py tests/tools/test_skills_session_path.py tests/agents -q` | pass: 153 tests |
| Live acceptance | New ADK Session, `doubao-seed-evolving`, actual tool-call responses | pass: Tool ID matched; host environment isolated; file write/read/edit, Skill loading and sandbox reuse verified; temporary fixtures removed |
| Lint, secrets and whitespace | `uv run --extra dev pre-commit run --all-files`; `git diff --check` | pass |
| User documentation | `npm --prefix docs run types:check`; `npm --prefix docs run build` | pass |
| Full regression | `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" --maxfail=3` | fail before rebasing (base `c662cc8d`): 3409 passed, 8 skipped, 6 failed before stopping; 3 migration-delivery tests require missing `zip`, and 3 Harness resource tests require missing `llama_index` |

## Limits and risks

The targeted and live acceptance passed; full-repository regression is not green. Missing executables/optional dependencies were not installed as part of this feature. A transport failure can leave a remote mutation's completion unknown, so such operations are not retried automatically. A sandbox must expose the Skill, file and Bash APIs used by the toolset. No new dependency or unrelated component change is included.
