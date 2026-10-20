# AgentKit Delivery

Use the installed AgentKit CLI directly to validate the current working tree in a temporary
cloud Runtime.

## Task environment

Verify these environment facts at runtime instead of inventing values:

- `ak` and `agentkit` are installed;
- the current working directory contains the intended project;
- task-scoped cloud credentials are available outside the deliverable project;
- production deployment remains a separate user-confirmed action.

## Credentials

Use the task-provided credential mechanism exactly as task context describes. Never open a
credential file to inspect values and never echo the environment. Keep credential material
outside the project and Artifact. Do not pass AK/SK as CLI flags because they
can leak through process listings, command history, tool traces, or Thread output.

If the credential contract is absent or invalid, finish safe local checks and report cloud
validation as blocked. Do not search home directories for alternative credentials.

## Verify the installed CLI

Before cloud work, run non-secret discovery commands such as:

```bash
ak --version
ak --help
ak init --help
ak init --list-templates
ak config --help
ak build --help
ak deploy --help
ak status --help
ak invoke run --help
ak runtime show --help
ak runtime logs --help
ak runtime delete --help
```

The reviewed environment currently exposes AgentKit CLI `0.52.1`, where `ak init` provides
version-aligned project templates and the project flow supports `ak config`, `ak build`,
`ak deploy`, `ak status`, `ak invoke run`, and Runtime show/log/delete commands. Treat this as
a reviewed baseline only; follow actual help when the installed version differs.

The CLI also exposes higher-level developer capabilities such as lifecycle `launch`/`release`,
datasets and evaluation, knowledge and memory resources, MCP, and Skill management.
Select these from the accepted product requirements, not from a fixed showcase checklist.
Prefer the smallest observable workflow: for example, do not provision a knowledge base when a
deterministic local corpus satisfies the contract, and do not run an evaluation campaign when a
small set of representative acceptance invokes is sufficient. Conversely, when quality targets
explicitly require a dataset or scored evaluation, use the installed `ak dataset`/`ak eval`
help and preserve its sanitized result as additional evidence.

## Prepare a validation attempt

Before spending a cloud attempt:

1. require relevant local tests and the exact process-level `/ping` probe to pass;
2. inspect the recursive Artifact inventory, not only ignore patterns;
3. require a valid project-root `agentkit.yaml` and verify its entry point exists;
4. choose a unique validation Runtime name derived from the task/session and attempt number;
5. ensure the name cannot collide with a production Runtime;
6. record the working-tree state that the attempt validates.

Keep the AgentKit control-plane project separate from that unique Runtime identity. Use the
existing validation project supplied by task configuration (normally `default`) and set
`launch_types.cloud.project_name` to that exact value. Never derive `project_name` from the
validation Runtime, image repository, pipeline, or Agent name. Confirm the effective value with
the installed CLI before build. A `CreateRegistry: NotFound.Project` response means the project
configuration is wrong or unavailable; it is not evidence of missing IAM permission. Correct
the configuration and restart the complete attempt rather than asking for broader credentials.

Do not mutate an unrelated Runtime. Use at most two attempts for one accepted user change.

## Complete one cloud attempt

Use the flags proven by current help. A typical `0.52.1` project flow is:

```bash
ak config --runtime_name <unique-validation-name>
ak build --config-file agentkit.yaml
ak deploy --config-file agentkit.yaml
ak status --config-file agentkit.yaml --verbose
ak invoke run --config-file agentkit.yaml --payload '<json>' --raw
ak runtime logs <runtime-id-or-name> --limit 200 --json
ak runtime delete <runtime-id-or-name> --yes
```

These commands are examples of the reviewed version, not permission to skip `--help`. Use the
credential launcher for commands that require cloud access. Never include credential values
in the command line.

Poll readiness with a bounded deadline. Preserve only bounded, sanitized output. Run enough
representative invokes to cover the material acceptance criteria; `/ping` or Runtime `Ready`
alone is insufficient.

Inspect logs for startup, authentication, model, tool, state, request, crash, timeout, and
secret-exposure failures. A warning is non-blocking only when it does not violate intended
behavior, safety, or trace requirements.

## Repair and full revalidation

On the first code/configuration failure:

1. retain the failed stage and sanitized evidence;
2. reconcile and delete the failed validation Runtime;
3. identify and repair the smallest evidence-backed cause;
4. rerun affected local tests and the exact service probe;
5. select a new validation Runtime identity;
6. rerun the complete cloud sequence beginning with `build`.

Do not reuse a previously built Artifact after source/configuration changes. Do not perform a
third cloud attempt for the same accepted change.

For a deploy timeout or malformed remote response, the Runtime may still exist. Query by the
unique validation name before deciding whether to retry or delete. If existence or cleanup
cannot be established, return `indeterminate` rather than claiming failure or success.

## Resume after user interruption

Stopping a reply interrupts the current turn; it does not prove that the last local process or
cloud write rolled back. On the next accepted message in the same conversation:

1. inspect the current working tree and retain coherent source changes instead of reinitializing;
2. treat the interrupted command and prior completion evidence as incomplete;
3. query every validation Runtime identity already used by the interrupted turn;
4. delete the Runtime or prove it absent before starting another cloud attempt;
5. rerun the affected local checks and, after any source/configuration change, the complete
   cloud sequence from build through cleanup.

If the interrupted turn had already started a cloud deployment, count that real attempt when
applying the two-attempt limit for the same accepted change. A new follow-up requirement starts
a new acceptance cycle, but it still must reconcile resources left by the previous cycle. Never
claim that the interruption itself cleaned a Runtime, and never discard a valid working tree only
to make recovery simpler.

## Completion evidence

Cloud validation is complete only when the current source has evidence for:

- successful build and deploy;
- a fresh Runtime reaching `Ready`;
- representative invoke results satisfying current acceptance criteria;
- bounded logs with no blocking error;
- deletion or confirmed absence of the validation Runtime.

After the final successful build begins, do not change deliverable source unless you invalidate
that attempt and run the complete cloud sequence again. AgentKit CLI currently archives its
build context in memory and uploads it directly; do not invent or search for a local `ak build`
archive path. Leave the verified working tree unchanged and report it as the deliverable.

The validation Runtime is temporary evidence, not the production service. Preserve the
project and sanitized evidence; leave production deployment to the user.
