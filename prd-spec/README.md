# PRD and Design Specification Guidelines

[中文版](README.zh.md)

This directory holds change-specific requirements and designs for VeADK. It adopts the feature/refactor/bugfix organization used by `mpa-codex-worker`, while using VeADK's own component boundaries, tools, and bilingual documentation conventions.

## 1. Document ownership

| Location | Responsibility |
| --- | --- |
| [AGENTS.md](../AGENTS.md) | Repository-wide development workflow and required gates, written in English. |
| `prd-spec/` | Why a particular change is needed, its scope, proposed solution, implementation tasks, and acceptance criteria. |
| [specs/](../specs/README.md) | Maintained component contracts: responsibilities, interfaces, state, data, and failure semantics. |
| [frontend/SPEC.md](../frontend/SPEC.md) | Existing Studio frontend and supporting backend development rules. Do not duplicate or replace them here. |
| `docs/content/docs/`, module READMEs, and `examples/` | User-facing documentation and runnable usage examples. Preserve each area's existing language conventions. |

A PRD describes a change; a component spec describes the maintained contract. Link the two, but do not create competing copies of the same contract.

## 2. Directory structure and naming

```text
prd-spec/
├── README.md
├── README.zh.md
├── features/
│   └── <topic>/
│       ├── YYYY-MM-DD-<description>.md
│       └── YYYY-MM-DD-<description>.zh.md
├── refactors/
│   └── <topic>/
│       ├── YYYY-MM-DD-<description>.md
│       └── YYYY-MM-DD-<description>.zh.md
└── bugfixes/
    └── <topic>/
        ├── YYYY-MM-DD-<description>.md
        └── YYYY-MM-DD-<description>.zh.md
```

- Create category and topic directories when the first actual design needs them; empty scaffolding and placeholder designs are not required.
- Use stable English kebab-case topic names and descriptions. The date is the design's creation date.
- English uses `.md`; Chinese uses `.zh.md`. Both files share the same directory, date, and basename.
- For example, `features/runtime-session-lifecycle/2026-09-10-runtime-session-lifecycle-design.md` and its `.zh.md` counterpart illustrate naming only; they do not declare an implemented feature.
- Use the topic as the stable change ID. If a later independent change reuses the topic, assign it a distinct change ID and link the preceding design.
- A new substantive design iteration gets a new dated pair. For multiple iterations on the same day, add a distinguishing English suffix. Preserve historical designs and link their successors.
- Corrections, review fixes, translations, and implementation-status updates may update the current pair in place. Do not rewrite an old design to conceal a changed decision.

## 3. Classification

| Category | Use for |
| --- | --- |
| `features/` | New user-visible or public SDK capabilities, including extensions to existing behavior. |
| `refactors/` | Internal restructuring that preserves external behavior and contracts. |
| `bugfixes/` | Correcting an existing defect, regression, crash, data error, or interaction failure. |

Choose the category by the intended outcome, not the size of the diff. A public behavior change must not be hidden under a refactor. Clarify mixed or ambiguous scope before implementation.

## 4. Bilingual contract

1. Every design is one complete English document plus one complete Chinese document. Do not split either language into separate PRD, spec, and plan files; keep its requirements, design, tasks, and acceptance criteria together.
2. Add a relative link to the other language near the top of each file.
3. Keep the change ID, revision date, lifecycle status, requirement IDs, task IDs, acceptance IDs, API identifiers, paths, commands, examples, and numeric limits aligned. Translate prose, not program identifiers.
4. Maintain both versions in the same change. The Chinese version is not an abbreviated summary, and the English version is not an optional translation backlog.
5. Review both versions for semantic equivalence. Missing counterparts, stale translations, or conflicting requirements block design approval and delivery; do not silently choose whichever version is convenient.
6. This bilingual rule overrides the Chinese-only default of a generic PRD skill for this repository. It does not change the documentation site's `.mdx` / `.en.mdx` convention.

## 5. Required design content

Each document must be understandable without chat history. Link supporting code and contracts, but restate the essential decisions and acceptance conditions locally.

| Section | Required content |
| --- | --- |
| Metadata | Change ID, creation/revision dates, lifecycle status, counterpart link, related component specs, and predecessor/successor when applicable. |
| Background and evidence | Current behavior, affected users/callers, concrete source or reproduction evidence, and assumptions that remain unverified. |
| Goals and non-goals | What this change must accomplish and what is explicitly outside its scope. |
| Scenarios and requirements | Observable Given/When/Then scenarios and stable `FR-*` requirement IDs, including failure and boundary cases. |
| Design and contract impact | Responsibilities, alternatives and choice, interfaces, state/data, concurrency, permissions, security, compatibility, and affected consumers. Mark irrelevant areas as not applicable with a reason. |
| Implementation tasks | Ordered `T-*` tasks, affected files, dependencies, and links to requirements and tests. |
| Verification and acceptance | `AC-*` criteria, test layers, actual repository commands, required environment, negative cases, and evidence needed to declare completion. |
| Risks and open questions | Unresolved decisions, operational risks, rollout/recovery considerations, and explicitly agreed follow-up work. |
| Review and delivery record | Review findings and resolution, user approval, executed checks and results, skipped/blocked checks with reasons, and remaining scope. |

Use lifecycle states `draft`, `in-review`, `approved`, `implemented`, and `superseded`. Approval requires resolved blockers and user agreement; `implemented` additionally requires completed in-scope tasks and acceptance evidence. Never equate an approved design with a shipped feature.

### Feature emphasis

Describe the user or SDK caller's workflow, new behavior, interface examples, dependencies, errors, and how the capability is reached through its actual entry point. Include integration and end-to-end verification when the change crosses a runtime or UI boundary.

### Bugfix emphasis

Record expected versus actual behavior, reproduction conditions, root-cause evidence, the affected path, and a regression test that fails before the fix. Distinguish a hypothesis from a confirmed cause. Explain why the proposed fix addresses the cause rather than masking the symptom.

### Refactor emphasis

Describe existing coupling or complexity, the new responsibility boundaries, unchanged external contracts, the implementation sequence, and tests that establish behavioral equivalence. Explicitly identify any required data or caller transition; if public behavior changes, reconsider the classification.

## 6. VeADK impact checklist

Only cover affected areas, and explain exclusions where a related contract might reasonably be impacted.

- **Python SDK:** public imports and signatures, Agent/Runner behavior, configuration and defaults, optional dependencies, supported Python versions, examples, and downstream callers.
- **Studio and code generation:** frontend types, server routes, generated Python/configuration/dependencies, deployment payloads, built web assets, and the rules in `frontend/SPEC.md`.
- **Runtime and integrations:** session identity/persistence, stream termination, cancellation, retries, late events, MCP/tools, harness/sidecar behavior, and resource cleanup.
- **Cloud and security:** provider/region boundaries, authorization, credentials, user-controlled URLs/files, redaction, external side effects, and recovery after partial failures.
- **User documentation:** affected Chinese/English pages, example READMEs, and whether users need upgrade or migration instructions.

Do not import `mpa-codex-worker`-specific commands, credentials, deployment authorization, coverage thresholds, or a blanket no-compatibility policy. VeADK is a published SDK as well as Studio; breaking changes require explicit impact analysis and approval.

## 7. Design-to-delivery workflow

1. Inspect the current implementation and relevant contracts, clarify scope, and obtain agreement on the approach before edits.
2. Write the bilingual PRD pair and assess component-spec impact. Create or update the affected bilingual component specs; explain a no-impact conclusion in the PRD.
3. Review requirements, contract consistency, implementation feasibility, tests, and bilingual equivalence. Resolve blockers and record approval before changing production code or tests.
4. Work through the approved tasks using spec-driven development and test-first implementation. A changed requirement returns to design review before its implementation proceeds.
5. Run targeted checks first, then the gates required by `AGENTS.md`, `frontend/SPEC.md`, and affected CI workflows. UI changes require real browser verification; mocked or static checks do not prove live integration behavior.
6. Review the implementation and tests, resolve blocking findings, and reconcile both document languages with the delivered behavior. Record actual commands, outcomes, and any missing verification.
7. Mark the design implemented only when all agreed tasks and acceptance criteria are satisfied. Deferred scope requires explicit user agreement and a traceable follow-up, not a silent status change.

Pure documentation, translation, or formatting work that does not change runtime behavior or public contracts does not need a recursive PRD about the documentation itself. It still requires agreed scope, synchronized language pairs where applicable, and relevant checks.

## 8. Acceptance traceability

Use a compact table in each design, extending it as implementation produces evidence:

| Requirement | Task | Acceptance criterion | Test or verification command | Result/evidence |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1` | `AC-1`: observable outcome | Exact command or manual procedure | `not_run` until executed |

For checks, use `pass`, `fail`, `blocked`, `not_run`, or `not_applicable`; explain the latter three. Include execution date, tested revision/diff scope, and a concise result. Keep evidence in the design unless separate artifacts are necessary; link those artifacts rather than adding a mandatory report hierarchy.

Do not place real API keys, AK/SK, tokens, cookies, signed URLs, personal data, or unredacted production logs in either language version or its evidence.
