# Component Specification Guidelines

[中文版](README.zh.md)

This directory holds VeADK's maintained component contracts. A component spec explains what a component owns, what it exposes, and which invariants its implementation and consumers must preserve. It is not a change proposal, implementation diary, or copy of source code.

## 1. Relationship to other documents

- [AGENTS.md](../AGENTS.md) defines the repository-wide development workflow and gates in English.
- [prd-spec/](../prd-spec/README.md) describes individual changes, alternatives, implementation tasks, and acceptance evidence.
- `specs/<component>/` defines the component's maintained responsibilities and behavioral contracts.
- [frontend/SPEC.md](../frontend/SPEC.md) remains the Studio frontend and supporting backend development standard. Component specs reference it rather than redefining visual, interaction, or coding rules.
- User documentation and examples explain how to use the product. Update them when a contract change affects users; a component spec does not replace them.

Keep one owner for each contract. A consumer spec references the owner's contract and describes its own obligations instead of copying the protocol. Implementation is evidence of current behavior, not authority to silently change an approved contract; report and resolve mismatches explicitly.

## 2. Directory structure and naming

```text
specs/
├── README.md
├── README.zh.md
└── <component>/
    ├── README.md
    └── README.zh.md
```

- Use a stable English kebab-case component name based on responsibility, not a release, date, task, or individual source file.
- English is `README.md`; Chinese is `README.zh.md`. Both files describe the same component and revision.
- Create a component directory when an actual change or explicit documentation task requires it. Do not pre-populate speculative contracts or claim undocumented components are already specified.
- Maintain component specs in place. Git history records revisions; dated change proposals belong in `prd-spec/`, not parallel dated component specs.
- Keep each component contract in its README pair by default. Split a genuinely large contract only along clear ownership boundaries, with paired language files and an index; do not create a file per endpoint mechanically.

## 3. Bilingual maintenance

1. Each component spec and these directory guidelines must have complete English and Chinese versions, linked near the top.
2. Keep component IDs, revision dates, status, contract IDs, interface names, fields, state names, paths, commands, numeric limits, and examples synchronized. Translate explanatory prose, not machine-facing identifiers.
3. Update both versions in the same change. Neither version may omit constraints, errors, risks, or compatibility requirements found in the other.
4. Missing, stale, or contradictory counterparts block approval and delivery. Resolve the discrepancy explicitly; neither language independently authorizes a conflicting implementation.
5. Preserve local documentation conventions outside `specs/`; in particular, the documentation site's Chinese `.mdx` and English `.en.mdx` pairing is unchanged.

## 4. Choosing component boundaries

Select boundaries from actual code ownership and runtime responsibilities. The following areas are investigation starting points, not pre-existing component specifications or a mandated directory list:

| Area | Representative implementation locations | Contracts to consider |
| --- | --- | --- |
| Agent execution | `veadk/agent.py`, `veadk/runner.py`, `veadk/agents/` | Public SDK entry points, invocation, event production, delegation, cancellation, and errors. |
| Configuration and models | `veadk/config.py`, `veadk/configs/`, `veadk/models/` | Configuration precedence, validation, provider selection, retries, and credentials. |
| Memory and knowledge | `veadk/memory/`, `veadk/knowledgebase/` | Session identity, persistence, retrieval, isolation, retention, and failure behavior. |
| Tools and protocols | `veadk/tools/`, `veadk/toolkits/`, `veadk/a2a/`, `veadk/a2ui/` | Tool contracts, discovery, protocol mapping, permissions, and untrusted inputs. |
| Runtime and harness | `veadk/runtime/`, `veadk/extensions/harness/`, `veadk/integrations/agentkit/` | Runtime lifecycle, session/stream behavior, sidecar integration, recovery, and resource cleanup. |
| Studio and generation | `frontend/src/`, `frontend/server/`, `veadk/cli/` | UI/server boundaries, API types, project generation, deployment payloads, and generated artifacts. |
| Observability | `veadk/tracing/` and relevant integration code | Logs, traces, metrics, error diagnostics, and redaction. |

Confirm the relevant code, tests, and consumers before defining ownership. A component may span several directories, but its spec must explain that responsibility boundary rather than merely list files.

## 5. Required content

Use this outline for both language versions. Keep applicable sections concrete; mark non-applicable sections with a reason instead of inventing mechanisms.

| Section | Required content |
| --- | --- |
| Metadata and scope | Component ID, status (`draft` or `active`), revision date, counterpart link, owned code, tests, related PRDs, and dependent components. |
| Responsibility and non-goals | What the component owns, what it delegates, and which callers depend on it. |
| Entry points and dependencies | Public imports, CLI commands, HTTP routes, events, internal interfaces, and external systems as applicable. Identify the owner on both sides. |
| Contract | Stable `CON-*` IDs, inputs/outputs, field types, required/default values, validation, errors, and side effects. Include concrete examples for exposed interfaces. |
| State and concurrency | Valid states and transitions, terminal behavior, ordering, duplicate/late events, cancellation, timeouts, retry/idempotency, and restart behavior where applicable. |
| Data and configuration | Source of truth, persistence boundaries, schema/version semantics, configuration precedence, environment variables, and defaults. |
| Security and isolation | Authentication/authorization, identity boundaries, untrusted inputs, credential handling, redaction, and permitted external effects. |
| Compatibility and evolution | Supported caller/dependency versions, breaking-change impact, required consumer updates, migration or recovery when necessary, and explicit deprecation decisions. |
| Observability and failures | Diagnostic signals, error propagation, failure modes, recovery guarantees, and bounded resource behavior. Do not invent metrics that do not exist. |
| Verification | Contract-to-test mapping, negative/boundary cases, integration/E2E requirements, executable repository commands, and required environment. |
| Change record | Related approved PRDs, contract changes, implementation state, verification references, and known limitations. |

A newly drafted component spec must distinguish observed behavior, intended changes, and unresolved questions. `active` means its stated current contract has been reviewed and reconciled with implementation and tests; it does not mean every future proposal is implemented.

## 6. When a spec must change

Assess component-spec impact for every feature, refactor, and bugfix PRD. Create or update a spec when the change affects:

- Component responsibilities, dependency direction, public imports, or shared interfaces.
- HTTP/API/CLI contracts, event schemas, error codes, defaults, or configuration precedence.
- Session/state transitions, stream semantics, persistence, concurrency, cancellation, or recovery.
- Authentication, permissions, credential handling, trust boundaries, or data isolation.
- Compatibility guarantees, generated projects, deployment/runtime behavior, or observability contracts.

Implementation-only changes that preserve these contracts need not modify component specs. Record the no-impact rationale in the PRD. Do not backfill the entire repository's specs just to deliver one scoped change.

## 7. Change and review workflow

1. Inspect the component's current code, tests, consumers, and existing documentation. Separate verified behavior from assumptions.
2. Describe the proposed change in a bilingual PRD and list the affected component contracts by ID.
3. Update both component-spec languages before implementation. Clearly label proposed behavior and link its PRD so it cannot be mistaken for already available behavior.
4. Review PRD/spec consistency, ownership, interface completeness, state/failure behavior, security, compatibility, testability, and bilingual equivalence. Resolve blockers before implementing the contract change.
5. Implement and verify the approved change. Each changed contract must map to a test or explicit validation procedure; runtime or UI boundaries require the relevant integration and end-to-end evidence.
6. Before delivery, reconcile both languages with the actual behavior, remove obsolete proposal labels for implemented changes, and link verification evidence. Do not mark unimplemented guarantees as active.

For an explicit spec-only task, a reviewed proposal may be delivered as documentation, but must remain clearly labeled as proposed; documentation approval is not implementation evidence.

## 8. Verification and completion

Use a compact mapping rather than duplicating the PRD's implementation task list:

| Contract | Guarantee | Test or validation | Evidence |
| --- | --- | --- | --- |
| `CON-1` | Observable invariant | Exact test path/command or procedure | Related PRD verification record or artifact |

- Use VeADK's actual tools and affected CI workflows. Do not introduce nonexistent `make` targets or copy another project's coverage thresholds.
- Check current consumers as well as the changed implementation. SDK compatibility, generated code, frontend types, runtime payloads, and examples must agree where affected.
- Distinguish automated tests, local simulated integrations, and real browser/cloud/provider verification. State what each result does and does not prove.
- Record `pass`, `fail`, `blocked`, `not_run`, or `not_applicable` for checks, with reasons for the last three. A skipped or unexecuted check is not a pass.
- Keep raw execution logs and repeated task reports outside the long-lived contract; link relevant evidence and retain only contract-level conclusions and limitations.
- Never include real credentials, signed URLs, personal data, or unredacted production logs in specifications or evidence.
