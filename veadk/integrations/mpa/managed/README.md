# Managed MPA creation

[中文版](README.zh.md)

VeADK prepares MPA prerequisites and deploys an agent without an `agentkit-mpa-agent` source checkout. Studio and `veadk mpa provision` use the same implementation. The deployed MPA image must support account-shared APIG registration and metadata bootstrap.

## Server setup

1. Copy the [example YAML](../../../../prd-spec/features/mpa-agent-oneclick-provision/mpa-create.config.example.yaml) to a private `mpa-create.config.yaml`. Keep filled-in configuration outside Git.
2. Supply an existing PostgreSQL instance, shared registry database, database login/owner, Runtime/worker IAM roles, images and model access. The deployment administrator needs `CREATEDB` and permission to assign the business database owner. The registry needs schema-write permissions and direct/session pooling; transaction pooling is incompatible with advisory locks.
3. Set `DEPLOYMENT_DATABASE_ADMIN_URL` and `SHARED_APIG_DATABASE_URL` in the CLI/Studio environment. These are PostgreSQL connection URLs; the YAML stores environment variable names. Flat/template secrets support complete `${ENV_NAME}` references. Do not expose these variables in browser configuration.
4. Configure deployment credentials through a rotating `managed.credential-file` or `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY` and optional `VOLCENGINE_SESSION_TOKEN`. Without an explicit file or environment key pair, the mounted `/var/run/secrets/iam/credential` is used. Each cloud call refreshes credentials; Runtime, VPC, worker and APIG use the same verified account.
5. Select a template source: `managed.from-runtime`, a private JSON `managed.template-file`, or the flat image/model/PostgreSQL fields. Reference mode removes agent-specific channel credentials and Skill Space identity. Configure `managed.worker.image` for a dedicated worker (optional `reference-id` for worker environment settings), or use an explicit `existing-id` after verifying compatibility.
6. For a private PostgreSQL host, set the reachable `managed.network.vpc-id` and `subnet-ids`. Automatic network creation does **not** configure database allowlists, peering, or cross-VPC routes. An explicit `managed.apig.adopt-id` requires that VPC ID and a compatible gateway. Otherwise the account's registered gateway is reused or created.
7. Set `VEADK_MPA_CREATE_CONFIG` to the private YAML's absolute path in the Studio process environment and start Studio normally. One profile serves its configured region; other regions display a configuration error. This path supports Volcengine.

The deployment identity needs access to AgentKit Runtime, Skill Space and Tool operations, VPC/subnet operations, APIG/IM Gateway operations and `GetCallerIdentity`. The Runtime/worker roles separately need the permissions and mounted credentials required by their images. IAM policies, PostgreSQL cloud instances, model services and network connectivity are operator prerequisites, not automatically created resources.

## Use in Studio

Choose **Agents → MPA agents → Create MPA agent**. Managers with agent-management permission can set the stable agent ID and description. Review the resource plan and submit. The workflow prepares account network/APIG/IM Gateway, a worker, an isolated business database and Skill Space, then deploys and checks Runtime and application readiness. Successful creation refreshes the directory.

The initial configuration check is local validation, **not** proof of live permissions or connectivity. Cloud identity and database permissions are checked after submission and before resource creation; each later cloud step validates its own response. Close the dialog to leave creation running, or cancel explicitly to stop orchestration. Reopen it in the same browser session to recover progress. The dialog supports keyboard operation, multiline Chinese input, both themes and narrow windows.

## CLI

```bash
veadk mpa provision --config /secure/mpa-create.config.yaml --agent-id customer-service --dry-run
veadk mpa provision --config /secure/mpa-create.config.yaml --agent-id customer-service --description "Customer service"
```

`--dry-run` validates local configuration and prints a safe plan without cloud/database calls. Actual creation can allocate billable cloud resources. Legacy `veadk mpa create` remains unchanged and does not prepare these managed prerequisites.

Managed flat mode reads image, registry name, model provider/base/key/name, PostgreSQL host/port/user/password/SSL settings, Runtime role and project. It derives a separate business database per agent; legacy `pg-database`, Tool selection, channel and OpenViking options are not implicitly applied to this mode. Use a private Runtime template for additional application environment settings, and `managed.worker` for worker selection. Bind channels after creation through Studio's MPA message channels page. An optional flat `account-id` is only an assertion against the authenticated account.

## Recovery and retained resources

Keep the same agent ID, request identity and original configuration when retrying. Shared PostgreSQL tables `mpa_account_network`, `mpa_account_apig` and `mpa_agent_deployment` retain resource identity, ownership, creation intent and client tokens. Another Studio owner cannot claim the same deployment. Native deployments without a Studio owner are not implicitly adopted; use a new agent ID. CLI-created deployments use a distinct CLI owner.

Studio stores nonsecret task state in `.adk/mpa-creation.sqlite3` (override with server-only `VEADK_MPA_TASK_DB`). Keep this file across restarts. It permits one active task per owner and four overall. Dead supervisors are reconciled on lookup/start; failed/cancelled tasks resume with the original request ID. There is no automatic task-history expiration. Browser session storage contains only the request and task identity. Server shutdown, timeout (default 1800 seconds, configurable 60–7200) or cancellation terminates and reaps the child process.

Cancellation is not cloud rollback. APIG/VPC, business database, Skill Space, worker and any Runtime already created remain for recovery; an in-flight cloud request may complete after cancellation. Do not delete shared resources to retry. Unknown create results use persisted intent and client tokens; conflicting unfinished configuration stops with an error. Success requires platform Ready **and** the application's `/readiness`. Task responses contain safe stage/error codes and resource IDs, never raw deployment logs or credentials.

See the [component contract](../../../../specs/studio-mpa-creation/README.md) and [verification record](../../../../prd-spec/features/mpa-agent-oneclick-provision/2026-09-20-studio-mpa-creation.md). Tests simulate cloud operations; live deployment requires separately supplied credentials and an isolated target.

### Runtime display names

New managed Runtime names equal the agent ID entered in Studio or supplied as `--agent-id`, for example `mi-example`. AgentKit still assigns a separate `r-...` Runtime ID. Existing Runtime names stay unchanged; the current update API has no Name parameter. Retrying unfinished legacy creation preserves the original hashed name and request token when its original inputs match. Database, worker and Skill Space naming remain scoped to the account, region and agent identity.

### Explicit MPA and worker images

Use `managed.runtime.image` to pin the MPA image independently of `managed.worker.image`:

```yaml
managed:
  version: 1
  from-runtime: r-reference
  runtime:
    image: registry.example/agentkit/mpa_agent:release-tag
  worker:
    image: registry.example/agentkit/mpa_codex_worker:release-tag
```

This is an excerpt; retain the other required settings. `from-runtime` supplies role, compute/scaling/concurrency, APM/project, VPC and sanitized environment settings such as model/database connectivity, as well as its default image. The explicit Runtime image overrides that default as a custom image. The same override applies to `template-file` and flat mode; flat mode may omit top-level `image` when this field is set. Omission/null preserves previous behavior; blank, whitespace-containing or placeholder image values fail validation. Source selection is unchanged. Changing this setting does not automatically update existing agents; retain the original effective image when retrying unfinished creation.

### Explicit infrastructure without a reference Runtime

Remove `managed.from-runtime` and `managed.template-file` to use the flat model/database fields plus these overrides:

```yaml
managed:
  version: 1
  runtime:
    image: registry.example/agentkit/mpa_agent:release-tag
    role-name: IDRoleForArkClawShareAgent
    cpu-milli: 2000       # 2 CPU cores
    memory-mb: 4096      # 4 GiB
    min-instance: 1
    max-instance: 1
    max-concurrency: 100
    apmplus-enable: true
    project-name: default
    env:
      CLOUD_PROVIDER: volcengine
  network:
    vpc-id: vpc-existing
    subnet-ids: [subnet-existing]
  worker:
    image: registry.example/agentkit/mpa_codex_worker:release-tag
model-provider: openai
model-name: your-model
model-api-base: https://model.example/api/v3
model-api-key: "${MPA_MODEL_API_KEY}"
pg-host: database.example
pg-port: "5432"
pg-user: app
pg-password: "${MPA_PG_PASSWORD}"
pg-sslmode: require
pg-channel-binding: require
```

Retain region, shared/admin database secret references and any worker-specific settings from the complete example. `runtime.env` supports additional string application settings and complete environment-variable references; it cannot supply provisioner-owned identities, generated database names, Runtime keys or deployment database URLs. With any source mode, explicit runtime fields win; omission retains its defaults. Minimum instances may be zero, but cannot exceed the effective maximum. Network provisioning still requires public/private connectivity and does not create database allowlists. Pinning settings makes later reference Runtime changes irrelevant to this profile. A worker `reference-id`, if retained, still supplies that worker's environment separately. These settings affect future provisioning; existing instances are not automatically redeployed.

### Choosing images when creating in Studio

The creation dialog contains **MPA image** and **Worker image** text inputs, initially filled from the current server configuration. Edit either image for this creation, or clear it to use the configured default. These fields accept container references such as `registry.example/mpa:v2` or `registry.example/worker@sha256:<64 hex digits>`, not download URLs or registry login credentials. They do not edit the YAML or redeploy existing agents. Submitting locks both inputs; failure, cancellation, closing and reopening retain the original request and known effective images for safe retry. A configuration based only on a reference Runtime/existing worker may have no locally available image default to display; leaving it blank retains that source. Administrators remain responsible for image access and compatibility. Explicit Worker image input provisions a dedicated worker, even when the profile otherwise selects an existing worker.

### Worker retries and failure diagnostics

Worker reference/discovery/create/read calls retry recognized timeouts, connection failures, throttling and temporary service errors up to **4 attempts**, waiting **1, 2, 4 seconds**. Create calls reuse the persisted payload and ClientToken. Recognized not-found is retried only for a registered managed Worker; missing reference/existing Workers, permission errors, invalid parameters and ownership conflicts fail immediately. Worker preparation has a default 600-second budget, including retries, and obeys task cancellation/deadlines. SDK-internal retries may add network requests. Unknown errors still require investigation/manual retry with the same identity; this does not guarantee every provider failure recovers.

Studio writes safe diagnostic categories to the server log and the private task database's `task_diagnostics` table. The latest 100 events per task survive manual retry and restart. Events contain task ID, timestamp, stage, operation, attempt, category and outcome (`retrying`, `failed`, `cancelled`), never raw messages, credentials or request payloads. Existing HTTP error codes and dialog behavior remain unchanged. To inspect locally:

```bash
sqlite3 -readonly .adk/mpa-creation.sqlite3 "SELECT task_id,datetime(created,'unixepoch'),stage,operation,category,attempt,outcome FROM task_diagnostics ORDER BY id DESC LIMIT 30;"
```

Use the configured `VEADK_MPA_TASK_DB` path when overridden. Times in this example are UTC. `permission` requires checking deployment credentials/permissions; `invalid_request` requires configuration checks; `ownership` and `configuration_changed` require reconciling the original resource identity/inputs. `timeout`, `connection`, `throttled` and `unavailable` distinguish transient failures; `not_found` identifies delayed visibility or missing resources, depending on the operation. `unknown`/`provider_error` means the provider error was not safely recognized, not success. Abnormal child exit, supervisor interruption, deadline and cancellation are also recorded. Historical errors discarded by older versions cannot be recovered.

### Initialization metadata delays

For managed Workers with a persisted creation ID/token/hash, missing ID/project/ownership tags during initialization are polled up to four incomplete observations, waiting 5, 10 and 20 seconds. This handles resources whose metadata becomes visible after CreateTool returns. Explicit conflicting values still fail immediately; Ready with missing metadata and terminal/unknown states receive no grace. These waits respect the existing stage deadline/cancellation and never create another Worker. Safe diagnostic operations identify the affected field (`worker_id`, `worker_project`, `worker_managed_by`, `worker_agent_key`, `worker_agent_binding`, `worker_state`); `metadata_pending` means waiting, `metadata_missing` means the bounded check failed. Field values remain private.
