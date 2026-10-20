# Skill shell tool naming

[中文](2026-10-20-skill-shell-tool-naming.zh.md)

- Change: skill-shell-tool-naming; date: 2026-10-20; status: approved.
- Scope approval: the user requested this fix after reviewing canonical naming, optional aliases, bounded Sandbox recovery, and error detail preservation. Local commits are authorized by the user; push, SDK publication and deployment remain outside scope.

## Evidence and goals

`SkillsToolset` publishes `FunctionTool(bash_tool)`, whose declared name is `bash_tool`. `SkillsTool` describes execution as "use the bash tool" both in its declaration and its loaded-skill footer. A remote run emitted several valid `bash_tool` calls, then an unknown `bash` call and failed. Wording is a verified ambiguity, not proof of a unique model-level cause or a regression from SDK 1.0.10.

FR-1: SDK-generated execution instructions must name the actual callable, `bash_tool`, in both the tool description and loaded-skill footer. Preserve user-authored Skill content verbatim.
FR-2: Keep tool names, schemas, execution, imports and signatures compatible. Do not introduce a `bash` alias or rename an existing tool.

## Design and contracts

Read the canonical function name from the existing shell callable rather than maintaining another spelling. Update only SDK-owned instruction text. Existing SkillsToolset discovery, registry, installation, working directory, environment, file handling, authorization and execution contracts remain unchanged; no component-spec change is required because this corrects descriptive wording to match the existing interface.

Final scope: the user excluded `actb-mono` because releasing that repository is costly. All Sandbox callback code, tests and changelog changes have been withdrawn. Keep only SDK naming corrections and bounded, redacted error details in the samples bridge. Unknown tool calls can still fail; no automatic recovery is provided. This SDK change does not automatically update a deployed Sandbox image.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification | Result |
| --- | --- | --- | --- | --- |
| FR-1 | T-1: add regression tests | AC-1: instruction names equal the real FunctionTool declaration | `uv run --extra dev pytest tests/skills/test_skill_tool_names.py` | passed |
| FR-1 | T-2: fix generated strings | AC-2: loaded Skill body remains intact, footer uses canonical name | same tests | passed |
| FR-2 | T-3: regression and review | AC-3: existing Skill installation/loading tests pass; tool declarations unchanged | targeted skills tests; Ruff; diff whitespace | passed |

## Review, risks and delivery

Direct design review completed: naming and evidence agree with current code; scope preserves interfaces and privileges; tests compare instructions to a real declaration. No review-spec skill is available, so the equivalent feasibility, compatibility, failure-boundary, testability and bilingual checks were performed directly. No unresolved design blockers. User approval is recorded above.

Skill-authored references to generic "bash" are outside SDK-generated wording. Probabilistic model output may still use an unknown tool name; automatic recovery is outside the approved scope. Image rebuild/release is a separate deployment action. Cloud provisioning timeouts are outside this change.

## Verification results

New regression tests failed before the fix and passed afterward. Naming, installation, callback and ADK toolset suites: 30 passed. Ruff E/F/I checks and diff whitespace checks passed. No SDK release; deployed Sandboxes require a later image build using the updated SDK.
