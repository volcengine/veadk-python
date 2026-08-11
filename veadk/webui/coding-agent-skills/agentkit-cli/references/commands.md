# AgentKit CLI — Command Reference

## Overview

```text
agentkit
├─ init                 scaffold a new agent project from a template
├─ deploy               build & deploy the project (config → build → apply)
│  ├─ config            scaffold .agentkit/ (agentkit.yaml + Dockerfile)
│  ├─ build             build the image in the cloud, write the artifact
│  └─ apply             create/update the runtime from the built artifact
├─ runtime              manage runtimes
│  ├─ list / show / delete / logs / versions / release / update
├─ knowledge (kb)       manage knowledge bases
│  ├─ list / show / create / add / update / delete
├─ memory (mem)         manage memory collections
│  ├─ list / show / create / update / delete
├─ tool                 manage tools
│  ├─ list / show / create / update / delete
├─ sandbox              operate a `code` tool: run commands, manage sessions
│  ├─ run / shell / cp / web / login / sessions / logs / rm
├─ harness              code-free agent from a harness.yaml
│  ├─ init / set / deploy
├─ invoke               call a deployed runtime
├─ auth                 SSO auth  (login/logout/whoami also top-level)
│  ├─ login / logout / whoami
│  └─ profile           set / list / show
├─ onboard              install bundled skills into local coding agents
├─ eval                 evaluation
│  ├─ dataset           datasets  (also top-level: `agentkit dataset …`)
│  │  ├─ list / show / create / delete      # dataset resource
│  │  └─ add / remove                        # cases inside a dataset
│  ├─ evaluator         scoring rubrics / judges
│  │  ├─ templates / list / show / create / delete
│  ├─ experiment (exp)  list / get / results
│  └─ run               submit an experiment (dataset × evaluators × runtime)
├─ skill                manage skills on the AgentKit skill platform
│  ├─ list / show / versions / spaces / delete
├─ destroy              delete the deployed runtime (by name or local config)
├─ upgrade              upgrade the agentkit CLI to the latest version
├─ docs                 open the AgentKit CLI documentation in a browser
└─ tree                 print the full command tree
```

Notes:

- `knowledge`↔`kb`, `memory`↔`mem`, `experiment`↔`exp` are aliases.
- Like `auth login`, the `eval` prefix is optional: `agentkit dataset …` == `agentkit eval dataset …`.
- Most read commands accept `--json`; region is auto-sensed unless you pass `-r, --region`.

---

## init

Scaffold a new agent project from a language/template. Every language has
`basic-agent`; **Python** additionally has `agent-with-feishu-bot` and
`agent-with-sso-frontend` — an internal IT service-desk demo agent (KB lookup,
support tickets, leave balance) delivered via a Feishu bot / public SSO frontend,
with `im.feishu` / `frontend` pre-enabled in the generated `.agentkit/agentkit.yaml`.

```bash
agentkit init my-agent -L python -t basic-agent
agentkit init my-agent -L python -t agent-with-feishu-bot
```

## deploy

One-shot build & deploy of the current project (runs config → build → apply).

```bash
agentkit deploy --name my-agent --project default
```

### deploy config

Scaffold `.agentkit/` (`agentkit.yaml` + `Dockerfile`) for the project. `init`
already writes an `agentkit.yaml` from the same single source, so you normally
edit that file rather than re-scaffolding.

```bash
agentkit deploy config --name my-agent
```

`agentkit deploy` is fully **yaml-driven** — everything lives in
`.agentkit/agentkit.yaml`, no flags required. Secrets are referenced from the
deploy environment with `${VAR}` (`${VAR}` required · `${VAR:-default}` ·
`${VAR:?message}`), never committed. Notable optional blocks:

- `envs:` — runtime environment variables (declare each explicitly with `${VAR}`).
- `auth:` — gateway auth (`key_auth` or `custom_jwt`); auto-derived when `frontend` is set.
- `im.feishu:` — deploy a Feishu bot proxy after the runtime (see the Feishu workflow).
- `frontend:` — deploy a public SSO frontend BFF (see the SSO-frontend workflow).

The model credential is derived from your Volcengine AK/SK on the cloud runtime,
so you do **not** set `MODEL_AGENT_API_KEY` there.

### deploy build

Build the image in the cloud and write the artifact.

```bash
agentkit deploy build
```

### deploy apply

Create/update the runtime from the latest built artifact.

```bash
agentkit deploy apply
```

## runtime

### runtime list

List all runtimes.

```bash
agentkit runtime list
```

### runtime show

Show a runtime's details (optionally a specific version).

```bash
agentkit runtime show my-agent --rev 3
```

### runtime delete

Delete a runtime.

```bash
agentkit runtime delete my-agent -y
```

### runtime logs

Show logs for a runtime instance.

```bash
agentkit runtime logs my-agent --instance <id> --limit 100
```

### runtime versions

List a runtime's version history.

```bash
agentkit runtime versions my-agent
```

### runtime release

Release (publish) a runtime version, making it live.

```bash
agentkit runtime release my-agent --rev 3
```

### runtime update

Update a runtime's configuration (does not release unless `--auto-release`).

```bash
agentkit runtime update my-agent --min-instance 1 --max-instance 5 --auto-release
```

## knowledge (kb)

### knowledge list

List all knowledge bases.

```bash
agentkit knowledge list
```

### knowledge show

Show a knowledge base's details.

```bash
agentkit knowledge show <id>
```

### knowledge create

Create a knowledge base. With no `--provider-knowledge-id`, a new **viking**
knowledge base is auto-provisioned (via the Viking KB API) and registered;
pass an id to register an existing provider-side KB instead.

```bash
agentkit knowledge create --name my-kb                        # auto-provision a viking KB
agentkit knowledge create --name my-kb --provider-knowledge-id kb-xxxx  # register an existing one
```

### knowledge add

Add documents to a (viking) knowledge base: upload local files/directories to
TOS and register them, or add by public URL. Directory arguments are uploaded
recursively (hidden entries skipped). Indexing runs asynchronously.

```bash
agentkit knowledge add my-kb ./notes.md ./guide.pdf     # individual files
agentkit knowledge add my-kb ./docs                     # a whole directory, recursively
agentkit knowledge add my-kb --url https://example.com/doc.md
```

### knowledge update

Update a knowledge base.

```bash
agentkit knowledge update <id> --description "product docs"
```

### knowledge delete

Delete a knowledge base.

```bash
agentkit knowledge delete <id> -y
```

## memory (mem)

### memory list

List all memory collections.

```bash
agentkit memory list
```

### memory show

Show a memory collection's details.

```bash
agentkit memory show <id>
```

### memory create

Create a memory collection.

```bash
agentkit memory create --name my-mem --provider-type viking
```

### memory update

Update a memory collection.

```bash
agentkit memory update <id> --description "user preferences"
```

### memory delete

Delete a memory collection.

```bash
agentkit memory delete <id> -y
```

## tool

### tool list

List all tools.

```bash
agentkit tool list
```

### tool show

Show a tool's details.

```bash
agentkit tool show <id>
```

### tool create

Create a tool.

```bash
agentkit tool create --name my-mcp --tool-type McpServer --image-url <url> --port 8080
```

### tool update

Update a tool.

```bash
agentkit tool update <id> --image-url <url>
```

### tool delete

Delete a tool.

```bash
agentkit tool delete <id> -y
```

## harness

Code-free agent defined entirely by a `harness.yaml`.

### harness init

Create a harness directory (`harness.yaml` + `.env.example`).

```bash
agentkit harness init my-harness
```

### harness set

Set fields in `harness.yaml` (partial update; run with no flags to list them).

```bash
agentkit harness set --name my-agent --model-name doubao --system-prompt "You are helpful."
```

### harness deploy

Build the harness image and create/update the runtime from `harness.yaml`.

```bash
agentkit harness deploy
```

## invoke

Call a deployed runtime by name or id (resolves endpoint + auth automatically).

```bash
agentkit invoke my-agent -m "hello"
```

## auth

SSO authentication. `login` / `logout` / `whoami` are also available at the top level.

### auth login

Authenticate via browser SSO and store short-lived STS credentials.

```bash
agentkit login sso.example.com
```

### auth logout

Clear the stored SSO session.

```bash
agentkit logout
```

### auth whoami

Show the identity behind the current credentials.

```bash
agentkit whoami
```

### auth profile set

Create or update a login profile's coordinates.

```bash
agentkit auth profile set prod --issuer <url> --client-id <id> --role-trn <trn>
```

### auth profile list

List saved profiles.

```bash
agentkit auth profile list
```

### auth profile show

Show a profile's coordinates (default: active).

```bash
agentkit auth profile show prod
```

## onboard

Install the bundled agent skills into your local coding agents (Claude Code, Codex, Trae).

```bash
agentkit onboard --agent claude-code,codex --scope project
```

## eval dataset

Manage evaluation datasets ("evaluation sets") and their case items. The `eval`
prefix is optional (`agentkit dataset …`). Verbs distinguish the target:
`create`/`delete` act on the dataset, `add`/`remove` act on its cases.

### dataset list

List evaluation datasets.

```bash
agentkit dataset list
```

### dataset show

Show a dataset's details, schema, and case items (with their ITEM IDs).

```bash
agentkit dataset show my-dataset --items 20
```

### dataset create

Create a dataset (schema defaults to `input,reference_output,output`).

```bash
agentkit dataset create --name my-dataset --schema question,answer
```

### dataset delete

Delete a dataset (and all its cases).

```bash
agentkit dataset delete my-dataset -y
```

### dataset add

Add one or more cases to a dataset (fields must match the schema).

```bash
agentkit dataset add my-dataset --field 'input=最大的行星?' --field 'reference_output=木星'
```

### dataset remove

Remove cases by ITEM ID (get IDs from `dataset show`).

```bash
agentkit dataset remove my-dataset 7590105346029796098
```

## eval evaluator

An evaluator is a scoring rubric + judge model. Create one by cloning a preset
template and pointing it at your Ark model endpoint.

### eval evaluator templates

List preset evaluator templates to create from.

```bash
agentkit eval evaluator templates
```

### eval evaluator list / show / delete

```bash
agentkit eval evaluator list
agentkit eval evaluator show <id>          # rubric, model, input schema
agentkit eval evaluator delete <id> -y
```

### eval evaluator create

Clone a template's rubric + input schema and set your judge model.

```bash
agentkit eval evaluator create --name my-judge \
  --from-template <template-id> --model ep-xxxxxxxx
```

## eval run

Submit an experiment: a dataset × one or more evaluators × a deployed runtime
(the eval target). Use `--map` to override the default field mapping between the
dataset columns and the evaluator/target fields.

```bash
agentkit eval run --dataset my-dataset --evaluator my-judge --target my-agent
agentkit eval run --dataset my-dataset --evaluator my-judge --target my-agent --dry-run
```

## eval experiment (exp)

Inspect submitted experiments.

```bash
agentkit eval experiment list
agentkit eval experiment get <id>            # status, dataset/target/evaluators, scores
agentkit eval experiment results <id> --limit 20   # per-row input, output, scores
```

## sandbox

Operate a sandbox (a `code` tool): run commands and manage live sessions.

```bash
agentkit sandbox run --tool-id <id> -- 'python --version'
agentkit sandbox shell --tool-id <id>        # interactive terminal (Ctrl-] to detach)
agentkit sandbox cp ./local.txt :/work/      # ':' prefixes the remote side
agentkit sandbox sessions                     # list active sessions
agentkit sandbox rm --all                     # stop & delete sessions
```

## skill

Manage skills on the AgentKit skill platform.

```bash
agentkit skill list
agentkit skill show <id>
agentkit skill versions <id>
agentkit skill spaces
agentkit skill delete <id> -y
```

## destroy

Delete the deployed runtime (by name, or resolved from the local config).

```bash
agentkit destroy --name my-agent -y
```

## upgrade

Upgrade the agentkit CLI itself to the latest published version (alias `update`).

```bash
agentkit upgrade
```

## docs

Open the AgentKit CLI documentation in a browser (`--print` to just print the URL).

```bash
agentkit docs
```

## tree

Print the full command tree (add `--all` for args/options, `--json` for machine output).

```bash
agentkit tree
```
