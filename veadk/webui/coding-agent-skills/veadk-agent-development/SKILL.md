---
name: veadk-agent-development
description: Build, modify, debug, and cloud-validate VeADK Agents from an accepted product intent. Use for VeADK architecture, tools, workflows, memory, knowledge, executable AgentKit projects, local tests, and AgentKit build/deploy/invoke/log repair loops. Do not use for unrelated user requests, other Agent frameworks, standalone cloud administration, or production Runtime operations.
---

# VeADK Agent Development

根据用户输入意图生成或修改 VeADK Agent，负责实现项目、运行、调试与本地验证、
AgentKit build/deploy 验证，并交付可部署到 AgentKit 的项目。

Turn the accepted user intent into the smallest suitable VeADK Agent and keep working until it
is cloud-validated or truthfully blocked.

## Operating model

Apply **Context over Control**: use the user's goal, acceptance criteria, repository facts,
installed versions, environment capabilities, and fresh execution evidence as context. Choose
and adapt the implementation instead of following a fixed template or command script.

Use only development and validation resources already authorized for the task. Do not ask for
a second “start validation” confirmation. Never treat development authorization as permission
to create, update, release, or delete a production Runtime.

Treat one accepted change as one continuing development effort:

- follow-up instructions refine the same working tree and acceptance context;
- after a user interruption, resume from the current working tree instead of restarting; first
  reconcile any incomplete local command, cloud write, validation Runtime, and completion
  evidence before making another change;
- any source or configuration change invalidates earlier validation evidence;
- complete cloud validation again before presenting a new verified delivery.

Read [`references/agentkit-delivery.md`](references/agentkit-delivery.md) before the first cloud
operation. Load the other references only when their decision is material.

Treat the installed AgentKit CLI as both the developer capability surface and the source of
truth for the installed version. Discover its current command tree and help before choosing a
workflow. Use lifecycle commands such as `init`, `config`, `build`, `deploy`, `status`, `invoke`,
and `runtime` for the normal delivery loop. Use CLI capabilities for knowledge, memory, MCP,
datasets, evaluation, or Skill management only when the accepted intent and
acceptance criteria actually require them; their existence is not a reason to expand the
Agent architecture.

## Hard boundaries

- Read repository instructions and verify every VeADK API, import, tool name, backend, config
  key, and AgentKit flag against the installed or locked version before using it.
- Never read, print, summarize, copy, commit, or package AK/SK, tokens, `.env`, private
  endpoints, or task credentials. Use only the credential mechanism supplied by
  the task context and keep secrets out of commands, logs, Thread text, and Artifacts.
- Do not claim an unexecuted model call, test, service probe, build, deploy, Runtime status,
  invoke, log inspection, or cleanup succeeded.
- Use a fresh validation Runtime for each cloud attempt. Never repurpose a production Runtime.
- Allow at most two complete cloud attempts for one accepted change: the initial attempt and
  one evidence-driven repair attempt. Never loop indefinitely.
- After a source/configuration repair, rerun affected local checks and the full cloud sequence
  from build through cleanup. Do not resume at only the failed step.

## Goal-driven loop

### 1. Understand

Read the user message, relevant conversation context, repository instructions, working tree, dependency
and deployment files, existing tests, and current evidence. Maintain a concise working contract:

- intended Agent behavior and users;
- accepted inputs and observable outputs;
- external systems and side effects;
- constraints, assumptions, and non-goals;
- acceptance criteria that distinguish success from a plausible-looking answer.

Ask only a question whose answer changes the product result, architecture, authority, or an
otherwise unsafe assumption. Continue with explicit reversible assumptions for lesser gaps.
If the preceding turn was interrupted, treat its last operation as indeterminate until fresh
evidence proves its result. Preserve valid source changes, discard incomplete completion
evidence, and reconcile any uniquely named validation Runtime before starting the next attempt.

### 2. Choose the smallest architecture

Start with one `Agent` and the fewest necessary components. Read
[`references/architecture-and-components.md`](references/architecture-and-components.md) when
topology, tools, state, memory, or retrieval is material. Add workflow Agents, sub-agents,
knowledge, memory, MCP, or A2A only when the acceptance criteria require them.

Define inputs, outputs, failure behavior, state ownership, authorization, timeout, and
idempotency for every deterministic stage or side-effecting tool.

### 3. Implement coherently

Follow the existing repository layout. Read
[`references/project-implementation.md`](references/project-implementation.md) for application
and test contracts. For a new empty project, inspect `ak init --help` and
`ak init --list-templates`, then select the application template explicitly from the accepted
intent. Use `agent_server` (`WebServer App`) as the default for a new empty VeADK project when
the intent does not require another protocol. Never run bare `ak init`; pass the explicit
template key supported by the installed CLI. Use `basic` only when the user explicitly needs a
minimal stateless single-entrypoint application, and select streaming or A2A templates only
when those interfaces are material. Adapt and test the generated skeleton instead of recreating
AgentKit lifecycle files from memory. Keep a valid existing project rather than reinitializing
it. Produce only files required for runtime, testing, configuration, or delivery. Ensure the
project root contains a valid `agentkit.yaml` whose entry point starts a persistent service over
HTTP on `0.0.0.0:${PORT:-8000}` and exposes `/ping`.

### 4. Observe locally

Follow [`references/running-debugging-and-validation.md`](references/running-debugging-and-validation.md):

1. run parse/compile and import checks;
2. run focused deterministic and existing regression tests;
3. test tools, state, and retrieval directly before Agent integration;
4. run representative Agent requests when the required model access exists;
5. launch the exact deployment entry point, prove the process stays alive, confirm its
   listener, and require a successful `/ping` response.

An importable `app`, a Runner smoke, or a process that exits with status 0 does not prove the
service is deployable.

### 5. Cloud-validate autonomously

Use the installed AgentKit CLI yourself; do not hand control back to the user or ask them to
click a validation button. Inspect current `--help`, inspect the Artifact inventory, then run:

```text
build → deploy fresh validation Runtime → wait for Ready
→ representative invoke(s) → bounded logs → delete validation Runtime
```

Validate the deployed behavior against the current acceptance criteria, not only liveness.
Classify a failure before acting:

- **code/configuration** — preserve sanitized evidence, repair the smallest root cause, rerun
  affected local checks, and perform the one full cloud revalidation;
- **infrastructure/permission/quota** — do not rewrite correct source; report the external
  blocker and retain useful local evidence;
- **control-plane configuration** — distinguish fixed account/project/region context from the
  unique validation Runtime name; for example, `NotFound.Project` is not an IAM denial;
- **indeterminate remote write** — reconcile Runtime state by the unique validation identity
  before retrying or deleting; never blindly repeat deploy;
- **unsafe Artifact or secret exposure** — stop delivery, remove the exposure, rebuild, and
  state that credential rotation may be required.

### 6. Deliver truthfully

Use one terminal result:

- **`verified`** — current source passed local evidence, fresh Runtime `Ready`, representative
  invoke and acceptance checks, bounded log inspection, and Runtime cleanup;
- **`partial`** — a useful project exists but a required live or cloud check was not completed;
- **`blocked`** — permission, dependency, quota, safety, or remaining-time boundary prevents
  progress;
- **`indeterminate`** — a cloud write may have succeeded but its remote state or cleanup cannot
  yet be established;
- **`failed`** — the current implementation still fails after the one allowed repair attempt.

Report only decision-relevant facts: changed behavior, important architecture choices,
non-secret configuration names, exact evidence actually executed, validation result and cleanup
result, warnings/blockers, and the terminal result. Keep command lines, host-environment details,
filesystem paths, launcher details, and internal tool names out of user-facing progress and
results. When a failure cannot be understood without lower-level evidence, provide only the
smallest sanitized explanation needed to act on it.

Never report `verified` before cleanup is confirmed, and never modify deliverable source after
the successful final build and validation. Keep command output, credentials, prompts,
responses, endpoints, and other sensitive payloads out of completion evidence.

## References

- component and topology decisions: [`references/architecture-and-components.md`](references/architecture-and-components.md)
- project, serving, and test shape: [`references/project-implementation.md`](references/project-implementation.md)
- local runtime and diagnosis: [`references/running-debugging-and-validation.md`](references/running-debugging-and-validation.md)
- AgentKit cloud loop: [`references/agentkit-delivery.md`](references/agentkit-delivery.md)
- VeADK source navigation map: [`references/veadk-python-index.md`](references/veadk-python-index.md)
- secret, Artifact, and failure safety: [`references/security-and-troubleshooting.md`](references/security-and-troubleshooting.md)
- behavior cases: [`tests/test-cases.md`](tests/test-cases.md)
