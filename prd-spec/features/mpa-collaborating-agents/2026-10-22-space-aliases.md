# Space-shared aliases and explicit A2A mentions

Change ID: agentkit-a2a-collaborators | Date: 2026-10-22 | Status: approved
[中文](2026-10-22-space-aliases.zh.md)

## Evidence, goals and boundaries

A2ACenter.tsx lists AgentKit registrations through the selected Runtime; a2aSpace.ts validates responses. The user explicitly approved editing aliases shared by all MPAs connected to a space, plus @alias/@AgentCardName dispatch, without changing AgentKit. Alias metadata belongs in the existing shared management PostgreSQL database, not browser storage or individual Runtime business databases. Runtime owns persistence, resolution and authorization. Studio owns editing and feedback. No autocomplete, multiple-target orchestration, cache or cloud write is included.

## Requirements and design

FR-1: Show an optional alias on each center member; edit and clear through the existing administrator-authenticated Runtime proxy. Reuse Input, FormLabel and Button plus existing form styles. Empty means clear; preserve original center name. Explain the alias is shared within the space. Normalization and uniqueness are server authoritative.
FR-2: PUT /api/v1/studio/collaborators/registry/aliases/{agent_id} accepts {space_id, alias:string|null, revision:int}; returns {alias,revision}. List adds Alias, AliasRevision and AliasAvailable. Old Runtime responses leave editing unavailable. Missing shared DB/account configuration is explicit, not local-storage fallback. Revision conflict and duplicate name have distinct feedback. An uncertain write requires refresh; no automatic mutation retry.
FR-3: A current-message prefix @name followed by whitespace/task, or @"name with spaces", identifies exactly one target. Runtime resolves the union of aliases and actual Card.name in the bound space, with NFKC/casefold comparison, then validates the dispatch ID. Ambiguity, missing name, incomplete directory, multiple leading targets or missing task prevents dispatch. Text within quotes/code, emails and ordinary body mentions do not route. This behavior is implemented in Runtime, not as a browser text rewrite.

## Scenarios, tests and acceptance

AC-1 / FR-1: Given a listed member, editing/clearing saves and displays server-confirmed data; original name and space selection remain. Tests: frontend/tests/a2aAlias.test.tsx.
AC-2 / FR-2: Conflict retains input; refresh restores latest revision. Abort/unmount discards late replies. IME cannot submit early; duplicate clicks produce one request. Missing capability disables editing with an explanation. Same test file and real browser check.
AC-3 / FR-3: Two Runtime business databases use one alias store; exact name resolution and mismatched dispatch are covered in agentkit-mpa-agent/tests/test_a2a_aliases.py. No remote Agent invocation is claimed by mocked tests.

## Tasks, risk and review

T1 write failing UI tests; T2 typed response projection/editor and translations; T3 npm test/build, browser normal/error/keyboard/narrow checks; T4 update paired specs and verification. No Python Studio server changes needed because the existing Runtime proxy carries these routes. No generated Agent code change. No external dependency.

Shared database configuration and privileges must be present on the Runtime; old instances require updated Runtime code. Reload after uncertain writes before retrying. Rollback the UI/Runtime while retaining new optional metadata. Source review checked account/space isolation, CAS and normalization ownership. User approval is the current request to implement both repositories; detailed @ grammar is the documented implementation default. Local verification is recorded below; no publication/deployment performed.


## Local verification

Implemented in Studio and Runtime. Studio Node tests:1389 passed; Vitest:192 passed; production build passed. A real-browser local fixture of the editor (mock transport) verified save, clear, duplicate-name feedback, Escape/focus and a320px column. No cloud calls, deployment or model end-to-end acceptance is claimed. Runtime evidence: agentkit-mpa-agent/docs/verification/agentkit-a2a-collaborators/alias-verification.md.

> Superseded storage decision: see `prd-spec/bugfixes/mpa-agent-alias/2026-10-22-agent-alias-business-store.md`. Registered Agent aliases now belong to the current MPA business database.
