---
name: agentkit-cli
description: Drive the agentkit CLI (aliases agentkit / ak) to scaffold, build, deploy, and manage agents on Volcengine AgentKit from the terminal — runtimes, knowledge bases, memory collections, tools, harnesses, invocation, SSO auth, sandboxes, and evaluation datasets. Use when a user wants to create/deploy an agent project, call or inspect a deployed runtime, manage AgentKit resources, or resolve a CLI/auth/deploy error. Does NOT handle non-AgentKit deployment, general Docker/k8s operations, Volcengine IAM management, or writing agent application code (use veadk-agent-development for that).
---

# AgentKit CLI

The `agentkit` CLI (also aliased `ak`) scaffolds, builds, deploys, and manages agents on
Volcengine AgentKit. It signs Volcengine OpenAPI requests, so every command needs
credentials (see **Authentication**). Optimize for a tight loop:
**init → deploy → invoke → iterate**.

For the exhaustive command list with one-liners and examples, read
**`references/commands.md`** — locate it and read it rather than guessing at flags. When
in doubt about what exists, run `agentkit tree` (add `--all` for args/options, `--json`
for machine output).

## When to Use This Skill

- Scaffolding a new agent project (`init`) and shipping it (`deploy`)
- Calling a deployed runtime (`invoke`) or inspecting one (`runtime show/logs/versions`)
- Managing AgentKit resources: knowledge bases, memory collections, tools, datasets
- Building a code-free agent from a `harness.yaml` (`harness`)
- Signing in via SSO or switching login profiles (`auth`)
- Diagnosing a CLI, auth, build, or deploy failure

## Authentication

Every command signs a Volcengine OpenAPI request; without credentials it fails. Provide
them one of two ways:

- **SSO (recommended)** — a browser login that stores short-lived STS credentials:

  ```bash
  agentkit login <sso-address>     # opens a browser, stores an STS session
  agentkit whoami                  # confirm the active identity
  ```

  `login` / `logout` / `whoami` are available both under `auth` and at the top level.
  Multiple SSO targets are handled with login profiles (`auth profile set/list/show`).

- **AK/SK** — set in the environment or a git-ignored local `.env`:

  ```bash
  VOLCENGINE_ACCESS_KEY=<ak>
  VOLCENGINE_SECRET_KEY=<sk>
  VOLCENGINE_REGION=cn-beijing      # optional; this is the default
  ```

Region is auto-sensed per resource; override any command with `-r, --region`.

## Core Workflow: init → deploy → invoke

```bash
# scaffold a project from a language + template
# templates: verify current support with agentkit init --list.
# Python ships basic-agent (default), veadk-agent-app, and several
# agent-with-* channel templates; Go / Java / TypeScript ship basic-agent only.
# `agentkit-harness` is NOT a template — it's the `agentkit harness` command
# path (code-free agent from a harness.yaml). See "Code-Free Agents (harness)".
agentkit init my-agent -L python -t basic-agent
cd my-agent

# ... edit the agent (instruction, tools) ...

# one-shot build & deploy — runs config → build → apply
agentkit deploy --name my-agent

# call the deployed runtime (resolves endpoint + auth automatically)
agentkit invoke my-agent -m "hello"

# when something misbehaves, read the cloud instance logs
agentkit runtime logs my-agent --limit 100
```

`deploy` is the composite of three steps you can also run individually:

| Step | What it does |
| --- | --- |
| `deploy config` | scaffold `.agentkit/` (`agentkit.yaml` + `Dockerfile`) for the project |
| `deploy build`  | build the image in the cloud and write the artifact |
| `deploy apply`  | create/update the runtime from the latest built artifact |

Run them separately when you want to inspect or hand-edit `agentkit.yaml` / the
`Dockerfile` between scaffolding and building.

`init` generates `.agentkit/agentkit.yaml` from a single source, so every
language/template starts from the same, current config. `deploy` is **yaml-driven** —
runtime resources, `envs` (`${VAR}` refs, never plaintext secrets), gateway `auth`,
an `im.feishu` bot proxy, and an SSO `frontend` BFF are all declared there, no flags
needed. The model credential is resolved on the cloud runtime from its mounted
IAM role / AK-SK, so do **not** set `MODEL_AGENT_API_KEY`.

## Managing a Runtime

```bash
agentkit runtime list                         # all runtimes
agentkit runtime show my-agent --rev 3        # details for a specific version
agentkit runtime versions my-agent            # version history
agentkit runtime release my-agent --rev 3     # publish a version → live
agentkit runtime update my-agent \            # change config; add --auto-release to publish
  --min-instance 1 --max-instance 5 --auto-release
agentkit runtime logs my-agent --instance <id> --limit 100
agentkit runtime delete my-agent -y
```

`update` changes configuration but does **not** publish unless you pass `--auto-release`;
otherwise follow it with `runtime release`.

## AgentKit Resources

Knowledge bases (`knowledge`, alias `kb`), memory collections (`memory`, alias `mem`),
and tools (`tool`) share the same `list / show / create / update / delete` shape:

```bash
agentkit kb list
agentkit kb create --name my-kb                     # auto-provisions a new viking KB
agentkit kb create --name my-kb --provider-knowledge-id kb-xxxx   # register an existing one
agentkit kb add my-kb ./notes.md ./docs             # upload + index files or whole dirs (or --url)

agentkit mem list
agentkit mem create --name my-mem --provider-type viking

agentkit tool list
agentkit tool create --name my-mcp --tool-type McpServer --image-url <url> --port 8080
```

## Code-Free Agents (harness)

A harness is an agent defined entirely by a `harness.yaml` — no application code:

```bash
agentkit harness init my-harness              # writes harness.yaml + .env.example
agentkit harness set --name my-agent \        # partial update; run with no flags to list fields
  --model-name doubao --system-prompt "You are helpful."
agentkit harness deploy                       # build the harness image + create/update the runtime
```

## Evaluation

The eval loop is **dataset → evaluator → run → results**. The `eval` prefix is
optional (`agentkit dataset …` == `agentkit eval dataset …`).

Datasets ("evaluation sets") hold cases; verbs distinguish the target —
`create`/`delete` act on the dataset, `add`/`remove` on its cases:

```bash
agentkit dataset create --name my-dataset --schema question,answer
agentkit dataset add my-dataset --field 'input=最大的行星?' --field 'reference_output=木星'
agentkit dataset show my-dataset --items 20   # lists cases WITH their ITEM IDs
agentkit dataset remove my-dataset <item-id>  # remove by ITEM ID from `dataset show`
```

An evaluator is a scoring rubric + judge model; submit an experiment against a
deployed runtime, then read the scores:

```bash
agentkit eval evaluator create --name my-judge \       # clone a preset template
  --from-template <template-id> --model ep-xxxxxxxx
agentkit eval run --dataset my-dataset \               # dataset × evaluators × runtime
  --evaluator my-judge --target my-agent
agentkit eval experiment results <id> --limit 20       # per-row input/output/scores
```

## Conventions

- **Aliases:** `knowledge`↔`kb`, `memory`↔`mem`, `experiment`↔`exp`; the `eval` prefix is optional.
- **JSON output:** most read commands accept `--json` for scripting.
- **Region:** auto-sensed unless you pass `-r, --region`.
- **Confirmation:** destructive commands (`delete`, `remove`, `destroy`) prompt; pass `-y` to skip.
- **Self-service:** `agentkit docs` opens the documentation; `agentkit upgrade` updates the CLI itself.

## Gotchas

- **Auth first.** Every command hits the signed OpenAPI. If commands fail with an auth
  error, run `agentkit whoami`; re-`login` if the STS session has expired.
- **`deploy` builds in the cloud**, not locally — the `Dockerfile` must use a
  Volcengine-hosted base image and no `# syntax=` directive (cloud builds can't reach
  Docker Hub). Install dependencies from PyPI.
- **`update` ≠ release.** `runtime update` stages configuration; the change is not live
  until a `runtime release` (or `--auto-release`).
- **`invoke` resolves the endpoint** from the runtime name/id automatically — you don't
  pass a URL. It auto-detects the runtime's route (`/run_sse` vs `/invoke`).
- **Read `runtime logs`** for the cloud instance's stdout/stderr when a deploy is Ready
  but the agent misbehaves; that's where model-credential and startup errors surface.
